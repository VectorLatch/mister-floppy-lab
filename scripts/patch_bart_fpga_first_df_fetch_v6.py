#!/usr/bin/env python3
"""Bart first fetch into DFxxxx, with six preceding program-fetch addresses.

Overlay on exact v1/v2/v3 diagnostic patches and working Rick ERSY patch.
Read-only ring and one-shot frozen trace. Existing SPI slots 0..44 remain
unchanged; add 45..63 (six preceding program-space fetches, trigger,
live internal PC/PSW/IRD at trigger, and validity flags). No functional
CPU/exception/Paula/physical-floppy control signals change.
"""
from pathlib import Path
import subprocess
import sys

PINNED="7d5d3c2f685af4ce3eb361c22893fccd153f2d87"

def once(s,old,new,label):
    n=s.count(old)
    if n!=1:
        raise ValueError(f"{label}: expected one source anchor, found {n}")
    return s.replace(old,new,1)

def apply(root):
    sha=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    if sha!=PINNED: raise ValueError(f"Wrong pinned FPGA source {sha}")
    paths={
        "fx":root/"rtl/fx68k/fx68k.sv",
        "cpu":root/"rtl/cpu_wrapper.v",
        "top":root/"Minimig.sv",
        "minimig":root/"rtl/minimig.v",
        "paula":root/"rtl/paula.v",
        "floppy":root/"rtl/paula_floppy.v",
    }
    d={k:p.read_text() for k,p in paths.items()}
    d["fx"]=paths["fx"].read_bytes().decode("utf-8")
    if "16'hB4A8" not in d["floppy"] or "bart_fx_err" not in d["cpu"]:
        raise ValueError("Apply original Bart FPGA v1/v2/v3 before v6")

    # The fx68k instruction fetch bus address is *not* necessarily its
    # architectural PC. Also record the core's internal PcH/PcL.
    # Preserve mixed CRLF/LF bytes in original fx68k.sv (v3 behavior).
    d["fx"]=once(d["fx"],
        "\toutput [7:0] oDbgErrorFlags,\r\n\tinput DTACKn,",
        "\toutput [7:0] oDbgErrorFlags,\r\n"
        "\toutput wire [31:0] oDbgPc,\r\n"
        "\tinput DTACKn,",
        "fx68k internal PC observation port")
    d["fx"]=once(d["fx"],
        "\treg [15:0] PcL, PcH;",
        "\treg [15:0] PcL, PcH;\n"
        "\tassign oDbgPc = {PcH, PcL};",
        "excUnit internal PC observer")
    # There are two modules in fx68k.sv. Port name is scoped within excUnit.
    d["fx"]=once(d["fx"],
        "\toutput logic [23:1] eab);",
        "\toutput logic [23:1] eab,\n"
        "\toutput wire [31:0] oDbgPc);",
        "excUnit PC debug port")
    d["fx"]=once(d["fx"],
        "\t\t.alue, .ccr);",
        "\t\t.alue, .ccr, .oDbgPc(bart_pc_internal));",
        "connect fx68k->excUnit PC")
    d["fx"]=once(d["fx"],
        "\twire [3:0] bart_seq_grp0;",
        "\twire [3:0] bart_seq_grp0;\n"
        "\twire [31:0] bart_pc_internal;\n"
        "\tassign oDbgPc = bart_pc_internal;",
        "parent PC observation wire")

    fields=[("addr%d"%i,32) for i in range(7)]+[
        ("pc",32),("psw",16),("ird",16),("flags",16)]
    port_names=lambda kind: "".join(
        "\t%s [%d:0] bart_df_%s,\n"%(kind,width-1,name)
        for name,width in fields)
    d["cpu"]=once(d["cpu"],"\toutput reg [15:0] bart_fx_err,",
        "\toutput reg [15:0] bart_fx_err,\n"+port_names("output reg").rstrip("\n"),
        "CPU frozen DF trace ports")
    d["cpu"]=once(d["cpu"],"wire [15:0] bart_fx_ird_wire;",
        "wire [15:0] bart_fx_ird_wire;\n"
        "wire [31:0] bart_pc_internal_wire;",
        "CPU raw internal PC wire")
    d["cpu"]=once(d["cpu"],"\t.oDbgIrd(bart_fx_ird_wire),",
        "\t.oDbgIrd(bart_fx_ird_wire),\n"
        "\t.oDbgPc(bart_pc_internal_wire),",
        "CPU fx68k debug PC hookup")

    # Historical trace addresses are 24-bit external addresses padded to
    # 32 bits to allow simple 16-bit SPI registers. Older history is only
    # valid if enough fetch cycles occurred; trace flags indicate activation.
    logic="""
// Bart V6 first *qualified program-space fetch* into $DF0000-$DFFFFF.
// This is a probe, not proof that the CPU retired any instruction there.
// The ring holds 6 fetch start addresses; a first transition from outside
// the DF region freezes it with the DF fetch and internal fx68k state.
// Stop updating the ring after trigger to minimize perturbations.
// FX path is selected only when cpucfg[1:0]==0, as in Bart A500 setup.
reg [31:0] bart_df_roll0, bart_df_roll1, bart_df_roll2;
reg [31:0] bart_df_roll3, bart_df_roll4, bart_df_roll5;
reg bart_df_have_prev;
reg bart_df_prev_region;
wire bart_df_is_region = (bart_fetch_addr[23:16] == 8'hDF);
wire bart_df_trigger = (cpucfg[1:0] == 0) && bart_fetch_evt
    && bart_df_is_region && (!bart_df_have_prev || !bart_df_prev_region)
    && !bart_df_flags[0];
always @(posedge clk) begin
    if (~reset) begin
        bart_df_roll0 <= 0; bart_df_roll1 <= 0;
        bart_df_roll2 <= 0; bart_df_roll3 <= 0;
        bart_df_roll4 <= 0; bart_df_roll5 <= 0;
        bart_df_have_prev <= 0;
        bart_df_prev_region <= 0;
        bart_df_addr0 <= 0; bart_df_addr1 <= 0;
        bart_df_addr2 <= 0; bart_df_addr3 <= 0;
        bart_df_addr4 <= 0; bart_df_addr5 <= 0;
        bart_df_addr6 <= 0;
        bart_df_pc <= 0; bart_df_psw <= 0;
        bart_df_ird <= 0; bart_df_flags <= 0;
    end else if (bart_fetch_evt && !bart_df_flags[0]) begin
        if (bart_df_trigger) begin
            // Oldest -> newest: six preceding addresses, then DF entry.
            bart_df_addr0 <= bart_df_roll5;
            bart_df_addr1 <= bart_df_roll4;
            bart_df_addr2 <= bart_df_roll3;
            bart_df_addr3 <= bart_df_roll2;
            bart_df_addr4 <= bart_df_roll1;
            bart_df_addr5 <= bart_df_roll0;
            bart_df_addr6 <= bart_fetch_addr;
            bart_df_pc <= bart_pc_internal_wire;
            bart_df_psw <= bart_fx_psw_wire;
            bart_df_ird <= bart_fx_ird_wire;
            // bit0=triggered; bit1=previous fetch existed;
            // bit2=fx68k; bit3=first fetch after reset was DF.
            bart_df_flags <= {12'd0, !bart_df_have_prev,
                              1'b1, bart_df_have_prev, 1'b1};
        end else begin
            bart_df_roll5 <= bart_df_roll4;
            bart_df_roll4 <= bart_df_roll3;
            bart_df_roll3 <= bart_df_roll2;
            bart_df_roll2 <= bart_df_roll1;
            bart_df_roll1 <= bart_df_roll0;
            bart_df_roll0 <= bart_fetch_addr;
            bart_df_have_prev <= 1;
            bart_df_prev_region <= bart_df_is_region;
        end
    end
end
"""
    d["cpu"]=once(d["cpu"],"\nreg inflight;\n",
        "\n"+logic+"\nreg inflight;\n","CPU first DF capture logic")

    wires="".join("wire [%d:0] bart_df_%s;\n"%(width-1,name)
                  for name,width in fields)
    d["top"]=once(d["top"],"cpu_wrapper cpu_wrapper\n",
        wires+"\ncpu_wrapper cpu_wrapper\n","Minimig top v6 wires")
    hooks="".join("\t.bart_df_%s(bart_df_%s),\n"%(name,name)
                  for name,width in fields)
    anchor="\t.bart_fx_err(bart_fx_err),\n"
    if d["top"].count(anchor)!=2:
        raise ValueError("Expected exactly two top fx68k diagnostic hook instances")
    d["top"]=d["top"].replace(anchor,anchor+hooks)

    inp=port_names("input")
    for name in ("minimig","paula","floppy"):
        d[name]=once(d[name],"\tinput [15:0] bart_fx_err,",
            "\tinput [15:0] bart_fx_err,\n"+inp.rstrip("\n"),
            f"{name} read-only DF trace inputs")
    for name in ("minimig","paula"):
        d[name]=once(d[name],anchor,anchor+hooks,
            f"{name} DF readout forwarding")

    d["floppy"]=once(d["floppy"],"6'd0: bart_diag_word = 16'hB4A8;",
        "6'd0: bart_diag_word = 16'hB4AB;","new FPGA signature")
    d["floppy"]=once(d["floppy"],"6'd1: bart_diag_word = 16'd3;",
        "6'd1: bart_diag_word = 16'd6;","new version")
    # Exactly fills the 6-bit 0..63 SPI index space without modifying
    # existing snapshot data registers 0..44 or SPI command decoding.
    words=[]
    for i in range(7):
        words.append("        6'd%d: bart_diag_word = bart_df_addr%d[15:0];"%(45+2*i,i))
        words.append("        6'd%d: bart_diag_word = bart_df_addr%d[31:16];"%(46+2*i,i))
    words+= [
        "        6'd59: bart_diag_word = bart_df_pc[15:0];",
        "        6'd60: bart_diag_word = bart_df_pc[31:16];",
        "        6'd61: bart_diag_word = bart_df_psw;",
        "        6'd62: bart_diag_word = bart_df_ird;",
        "        6'd63: bart_diag_word = bart_df_flags;",
    ]
    d["floppy"]=once(d["floppy"],
        "        6'd44: bart_diag_word = bart_fx_err;\n"
        "        default: bart_diag_word = 16'hDEAD;",
        "        6'd44: bart_diag_word = bart_fx_err;\n"
        +"\n".join(words)+"\n"
        "        default: bart_diag_word = 16'hDEAD;",
        "extend FPGA diagnostic to 64 words")

    for name,path in paths.items():
        if name=="fx":
            path.write_bytes(d[name].encode("utf-8"))
        else:
            path.write_text(d[name])
    print("Applied first-DF-fetch freeze trace with six preceding fetches.")
    print("SPI B4AB version6, 64 words (0..63), other state readouts unchanged.")

if __name__=="__main__":
    if len(sys.argv)!=2:
        raise SystemExit("Usage: patch_bart_fpga_first_df_fetch_v6.py <pinned FPGA source>")
    apply(Path(sys.argv[1]).resolve())
