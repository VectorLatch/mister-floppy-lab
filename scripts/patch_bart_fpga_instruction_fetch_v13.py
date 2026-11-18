#!/usr/bin/env python3
"""Bart v13: read-only CPU instruction-bus data at the latest Line-F event.

Apply only after pinned v11 waits + v12 Line-F history FPGA patches.
Do not alter CPU functional data input, clock, DTACK, or DMA control.
"""
from pathlib import Path
import subprocess
import sys

PINNED="7d5d3c2f685af4ce3eb361c22893fccd153f2d87"

def once(s, old, new, label):
    n=s.count(old)
    if n != 1: raise ValueError(f"{label}: one anchor required, got {n}")
    return s.replace(old,new,1)

def apply(root):
    rev=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    if rev != PINNED: raise ValueError(f"Unexpected pinned FPGA {rev}")
    cpu_p=root/"rtl/cpu_wrapper.v"
    fx_p=root/"rtl/fx68k/fx68k.sv"
    spi_p=root/"rtl/paula_floppy.v"
    bridge_p=root/"rtl/minimig_m68k_bridge.v"
    cpu=cpu_p.read_text()
    fx=fx_p.read_bytes().decode("utf-8")
    spi=spi_p.read_text()
    if "bart_v11_wait_target" not in bridge_p.read_text() or "bart_v12_linef_edge" not in cpu:
        raise ValueError("v13 must follow v11 live waits and v12 Line-F recorder")
    if "16'hB4AE" not in spi or "6'd1: bart_diag_word = 16'd12;" not in spi:
        raise ValueError("Expected v12 E7 signature and version")

    # Observe the *actual* internal fx68k Irc prefetch register, read-only.
    fx=once(fx,
        "\toutput wire [15:0] oDbgIr,\r\n",
        "\toutput wire [15:0] oDbgIr,\r\n"
        "\toutput wire [15:0] oDbgIrc,\r\n",
        "fx68k prefetch debug output")
    fx=once(fx,
        "\tassign oDbgIr = Ir;",
        "\tassign oDbgIr = Ir;\n\tassign oDbgIrc = Irc;",
        "fx68k Irc read-only tap")
    cpu=once(cpu,
        "wire [15:0] bart_ir_wire;",
        "wire [15:0] bart_ir_wire;\nwire [15:0] bart_irc_wire;",
        "CPU Irc tap wire")
    cpu=once(cpu,
        "\t.oDbgIr(bart_ir_wire),",
        "\t.oDbgIr(bart_ir_wire),\n\t.oDbgIrc(bart_irc_wire),",
        "CPU Irc tap connection")

    # v1 ar_fetch is the *start* of a program fetch. To sample data,
    # qualify the active fx68k program-space READ on its 68000 PHI2
    # with its effective RAM/chip acknowledge asserted.
    # Unlike a generic sample at AS assertion, cpu_din at the ack edge
    # is the actual 16-bit bus signal presented to fx68k.iEdb.
    #
    # This does NOT prove Irc consumed this sampled word; the separately
    # tapped Irc register provides complementary evidence.
    begin="// Bart v12: read-only Line-F sequencer recognition history."
    end="\nreg inflight;\n"
    a,b=cpu.find(begin),cpu.find(end,cpu.find(begin))
    if a<0 or b<a or cpu.count(begin)!=1:
        raise ValueError("Could not uniquely locate v12 snapshot logic")
    block="""
// Bart v13: passive acknowledged CPU program-fetch data history.
// Only the fx68k 68000 path is relevant for A500+ KS2 ECS.
// bus data = cpu_din, the unmodified signal wired to fx68k.iEdb.
// A read is sampled only once per acknowledged AS cycle on PHI2.
// The sample is a *bus* observation, not a proven retired opcode.
// Distinct debug Irc gives the actual internal prefetch register.
//
// Three most recent ACKed program-space READs are continuously kept;
// at each sequencer Line-F recognition the whole rolling window is
// frozen in the existing 64-word E7 on-demand transport (slots 45..63).
// Event 590 is expected to show a divergence at or around $0007087A.
// Note the internal PC is an *observed* fx68k register, not the 68k
// architecturally faulting PC.
//
// E7 words (low 16 first for all address pairs):
// 45:46 event internal PC
// 47:48 latest ACKed program read address
// 49:50 preceding ACKed program read address
// 51:52 third-most-recent ACKed program read address
// 53:54 live CPU bus address when Line-F recognized
// 55 latest ACKed bus data (iEdb input)
// 56 preceding ACKed bus data
// 57 third ACKed bus data
// 58 live iEdb when Line-F recognized (not necessarily accepted)
// 59 decoded Ir at Line-F
// 60 internal Irc prefetch register at Line-F
// 61 16-bit saturating Line-F recognition event count
// 62 prior Line-F decoded Ir
// 63 FLAGS: 0 any-event,1 prior-event,2-4 valid for fetch0-2,
// 5-7 corresponding RAM route, 8 AS asserted at Line-F,
// 9 effective DTACK asserted at Line-F,10 RW read,
// 11 program-space FC at Line-F,12 reset-out low,
// 13 event count saturated,14 overlay at Line-F,15 reserved.

wire bart_v13_dtack_n = ramsel ? ~ramready : chip_dtack;
wire bart_v13_ack_qual =
    (cpucfg[1:0] == 0) && !as_o && wr_o &&
    (fc_o[1:0] == 2'b10) && !bart_v13_dtack_n;
reg bart_v13_ack_d;
reg [31:0] bart_v13_addr0, bart_v13_addr1, bart_v13_addr2;
reg [15:0] bart_v13_data0, bart_v13_data1, bart_v13_data2;
reg [2:0] bart_v13_valid, bart_v13_ram;
reg bart_v13_linef_d;
wire bart_v13_linef_edge = bart_linef_pulse_wire && !bart_v13_linef_d;

always @(posedge clk) begin
    if (!reset) begin
        bart_v13_ack_d <= 1'b0;
        bart_v13_linef_d <= 1'b0;
        bart_v13_addr0 <= 32'd0; bart_v13_addr1 <= 32'd0;
        bart_v13_addr2 <= 32'd0;
        bart_v13_data0 <= 16'd0; bart_v13_data1 <= 16'd0;
        bart_v13_data2 <= 16'd0;
        bart_v13_valid <= 3'd0;
        bart_v13_ram <= 3'd0;
        bart_df_addr0 <= 32'd0; bart_df_addr1 <= 32'd0;
        bart_df_addr2 <= 32'd0; bart_df_addr3 <= 32'd0;
        bart_df_addr4 <= 32'd0; bart_df_addr5 <= 32'd0;
        bart_df_addr6 <= 32'd0;
        bart_df_pc <= 32'd0; bart_df_psw <= 16'd0;
        bart_df_ird <= 16'd0; bart_df_flags <= 16'd0;
    end else begin
        bart_v13_linef_d <= bart_linef_pulse_wire;
        if (ph2) begin
            bart_v13_ack_d <= bart_v13_ack_qual;
            if (bart_v13_ack_qual && !bart_v13_ack_d) begin
                bart_v13_addr2 <= bart_v13_addr1;
                bart_v13_addr1 <= bart_v13_addr0;
                bart_v13_addr0 <= {8'd0,cpu_addr_o,1'b0};
                bart_v13_data2 <= bart_v13_data1;
                bart_v13_data1 <= bart_v13_data0;
                bart_v13_data0 <= cpu_din;
                bart_v13_valid <= {bart_v13_valid[1:0],1'b1};
                bart_v13_ram <= {bart_v13_ram[1:0],ramsel};
            end
        end
        if (bart_v13_linef_edge) begin
            bart_df_addr0 <= bart_pc_internal_wire;
            bart_df_addr1 <= bart_v13_addr0;
            bart_df_addr2 <= bart_v13_addr1;
            bart_df_addr3 <= bart_v13_addr2;
            bart_df_addr4 <= {8'd0,cpu_addr_o,1'b0};
            bart_df_addr5 <= {bart_v13_data1,bart_v13_data0};
            bart_df_addr6 <= {cpu_din,bart_v13_data2};
            bart_df_pc <= {bart_irc_wire,bart_ir_wire};
            bart_df_ird <= bart_df_pc[15:0];
            if (bart_df_psw != 16'hFFFF)
                bart_df_psw <= bart_df_psw + 16'd1;
            bart_df_flags <= {
                1'b0, bart_dbg_overlay, (bart_df_psw==16'hFFFF),
                ~reset_out_o, (fc_o[1:0]==2'b10), wr_o,
                ~bart_v13_dtack_n, ~as_o,
                bart_v13_ram[2],bart_v13_ram[1],bart_v13_ram[0],
                bart_v13_valid[2],bart_v13_valid[1],bart_v13_valid[0],
                bart_df_flags[0],1'b1
            };
        end
    end
end
"""
    cpu=cpu[:a]+block+cpu[b:]
    spi=once(spi,"6'd0: bart_diag_word = 16'hB4AE;",
                "6'd0: bart_diag_word = 16'hB4AF;","v13 SPI signature")
    spi=once(spi,"6'd1: bart_diag_word = 16'd12;",
                "6'd1: bart_diag_word = 16'd13;","v13 SPI version")
    for slot in range(45,64):
        if f"6'd{slot}: bart_diag_word =" not in spi:
            raise ValueError(f"Missing word slot {slot}")
    fx_p.write_bytes(fx.encode("utf-8"))
    cpu_p.write_text(cpu)
    spi_p.write_text(spi)
    print("Bart v13: 3 acknowledged fx68k program-read address/data pairs + internal Irc/Ir.")
    print("E7 signature B4AF version 13; v11 E8 live wait knobs and Rick ERSY fix retained.")

if __name__=="__main__":
    if len(sys.argv)!=2:
        raise SystemExit("Usage: patch_bart_fpga_instruction_fetch_v13.py <pinned FPGA root>")
    apply(Path(sys.argv[1]).resolve())
