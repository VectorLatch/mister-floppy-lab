#!/usr/bin/env python3
"""Bart v8: read-only first Line-F and first/last pre-LineF CPU RESET events.

Apply AFTER Rick ERSY v4 and Bart diagnostic v1,v2,v3,v6 overlays,
not v4/v5/v7. Keep 64-word E7xx on-demand SPI diagnostic transport.
Repurpose v6 words 45..63. No change to fx68k microcode, bus/control,
floppy datapath, memory datapath, OSD reset, or CPU reset behaviour.

Line-F event is precisely the sequencer's grp1LatchEn & enT3 & isLineF
condition, one edge before rLineF updates. Record the decoded IR (not
the possibly older IRD). CPU RESET-output assertion is a falling edge
of fx68k oRESETn, distinct from the CPU reset input. Also observe
Minimig's Kickstart overlay 'ovl' at the event through an output port.
"""
from pathlib import Path
import subprocess
import sys

PINNED="7d5d3c2f685af4ce3eb361c22893fccd153f2d87"

def once(s,old,new,label):
    n=s.count(old)
    if n!=1:
        raise ValueError(f"{label}: expected exactly one anchor, found {n}")
    return s.replace(old,new,1)

def apply(root):
    rev=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    if rev!=PINNED: raise ValueError(f"Wrong FPGA source commit: {rev}")
    paths={
        "fx":root/"rtl/fx68k/fx68k.sv",
        "cpu":root/"rtl/cpu_wrapper.v",
        "top":root/"Minimig.sv",
        "mini":root/"rtl/minimig.v",
        "floppy":root/"rtl/paula_floppy.v",
    }
    d={k:p.read_text() for k,p in paths.items()}
    d["fx"]=paths["fx"].read_bytes().decode("utf-8")
    if "16'hB4AB" not in d["floppy"] or "bart_df_roll0" not in d["cpu"] \
            or "oDbgPc" not in d["fx"] or "bart_seq_grp0" not in d["fx"]:
        raise ValueError("v8 requires exact preceding v1/v2/v3/v6 patches")

    # fx68k is *observed*, never fed a diagnostic signal.
    d["fx"]=once(d["fx"],
        "\toutput wire [31:0] oDbgPc,\r\n\tinput DTACKn,",
        "\toutput wire [31:0] oDbgPc,\r\n"
        "\toutput wire [15:0] oDbgIr,\r\n"
        "\toutput wire oDbgLineFPulse,\r\n"
        "\tinput DTACKn,",
        "fx68k debug-only observation ports")
    d["fx"]=once(d["fx"],
        "\tassign oDbgIrd = Ird;",
        "\tassign oDbgIrd = Ird;\n\tassign oDbgIr = Ir;",
        "decode-stage IR observation")
    d["fx"]=once(d["fx"],
        "\twire [3:0] bart_seq_grp0;",
        "\twire [3:0] bart_seq_grp0;\n"
        "\twire bart_seq_linef_pulse;\n"
        "\tassign oDbgLineFPulse = bart_seq_linef_pulse;",
        "fx68k read-only LineF event tap")
    d["fx"]=once(d["fx"],
        ".nma, .oDbgGrp0(bart_seq_grp0), .a1,",
        ".nma, .oDbgGrp0(bart_seq_grp0), "
        ".oDbgLineFPulse(bart_seq_linef_pulse), .a1,",
        "fx68k sequencer LineF event connection")
    d["fx"]=once(d["fx"],
        "\toutput wire [3:0] oDbgGrp0);",
        "\toutput wire [3:0] oDbgGrp0,\n"
        "\toutput wire oDbgLineFPulse);",
        "sequencer read-only LineF port")
    d["fx"]=once(d["fx"],
        "\tassign grp1LatchEn = microLatch[0] & (microLatch[1] | !microLatch[4]);",
        "\tassign grp1LatchEn = microLatch[0] & (microLatch[1] | !microLatch[4]);\n"
        "\tassign oDbgLineFPulse = grp1LatchEn & enT3 & isLineF;",
        "real sequencer LineF latch qualification")

    # Existing cpu_wrapper's v6 probe transport exposes 7x32 + 1x32 +
    # 3x16 bits, enough to record reset / LineF independently.
    d["cpu"]=once(d["cpu"],
        "\tinput             reset,",
        "\tinput             reset,\n\tinput             bart_dbg_overlay,",
        "CPU wrapper overlay observation input")
    d["cpu"]=once(d["cpu"],
        "wire [31:0] bart_pc_internal_wire;",
        "wire [31:0] bart_pc_internal_wire;\n"
        "wire [15:0] bart_ir_wire;\n"
        "wire bart_linef_pulse_wire;",
        "read-only CPU stage input wires")
    d["cpu"]=once(d["cpu"],
        "\t.oDbgPc(bart_pc_internal_wire),",
        "\t.oDbgPc(bart_pc_internal_wire),\n"
        "\t.oDbgIr(bart_ir_wire),\n"
        "\t.oDbgLineFPulse(bart_linef_pulse_wire),",
        "CPU observability-only fx68k hooks")

    start_marker="// Bart V6 first *qualified program-space fetch* into $DF0000-$DFFFFF."
    end_marker="\nreg inflight;\n"
    start=d["cpu"].find(start_marker)
    end=d["cpu"].find(end_marker,start)
    if start<0 or end<0 or d["cpu"].find(start_marker,start+1)>=0:
        raise ValueError("Cannot locate unique v6 first-DF recorder block")

    logic="""
// Bart v8. Freeze first asserted 68000 RESET output and first Line-F
// exception recognition. Track last RESET event before first Line-F.
// This block is READ ONLY, has no connection to functional CPU inputs.
// Source: reset_out_o is fx68k.oRESETn, bart_linef_pulse_wire comes
// from sequencer grp1LatchEn & enT3 & isLineF (not a blind IR nibble).
reg bart_ev_reset_out_d;
wire bart_ev_reset_start = bart_ev_reset_out_d && !reset_out_o;
wire bart_ev_linef_event = bart_linef_pulse_wire;

// Reuse v6 64-word diagnostic output register slots 45..63:
// addr0 first reset internal PC (32)
// addr1 latest reset PC before first Line-F (32)
// addr2 latest reset's last program fetch bus address (32)
// addr3 latest reset's previous program fetch bus address (32)
// addr4 first Line-F internal PC (32)
// addr5 Line-F latest program fetch bus address (32)
// addr6 Line-F previous program fetch bus address (32)
// pc[31:16] latest reset PSW, [15:0] first Line-F PSW
// psw latest reset decoded Ir, ird first Line-F decoded Ir
// flags[0] CPU RESET output seen, [1] Line-F recognized,
// [2] Kickstart ovl at latest RESET, [3] ovl at first Line-F,
// [4] reset previously seen at Line-F, [5] reset output active
// at Line-F, [6] current ovl sampled at snapshot,
// [7] last sampled CPU reset output low (live),
// [15:8] RESET output assertion count (saturated).
always @(posedge clk) begin
    if (!reset) begin
        bart_ev_reset_out_d <= 1'b1;
        bart_df_addr0 <= 32'd0;
        bart_df_addr1 <= 32'd0;
        bart_df_addr2 <= 32'd0;
        bart_df_addr3 <= 32'd0;
        bart_df_addr4 <= 32'd0;
        bart_df_addr5 <= 32'd0;
        bart_df_addr6 <= 32'd0;
        bart_df_pc <= 32'd0;
        bart_df_psw <= 16'd0;
        bart_df_ird <= 16'd0;
        bart_df_flags <= 16'd0;
    end else begin
        bart_ev_reset_out_d <= reset_out_o;
        // Live overlay and RESET output sampled for the on-demand read.
        bart_df_flags[6] <= bart_dbg_overlay;
        bart_df_flags[7] <= ~reset_out_o;

        if (bart_ev_reset_start && !bart_df_flags[1]) begin
            if (!bart_df_flags[0])
                bart_df_addr0 <= bart_pc_internal_wire;
            bart_df_flags[0] <= 1'b1;
            bart_df_flags[2] <= bart_dbg_overlay;
            if (bart_df_flags[15:8] != 8'hFF)
                bart_df_flags[15:8] <= bart_df_flags[15:8] + 8'd1;
            bart_df_addr1 <= bart_pc_internal_wire;
            bart_df_addr2 <= bart_last_fetch;
            bart_df_addr3 <= bart_prev_fetch;
            bart_df_pc[31:16] <= bart_fx_psw_wire;
            bart_df_psw <= bart_ir_wire;
        end

        if (bart_ev_linef_event && !bart_df_flags[1]) begin
            bart_df_flags[1] <= 1'b1;
            bart_df_flags[3] <= bart_dbg_overlay;
            bart_df_flags[4] <= bart_df_flags[0];
            bart_df_flags[5] <= ~reset_out_o;
            bart_df_addr4 <= bart_pc_internal_wire;
            bart_df_addr5 <= bart_last_fetch;
            bart_df_addr6 <= bart_prev_fetch;
            bart_df_pc[15:0] <= bart_fx_psw_wire;
            bart_df_ird <= bart_ir_wire;
        end
    end
end
"""
    d["cpu"]=d["cpu"][:start]+logic+d["cpu"][end:]

    # Export *only* the current OVL state, no write or control changes.
    d["mini"]=once(d["mini"],
        "\toutput \t     rst_out,     // minimig reset status",
        "\toutput \t     rst_out,     // minimig reset status\n"
        "\toutput wire bart_dbg_overlay, // read-only overlay state",
        "Minimig overlay debug port")
    d["mini"]=once(d["mini"],
        "reg ovl; //kickstart overlay enable",
        "reg ovl; //kickstart overlay enable\n"
        "assign bart_dbg_overlay = ovl;",
        "Minimig read-only overlay export")

    d["top"]=once(d["top"],
        "cpu_wrapper cpu_wrapper\n",
        "wire bart_dbg_overlay;\n\ncpu_wrapper cpu_wrapper\n",
        "top-level overlay monitor wire")
    d["top"]=once(d["top"],
        "\t.reset        (cpu_rst         ),",
        "\t.reset        (cpu_rst         ),\n"
        "\t.bart_dbg_overlay(bart_dbg_overlay),",
        "CPU monitor overlay input")
    d["top"]=once(d["top"],
        "\t.rst_out      (                 ), // minimig reset status",
        "\t.rst_out      (                 ), // minimig reset status\n"
        "\t.bart_dbg_overlay(bart_dbg_overlay),",
        "Minimig overlay output tap")

    d["floppy"]=once(d["floppy"],
        "6'd0: bart_diag_word = 16'hB4AB;",
        "6'd0: bart_diag_word = 16'hB4AD;",
        "v8 matched signature")
    d["floppy"]=once(d["floppy"],
        "6'd1: bart_diag_word = 16'd6;",
        "6'd1: bart_diag_word = 16'd8;",
        "v8 matched version")
    for s in (
        "6'd45: bart_diag_word = bart_df_addr0[15:0];",
        "6'd58: bart_diag_word = bart_df_addr6[31:16];",
        "6'd59: bart_diag_word = bart_df_pc[15:0];",
        "6'd63: bart_diag_word = bart_df_flags;",
    ):
        if s not in d["floppy"]:
            raise ValueError(f"Unexpected 64-word v6 transport: missing {s}")
    for name,path in paths.items():
        if name=="fx":path.write_bytes(d[name].encode("utf-8"))
        else:path.write_text(d[name])
    print("V8 first RESET and first Line-F event recorder applied.")
    print("Overlay tapped read-only; SPI B4AD version 8 uses same 64 words.")
    print("No functional processor, Paula, DMA, memory or reset paths modified.")

if __name__=="__main__":
    if len(sys.argv)!=2:
        raise SystemExit("Usage: patch_bart_fpga_first_reset_linef_v8.py <pinned FPGA source>")
    apply(Path(sys.argv[1]).resolve())
