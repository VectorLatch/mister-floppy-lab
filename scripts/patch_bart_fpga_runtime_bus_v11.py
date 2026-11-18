#!/usr/bin/env python3
"""Bart v11: tune CPU chip/custom and CIA bus wait opportunities at runtime.

Apply after pinned Rick ERSY v4 and Bart v1/v2/v3/v6/v8 patches.
E8xx is a *write-only* diagnostic HPS SPI command, unlike read-only E7xx.
Zero waits is the exact original acknowledged-data path. The settings
survive Amiga soft resets and only reset when the FPGA image is reloaded.
No floppy, DMA scheduler, pixel, CPU instruction or host boot memory edits.
"""
from pathlib import Path
import subprocess
import sys

PINNED="7d5d3c2f685af4ce3eb361c22893fccd153f2d87"

def once(s,old,new,label):
    n=s.count(old)
    if n!=1:
        raise RuntimeError(f"{label}: expected exactly one anchor, found {n}")
    return s.replace(old,new,1)

def apply(root):
    actual=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    if actual!=PINNED:
        raise RuntimeError(f"Unexpected pinned upstream FPGA SHA: {actual}")
    paths={k:root/p for k,p in {
        "top":"Minimig.sv",
        "mini":"rtl/minimig.v",
        "paula":"rtl/paula.v",
        "floppy":"rtl/paula_floppy.v",
        "bridge":"rtl/minimig_m68k_bridge.v"}.items()}
    d={k:p.read_text() for k,p in paths.items()}
    if "16'hB4AD" not in d["floppy"] or "bart_diag_command" not in d["floppy"]:
        raise RuntimeError("V11 requires the existing v8 FPGA diagnostic overlays")

    # Route a single 4-bit latched configuration: {CIA wait[1:0], chip wait[1:0]}.
    # No top-level extra pins: CPU bus controller and Paula live in minimig.v.
    d["floppy"]=once(d["floppy"],
        "\toutput reg [15:0] IO_DOUT,",
        "\toutput reg [15:0] IO_DOUT,\n"
        "\toutput reg [3:0] bart_v11_waits = 4'b0000, // held through Amiga soft reset",
        "Paula floppy control output")
    d["floppy"]=once(d["floppy"],
        "reg bart_diag_command;",
        """reg bart_diag_command;
// E8xx write command: second SPI word carries low 4 bits:
//   bits 1:0: extra chip/slow/custom-register DTACK qualified cycles (0..3)
//   bits 3:2: extra CIA E-clock acknowledge opportunities (0..3)
// No command can edit a data path, CPU opcode, pixel or floppy byte.
reg bart_v11_cmd = 1'b0;
always @(posedge clk) begin
    if (clk7_en) begin
        if (!IO_ENA) bart_v11_cmd <= 0;
        else if (stb7 && cmd_cnt == 2'd0)
            bart_v11_cmd <= (rx_data[15:8] == 8'hE8);
        else if (stb7 && cmd_cnt == 2'd1 && bart_v11_cmd)
            bart_v11_waits <= rx_data[3:0];
    end
end
""",
        "E8xx config input")
    d["floppy"]=once(d["floppy"],
        "    if (bart_diag_command && cmd_cnt != 2'd0)\n        tx_data = bart_diag_word;",
        """    if (bart_diag_command && cmd_cnt != 2'd0)
        tx_data = bart_diag_word;
    else if (bart_v11_cmd && cmd_cnt != 2'd0)
        tx_data = 16'hB800 | {12'd0, bart_v11_waits};""",
        "E8xx configuration readback")

    d["paula"]=once(d["paula"],
        "\toutput [15:0] IO_DOUT,",
        "\toutput [15:0] IO_DOUT,\n"
        "\toutput [3:0] bart_v11_waits,",
        "Paula output port")
    d["paula"]=once(d["paula"],
        "\t.IO_DOUT(IO_DOUT),",
        "\t.IO_DOUT(IO_DOUT),\n"
        "\t.bart_v11_waits(bart_v11_waits),",
        "Paula floppy output hook")

    d["mini"]=once(d["mini"],
        "wire [15:0] IO_DOUT_PAULA;",
        "wire [15:0] IO_DOUT_PAULA;\n"
        "wire [3:0] bart_v11_waits; // live HPS diagnostic bus waits, 0/0=stock",
        "Minimig wait register wire")
    d["mini"]=once(d["mini"],
        "\t.IO_DOUT(IO_DOUT_PAULA),",
        "\t.IO_DOUT(IO_DOUT_PAULA),\n"
        "\t.bart_v11_waits(bart_v11_waits),",
        "Minimig Paula wait source")
    d["mini"]=once(d["mini"],
        "\t.nrdy((gayle_nrdy & rd_cyc) | a2065_nrdy),",
        "\t.nrdy((gayle_nrdy & rd_cyc) | a2065_nrdy),\n"
        "\t.bart_v11_waits(bart_v11_waits),",
        "Minimig 68000 bus wait hook")

    d["bridge"]=once(d["bridge"],
        "\tinput         nrdy,          // target device is not ready",
        "\tinput         nrdy,          // target device is not ready\n"
        "\tinput [3:0] bart_v11_waits, // [1:0] chip/custom, [3:2] CIA",
        "68000 chip bridge new runtime wait inputs")
    old="""reg _ta_n; // transfer acknowledge
always @(posedge clk or posedge _as_and_cs) begin
\tif (_as_and_cs) _ta_n <= 1;
\telse if (clk7n_en) begin
\t\tif (!l_as && cck && ((!vpa && !(dbr && dbs) && !(blit_nasty && blt_wr)) || (vpa && vma && eclk[8])) && !nrdy) _ta_n <= 0;
\tend
end"""
    new="""reg _ta_n; // transfer acknowledge
reg [1:0] bart_v11_wait_seen = 2'd0;
// For standard CPU bus reads and writes, insert 0-3 *eligible acknowledge
// opportunities* on the CPU bridge. The CIA opportunities are ECLK-aligned.
// Do not delay MiSTer HPS host cycles or change the DMA slot scheduler.
// With config 0 the original dtack condition and cycle are unchanged.
wire [1:0] bart_v11_wait_target =
    halt ? 2'd0 :
    vpa ? bart_v11_waits[3:2] :
    dbs ? bart_v11_waits[1:0] : 2'd0;
wire bart_v11_can_ack =
    !l_as && cck &&
    ((!vpa && !(dbr && dbs) && !(blit_nasty && blt_wr)) ||
     (vpa && vma && eclk[8])) && !nrdy;
always @(posedge clk or posedge _as_and_cs) begin
    if (_as_and_cs) begin
        _ta_n <= 1;
        bart_v11_wait_seen <= 0;
    end else if (clk7n_en) begin
        if (bart_v11_can_ack) begin
            if (bart_v11_wait_seen < bart_v11_wait_target)
                bart_v11_wait_seen <= bart_v11_wait_seen + 2'd1;
            else
                _ta_n <= 0;
        end
    end
end"""
    d["bridge"]=once(d["bridge"],old,new,"68000 DTACK qualified wait logic")
    # All changes must be purposeful; never touch user-adjustable video,
    # floppy pipeline, DMA grant, CPU instruction stream or OCS state machine.
    for name,path in paths.items():
        if d[name] != path.read_text():
            path.write_text(d[name])
    print("Bart v11 E8xx runtime CPU-bus wait controller installed (0..3 chip, CIA).")
    print("FPGA defaults = 0/0, zero setting retains original DTACK expression.")
    print("No timing settings are magically loaded from MiSTer.ini; Main must send E8.")

if __name__=="__main__":
    if len(sys.argv)!=2:
        raise SystemExit("Usage: patch_bart_fpga_runtime_bus_v11.py <pinned FPGA root>")
    apply(Path(sys.argv[1]).resolve())
