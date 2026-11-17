#!/usr/bin/env python3
"""Bart v9: read-only OCS Denise bitplane/ownership and DMA-path probes.

Apply after the exact v8 FPGA overlay, preserving all pre-existing v1/v2/v3/v6
CPU/floppy diagnostic slots 0..44. Reuse SPI slots 45..63 for graphic counters.
No changes to bitplane shifters, Copper/Blitter control or memory datapaths.
"""
from pathlib import Path
import subprocess
import sys
import re

PINNED="7d5d3c2f685af4ce3eb361c22893fccd153f2d87"

def once(s, old, new, label):
    n=s.count(old)
    if n!=1: raise RuntimeError(f"{label}: expected one anchor, got {n}")
    return s.replace(old,new,1)

def apply(root):
    sha=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    if sha!=PINNED: raise RuntimeError(f"Wrong pinned upstream FPGA {sha}")
    paths={k:root/p for k,p in {
        "bp":"rtl/denise_bitplanes.v","denise":"rtl/denise.v",
        "mini":"rtl/minimig.v","paula":"rtl/paula.v",
        "floppy":"rtl/paula_floppy.v"}.items()}
    d={k:p.read_text() for k,p in paths.items()}
    if "6'd0: bart_diag_word = 16'hB4AD;" not in d["floppy"]:
        raise RuntimeError("Apply v1/v2/v3/v6/v8 FPGA overlays first")

    # Denise's specialised OCS low-res/fmode0 pipeline has two ownership
    # modes. Count its actual use and related line setup transitions, not
    # speculative derived information. The hardware's original functions
    # and timing controls remain untouched.
    d["bp"]=once(d["bp"],
        "   output   [8:1] bpldata      // bitplane data out",
        "   output   [8:1] bpldata,     // bitplane data out\n"
        "   output wire [191:0] bart_v9_denise_diag // observation only",
        "Denise bitplane debug output")
    logic=r"""
// Bart v9 read-only Denise OCS state counters. 32-bit counters may wrap.
// These outputs never feed the pixel, shifter, DMA or OCS ownership FSM.
reg [31:0] bart_v9_bpl1_count;
reg [31:0] bart_v9_snapshot_count;
reg [31:0] bart_v9_pending_count;
reg [31:0] bart_v9_legacy_count;
reg [15:0] bart_v9_immediate_count;
reg [15:0] bart_v9_delayed_count;

always @(posedge clk) begin
  if (reset) begin
    bart_v9_bpl1_count <= 0;
    bart_v9_snapshot_count <= 0;
    bart_v9_pending_count <= 0;
    bart_v9_legacy_count <= 0;
    bart_v9_immediate_count <= 0;
    bart_v9_delayed_count <= 0;
  end else begin
    // Count original 7-MHz register load/strobes and actual OCS events.
    if (bpl1dat_now)
      bart_v9_bpl1_count <= bart_v9_bpl1_count + 32'd1;
    if (ocs_snapshot_event)
      bart_v9_snapshot_count <= bart_v9_snapshot_count + 32'd1;
    if (ocs_lores_fmode0 && hdiw && !blank) begin
      // Compare use of pending vs original stream during active display.
      if (use_ocs_pending_stream)
        bart_v9_pending_count <= bart_v9_pending_count + 32'd1;
      else
        bart_v9_legacy_count <= bart_v9_legacy_count + 32'd1;
    end
    if (ocs_immediate_ownership_now)
      bart_v9_immediate_count <= bart_v9_immediate_count + 16'd1;
    if (first_bpl1dat_of_line && ocs_delayed_ownership_now)
      bart_v9_delayed_count <= bart_v9_delayed_count + 16'd1;
  end
end

// bits 0..15: blank, hdiw, BPL1DAT now, phase, phase valid, pending
// stream selected, OCS lores, trigger, PF2/PF1 pending, delayed stage,
// ownership state, reserved.
wire [15:0] bart_v9_ocs_flags = {
  2'b00, ocs_ownership_state, ocs_delayed_fetch_stage,
  ocs_pending_pf1, ocs_pending_pf2, ocs_trigger,
  ocs_lores_fmode0, use_ocs_pending_stream,
  bitplane_fetch_phase_valid, bitplane_fetch_phase,
  bpl1dat_now, hdiw, blank
};

// 12 x 16-bit words, low word first per 32-bit count.
assign bart_v9_denise_diag = {
  bart_v9_delayed_count, bart_v9_immediate_count,
  bart_v9_legacy_count, bart_v9_pending_count,
  bart_v9_snapshot_count, bart_v9_bpl1_count,
  bplcon1, bart_v9_ocs_flags
};
"""
    d["bp"]=once(d["bp"],"\nendmodule\n","\n"+logic+"\nendmodule\n",
                 "Denise OCS counter logic")

    d["denise"]=once(d["denise"],
        "  output wire           shres           // shres",
        "  output wire           shres,          // shres\n"
        "  output wire [15:0] bart_v9_bplcon0,\n"
        "  output wire [191:0] bart_v9_denise_diag",
        "Denise observation output ports")
    d["denise"]=once(d["denise"],
        "assign hires    = bplcon0[15];",
        "assign bart_v9_bplcon0 = bplcon0;\n"
        "assign hires    = bplcon0[15];",
        "Denise BPLCON0 observation")
    d["denise"]=once(d["denise"],
        ".bpldata(bpldata_out)",
        ".bpldata(bpldata_out),\n"
        "  .bart_v9_denise_diag(bart_v9_denise_diag)",
        "Denise bitplane read-only port hookup")

    mini_logic=r"""
// Bart v9 graphics-only observations. The readout bus is used solely by
// the *on-demand* Paula E7 diagnostic SPI; it never controls the hardware.
wire [191:0] bart_v9_denise_diag;
wire [15:0] bart_v9_bplcon0;
reg [31:0] bart_v9_dma_count;
reg [20:1] bart_v9_last_dma_addr;
reg [15:0] bart_v9_last_dma_bus;
reg [15:0] bart_v9_mem_dma_writes;
always @(posedge clk) begin
  if (reset) begin
    bart_v9_dma_count <= 0;
    bart_v9_last_dma_addr <= 0;
    bart_v9_last_dma_bus <= 0;
    bart_v9_mem_dma_writes <= 0;
  end else if (clk7_en) begin
    if (bitplane_dma) begin
      bart_v9_dma_count <= bart_v9_dma_count + 32'd1;
      bart_v9_last_dma_addr <= dma_address_out;
      // Raw custom bus at the DMA slot, NOT guaranteed final Denise data.
      bart_v9_last_dma_bus <= custom_data_in;
    end
    // Agnus memory DMA write, from disk or Blitter (NOT Blitter-only).
    if (dbwe)
      bart_v9_mem_dma_writes <= bart_v9_mem_dma_writes + 16'd1;
  end
end

// The 19x16-bit SPI v9 slots 45..63, index 0..18 here.
// First 45 v1/v2/v3 observations remain intact and on-demand only.
wire [303:0] bart_v9_words;
assign bart_v9_words[  0+:16] = bart_v9_denise_diag[  0+:16]; // 45 OCS live flags
assign bart_v9_words[ 16+:16] = bart_v9_bplcon0;             // 46 BPLCON0
assign bart_v9_words[ 32+:16] = bart_v9_denise_diag[ 16+:16]; // 47 BPLCON1
assign bart_v9_words[ 48+:32] = bart_v9_dma_count;          // 48..49 DMA slots
assign bart_v9_words[ 80+:32] = bart_v9_denise_diag[ 32+:32]; // 50..51 BPL1DAT
assign bart_v9_words[112+:32] = bart_v9_denise_diag[ 64+:32]; // 52..53 snapshots
assign bart_v9_words[144+:32] = bart_v9_denise_diag[ 96+:32]; // 54..55 OCS pending
assign bart_v9_words[176+:32] = bart_v9_denise_diag[128+:32]; // 56..57 OCS legacy
assign bart_v9_words[208+:16] = bart_v9_denise_diag[160+:16]; // 58 immediate
assign bart_v9_words[224+:16] = bart_v9_denise_diag[176+:16]; // 59 delayed
assign bart_v9_words[240+:16] = bart_v9_last_dma_addr[16:1]; // 60 last addr lo
assign bart_v9_words[256+:16] = {12'd0,bart_v9_last_dma_addr[20:17]}; // 61 hi
assign bart_v9_words[272+:16] = bart_v9_last_dma_bus;       // 62 raw bus
assign bart_v9_words[288+:16] = bart_v9_mem_dma_writes;     // 63 DMA write count
"""
    d["mini"]=once(d["mini"],
        "wire [15:0] denise_data_out;",
        "wire [15:0] denise_data_out;\n"+mini_logic,
        "minimig graphics read-only taps")
    d["mini"]=once(d["mini"],
        ".shres(shres)\n",
        ".shres(shres),\n"
        "\t.bart_v9_bplcon0(bart_v9_bplcon0),\n"
        "\t.bart_v9_denise_diag(bart_v9_denise_diag)\n",
        "minimig Denise diagnostic hookup")

    # Forward a single graphics bus to the existing on-demand SPI endpoint,
    # rather than introducing any new MMIO, SPI reads during gameplay,
    # or moving clocks across domains.
    for name in ("paula","floppy"):
        d[name]=once(d[name],
            "\tinput [15:0] bart_fx_err,",
            "\tinput [15:0] bart_fx_err,\n"
            "\tinput [303:0] bart_v9_words,",
            f"{name} read-only graphics input")
    for name in ("mini","paula"):
        d[name]=once(d[name],
            "\t.bart_df_flags(bart_df_flags),",
            "\t.bart_df_flags(bart_df_flags),\n"
            "\t.bart_v9_words(bart_v9_words),",
            f"{name} debug word forwarding")
    d["floppy"]=once(d["floppy"],
        "6'd0: bart_diag_word = 16'hB4AD;",
        "6'd0: bart_diag_word = 16'hB4AE;",
        "v9 matched protocol signature")
    d["floppy"]=once(d["floppy"],
        "6'd1: bart_diag_word = 16'd8;",
        "6'd1: bart_diag_word = 16'd9;",
        "v9 protocol version")
    # All slots 45..63 are a matched single contiguous bank in the v6 FPGA
    # reader; v8 did not alter that bank, only the signal backing it.
    for idx in range(45,64):
        pat=rf"(?m)^([ \t]*)6'd{idx}: bart_diag_word = [^\n]+;$"
        new=f"6'd{idx}: bart_diag_word = bart_v9_words[{16*(idx-45)}+:16];"
        d["floppy"], n = re.subn(pat, lambda m: m.group(1)+new, d["floppy"])
        if n!=1:
            raise RuntimeError(f"FPGA SPI word {idx}: expected one anchor, got {n}")
    for name,path in paths.items():
        path.write_text(d[name])
    print("Applied read-only Bart v9 OCS bitplane/DMA probe to:")
    for path in paths.values(): print(" ", path)
    print("SPI B4AE version9, 64 slots, 0-44 preserved, 45-63 graphics.")
    print("No pixel generation, DMA arbitration, RAM, blitter or CPU control changed.")

if __name__=="__main__":
    if len(sys.argv)!=2:
        raise SystemExit("Usage: patch_bart_fpga_graphics_v9.py <pinned FPGA source>")
    apply(Path(sys.argv[1]).resolve())
