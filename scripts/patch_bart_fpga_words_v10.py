#!/usr/bin/env python3
"""v10: ECS-aware read-only two-scanline bitplane word + first DMA pointer trace.

Apply after v1/v2/v3/v6/v8/v9 patches. Capture lines $80 and $E0 once
per frame at the first BPL1DAT latch; running 32-bit per-line fingerprints
cover BPL1DAT..BPL4DAT words. The Agnus first-BPL1DMA pointer is separately
sampled and may NOT correspond cycle-for-cycle to Denise's latched data:
the memory bus has a pipeline. No functional datapath or timing logic altered.
"""
from pathlib import Path
import subprocess
import sys

PINNED="7d5d3c2f685af4ce3eb361c22893fccd153f2d87"

def once(s,before,after,label):
    n=s.count(before)
    if n!=1: raise RuntimeError(f"{label}: expected one anchor, found {n}")
    return s.replace(before,after,1)

def apply(root):
    sha=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    if sha!=PINNED: raise RuntimeError(f"Wrong pinned FPGA SHA {sha}")
    paths={k:root/p for k,p in {
        "agnus":"rtl/agnus.v","bp":"rtl/denise_bitplanes.v",
        "denise":"rtl/denise.v","mini":"rtl/minimig.v",
        "paula":"rtl/paula.v","floppy":"rtl/paula_floppy.v"}.items()}
    d={k:p.read_text() for k,p in paths.items()}
    if "16'hB4AE" not in d["floppy"] or "bart_v9_words" not in d["mini"]:
        raise RuntimeError("Apply exact v9 diagnostic first")
    d["agnus"]=once(d["agnus"],
        "input         floppy_speed     // allocates refresh slots for disk DMA",
        "input         floppy_speed,    // allocates refresh slots for disk DMA\n"
        "output wire [10:0] bart_v10_beam_vpos // read-only Agnus beam line",
        "Agnus vpos debug port")
    d["agnus"]=once(d["agnus"],
        "assign reg_address_out = reg_address;",
        "assign reg_address_out = reg_address;\n"
        "assign bart_v10_beam_vpos = vpos;",
        "Agnus read-only beam tap")

    d["bp"]=once(d["bp"],
        "   output wire [191:0] bart_v9_denise_diag // observation only",
        "   output wire [191:0] bart_v9_denise_diag, // observation only\n"
        "   input wire [10:0] bart_v10_beam_vpos,\n"
        "   output wire [223:0] bart_v10_capture",
        "bitplane probe ports")
    logic=r"""
// Bart v10 read-only ECS/OCS low-res diagnostics: actual words delivered to
// Denise bitplane holding registers on the same clock edge as their load.
// An independently captured Agnus DMA *pointer* is not address-data aligned.
reg [3:0] bart_v10_sel;
reg [63:0] bart_v10_a_data, bart_v10_b_data;
reg [31:0] bart_v10_a_hash, bart_v10_b_hash;
reg [15:0] bart_v10_a_hits, bart_v10_b_hits;
reg bart_v10_a_seen, bart_v10_b_seen;
wire bart_v10_a_line = bart_v10_beam_vpos == 11'h080;
wire bart_v10_b_line = bart_v10_beam_vpos == 11'h0E0;

// The original bpl1..4 holding registers consume 'data16' on the phase
// following a BPLxDAT bus strobe. This independent selector tracks that phase.
always @(posedge clk) begin
  if (reset)
    bart_v10_sel <= 4'b0;
  else if (clk7_en) begin
    case (reg_address_in[8:1])
      BPL1DAT[8:1]: bart_v10_sel <= 4'b0001;
      BPL2DAT[8:1]: bart_v10_sel <= 4'b0010;
      BPL3DAT[8:1]: bart_v10_sel <= 4'b0100;
      BPL4DAT[8:1]: bart_v10_sel <= 4'b1000;
      default:      bart_v10_sel <= 4'b0000;
    endcase
  end
end

always @(posedge clk) begin
  if (reset) begin
    bart_v10_a_data <= 0; bart_v10_b_data <= 0;
    bart_v10_a_hash <= 0; bart_v10_b_hash <= 0;
    bart_v10_a_hits <= 0; bart_v10_b_hits <= 0;
    bart_v10_a_seen <= 0; bart_v10_b_seen <= 0;
  end else begin
    if (clk7_en && strhor) begin
      if (bart_v10_a_line) begin
        bart_v10_a_seen <= 0;
        bart_v10_a_hash <= 32'hA5000080;
      end
      if (bart_v10_b_line) begin
        bart_v10_b_seen <= 0;
        bart_v10_b_hash <= 32'hA50000E0;
      end
    end

    if (clk7n_en && (bart_v10_sel != 4'b0)) begin
      // Rotate/XOR fingerprint is a correlation marker, not a formal CRC.
      if (bart_v10_a_line) begin
        bart_v10_a_hash <= {bart_v10_a_hash[26:0],bart_v10_a_hash[31:27]}
                          ^ {16'd0,data16} ^ {28'd0,bart_v10_sel};
        if (bart_v10_sel[0] && !bart_v10_a_seen) begin
          bart_v10_a_data <= {bpl4dat[63:48],bpl3dat[63:48],
                              bpl2dat[63:48],data16};
          bart_v10_a_seen <= 1;
          bart_v10_a_hits <= bart_v10_a_hits + 16'd1;
        end
      end
      if (bart_v10_b_line) begin
        bart_v10_b_hash <= {bart_v10_b_hash[26:0],bart_v10_b_hash[31:27]}
                          ^ {16'd0,data16} ^ {28'd0,bart_v10_sel};
        if (bart_v10_sel[0] && !bart_v10_b_seen) begin
          bart_v10_b_data <= {bpl4dat[63:48],bpl3dat[63:48],
                              bpl2dat[63:48],data16};
          bart_v10_b_seen <= 1;
          bart_v10_b_hits <= bart_v10_b_hits + 16'd1;
        end
      end
    end
  end
end

assign bart_v10_capture = {
  bart_v10_b_hits, bart_v10_a_hits,
  bart_v10_b_hash, bart_v10_a_hash,
  bart_v10_b_data, bart_v10_a_data
};
"""
    d["bp"]=once(d["bp"],"\nendmodule\n","\n"+logic+"\nendmodule\n","bitplane capture")
    d["denise"]=once(d["denise"],
        "  output wire [191:0] bart_v9_denise_diag",
        "  output wire [191:0] bart_v9_denise_diag,\n"
        "  input wire [10:0] bart_v10_beam_vpos,\n"
        "  output wire [223:0] bart_v10_capture",
        "Denise debug ports")
    d["denise"]=once(d["denise"],
        ".bart_v9_denise_diag(bart_v9_denise_diag)",
        ".bart_v9_denise_diag(bart_v9_denise_diag),\n"
        "  .bart_v10_beam_vpos(bart_v10_beam_vpos),\n"
        "  .bart_v10_capture(bart_v10_capture)",
        "Denise to bitplanes")
    d["mini"]=once(d["mini"],
        "wire [191:0] bart_v9_denise_diag;",
        "wire [191:0] bart_v9_denise_diag;\n"
        "wire [10:0] bart_v10_beam_vpos;\n"
        "wire [223:0] bart_v10_capture;\n"
        "reg [20:1] bart_v10_a_ptr, bart_v10_b_ptr;\n"
        "reg bart_v10_a_ptr_seen, bart_v10_b_ptr_seen;\n"
        "reg [10:0] bart_v10_prev_vpos;\n",
        "Minimig capture wires")
    d["mini"]=once(d["mini"],
        ".floppy_speed(floppy_speed)\n",
        ".floppy_speed(floppy_speed),\n"
        "\t.bart_v10_beam_vpos(bart_v10_beam_vpos)\n",
        "Minimig Agnus port")
    d["mini"]=once(d["mini"],
        "\t.bart_v9_denise_diag(bart_v9_denise_diag)\n",
        "\t.bart_v9_denise_diag(bart_v9_denise_diag),\n"
        "\t.bart_v10_beam_vpos(bart_v10_beam_vpos),\n"
        "\t.bart_v10_capture(bart_v10_capture)\n",
        "Minimig Denise port")
    mini=r"""
// First BPL1 DMA pointer on two beam lines, separately from Denise data.
// Captures prior-to-increment Agnus word address (not a guaranteed word/data
// pair; the bitplane memory read follows pipelined RAM/Denise bus clocks).
always @(posedge clk) begin
  if (reset) begin
    bart_v10_a_ptr <= 0; bart_v10_b_ptr <= 0;
    bart_v10_a_ptr_seen <= 0; bart_v10_b_ptr_seen <= 0;
    bart_v10_prev_vpos <= 0;
  end else if (clk7_en) begin
    bart_v10_prev_vpos <= bart_v10_beam_vpos;
    if (bart_v10_prev_vpos != bart_v10_beam_vpos) begin
      if (bart_v10_beam_vpos == 11'h080) bart_v10_a_ptr_seen <= 0;
      if (bart_v10_beam_vpos == 11'h0E0) bart_v10_b_ptr_seen <= 0;
    end
    if (bitplane_dma && (reg_address == 8'h88)) begin
      if (bart_v10_beam_vpos == 11'h080 && !bart_v10_a_ptr_seen) begin
        bart_v10_a_ptr <= dma_address_out;
        bart_v10_a_ptr_seen <= 1;
      end
      if (bart_v10_beam_vpos == 11'h0E0 && !bart_v10_b_ptr_seen) begin
        bart_v10_b_ptr <= dma_address_out;
        bart_v10_b_ptr_seen <= 1;
      end
    end
  end
end

// 19 x 16-bit SPI readout words 45..63. Original CPU/Paula 0..44 preserved.
// Sample words are ACTUAL data16 latched into Denise BPL1DAT; planes 2..4
// reflect their existing holding registers at that clock edge.
wire [303:0] bart_v10_words;
assign bart_v10_words[  0+:16] = {4'd0, (|chipset_config[4:3]), chipset_config[4],
  bart_v10_a_ptr_seen, bart_v10_b_ptr_seen,
  bart_v10_b_ptr[20:17], bart_v10_a_ptr[20:17]}; // 45
assign bart_v10_words[ 16+:16] = bart_v10_capture[192+:16]; // 46 A hits
assign bart_v10_words[ 32+:16] = bart_v10_capture[208+:16]; // 47 B hits
assign bart_v10_words[ 48+:32] = bart_v10_capture[128+:32]; // 48..49 A hash
assign bart_v10_words[ 80+:32] = bart_v10_capture[160+:32]; // 50..51 B hash
assign bart_v10_words[112+:64] = bart_v10_capture[  0+:64]; // 52..55 A data
assign bart_v10_words[176+:64] = bart_v10_capture[ 64+:64]; // 56..59 B data
assign bart_v10_words[240+:16] = bart_v10_a_ptr[16:1];      // 60 A addr lo
assign bart_v10_words[256+:16] = bart_v10_b_ptr[16:1];      // 61 B addr lo
assign bart_v10_words[272+:16] = bart_v9_bplcon0;           // 62 mode
assign bart_v10_words[288+:16] = bart_v9_denise_diag[16+:16]; // 63 scroll
"""
    d["mini"]=once(d["mini"],
        "// The 19x16-bit SPI v9 slots 45..63, index 0..18 here.",
        mini+"\n// The 19x16-bit SPI v9 slots 45..63, index 0..18 here.",
        "Mini v10 trace block")
    for name in ("paula","floppy"):
        d[name]=once(d[name],
            "\tinput [303:0] bart_v9_words,",
            "\tinput [303:0] bart_v9_words,\n"
            "\tinput [303:0] bart_v10_words,",
            f"{name} trace port")
    for name in ("mini","paula"):
        d[name]=once(d[name],
            "\t.bart_v9_words(bart_v9_words),",
            "\t.bart_v9_words(bart_v9_words),\n"
            "\t.bart_v10_words(bart_v10_words),",
            f"{name} forwarded capture bus")
    d["floppy"]=once(d["floppy"],
        "6'd0: bart_diag_word = 16'hB4AE;",
        "6'd0: bart_diag_word = 16'hB4AF;",
        "new snapshot signature")
    d["floppy"]=once(d["floppy"],
        "6'd1: bart_diag_word = 16'd9;",
        "6'd1: bart_diag_word = 16'd10;",
        "new snapshot version")
    for idx in range(45,64):
        old=f"6'd{idx}: bart_diag_word = bart_v9_words[{16*(idx-45)}+:16];"
        new=f"6'd{idx}: bart_diag_word = bart_v10_words[{16*(idx-45)}+:16];"
        d["floppy"]=once(d["floppy"],old,new,f"v10 SPI index {idx}")
    for name,path in paths.items(): path.write_text(d[name])
    print("Applied Bart v10 ECS-aware two-line bitplane word/fingerprint/pointer probe.")
    print("E7xx signature B4AF version10, lines $080/$0E0, 19 graphics slots.")
    print("Does not change any graphics/CPU/floppy functional path.")

if __name__=="__main__":
    if len(sys.argv)!=2: raise SystemExit("Usage: patch_bart_fpga_words_v10.py <pinned FPGA root>")
    apply(Path(sys.argv[1]).resolve())
