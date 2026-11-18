#!/usr/bin/env python3
"""Bart v12 passive Line-F first/last/prior history; apply after pinned v11."""
from pathlib import Path
import subprocess
import sys

PINNED = "7d5d3c2f685af4ce3eb361c22893fccd153f2d87"

def once(s, old, new, desc):
    if s.count(old) != 1:
        raise ValueError(f"{desc}: expected one anchor; got {s.count(old)}")
    return s.replace(old, new, 1)

def apply(root):
    rev = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    if rev != PINNED:
        raise ValueError(f"Wrong pinned upstream FPGA: {rev}")
    cpu_path = root / "rtl/cpu_wrapper.v"
    spi_path = root / "rtl/paula_floppy.v"
    cpu, spi = cpu_path.read_text(), spi_path.read_text()
    if "bart_v11_wait_target" not in (root / "rtl/minimig_m68k_bridge.v").read_text():
        raise ValueError("Apply v11 FPGA runtime bus wait patch first")
    if "16'hB4AD" not in spi or "16'd8" not in spi:
        raise ValueError("Expected v8 E7 signature and version")
    if "bart_linef_pulse_wire" not in cpu or "bart_last_fetch" not in cpu:
        raise ValueError("Expected v8 CPU Line-F tap and fetch recorder")

    begin = "// Bart v8. Freeze first asserted 68000 RESET output and first Line-F"
    end = "\nreg inflight;\n"
    a, b = cpu.find(begin), cpu.find(end, cpu.find(begin))
    if a < 0 or b < a or cpu.count(begin) != 1:
        raise ValueError("Cannot uniquely locate v8 recorder")
    replacement = """
// Bart v12: read-only Line-F sequencer recognition history.
// Edge qualify the existing v8 grp1LatchEn & enT3 & isLineF tap.
// The 64-word E7 transport's slots 45..63 are repurposed:
// addr0 first internal PC; addr1 last internal PC;
// addr2/3 last external fetch/previous external fetch;
// addr4 prior Line-F internal PC; addr5/6 prior event fetch/previous fetch;
// pc[15:0] last PSW, pc[31:16] last decoded Ir;
// psw prior decoded Ir; ird saturating 16-bit count;
// flags[0] any, [1] prior valid, [2] last OVL, [3] live OVL,
// [4] live CPU reset-out low, [5] reset-out low at last event,
// [6] count saturated.
// Sampled internal PC is NOT necessarily the architecturally retired PC.
// No functional CPU, DMA, RAM, or memory control signal is modified.
reg bart_v12_linef_d;
wire bart_v12_linef_edge = bart_linef_pulse_wire && !bart_v12_linef_d;
always @(posedge clk) begin
    if (!reset) begin
        bart_v12_linef_d <= 1'b0;
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
        bart_v12_linef_d <= bart_linef_pulse_wire;
        bart_df_flags[3] <= bart_dbg_overlay;
        bart_df_flags[4] <= ~reset_out_o;
        if (bart_v12_linef_edge) begin
            if (!bart_df_flags[0])
                bart_df_addr0 <= bart_pc_internal_wire;
            if (bart_df_flags[0]) begin
                bart_df_addr4 <= bart_df_addr1;
                bart_df_addr5 <= bart_df_addr2;
                bart_df_addr6 <= bart_df_addr3;
                bart_df_psw <= bart_df_pc[31:16];
            end
            bart_df_addr1 <= bart_pc_internal_wire;
            bart_df_addr2 <= bart_last_fetch;
            bart_df_addr3 <= bart_prev_fetch;
            bart_df_pc[15:0] <= bart_fx_psw_wire;
            bart_df_pc[31:16] <= bart_ir_wire;
            if (bart_df_ird != 16'hFFFF)
                bart_df_ird <= bart_df_ird + 16'd1;
            else
                bart_df_flags[6] <= 1'b1;
            bart_df_flags[0] <= 1'b1;
            bart_df_flags[1] <= bart_df_flags[0];
            bart_df_flags[2] <= bart_dbg_overlay;
            bart_df_flags[5] <= ~reset_out_o;
        end
    end
end
"""
    cpu = cpu[:a] + replacement + cpu[b:]
    spi = once(spi, "6'd0: bart_diag_word = 16'hB4AD;",
               "6'd0: bart_diag_word = 16'hB4AE;", "E7 signature")
    spi = once(spi, "6'd1: bart_diag_word = 16'd8;",
               "6'd1: bart_diag_word = 16'd12;", "E7 version")
    for slot in range(45, 64):
        if f"6'd{slot}: bart_diag_word =" not in spi:
            raise ValueError(f"Missing E7 output word {slot}")
    cpu_path.write_text(cpu)
    spi_path.write_text(spi)
    print("v12 FPGA Line-F first/last/prior event recorder, E7 B4AE version12.")
    print("Rick ERSY v4 and v11 E8 runtime bus waits are preserved.")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: patch_bart_fpga_linef_history_v12.py <FPGA root>")
    apply(Path(sys.argv[1]).resolve())
