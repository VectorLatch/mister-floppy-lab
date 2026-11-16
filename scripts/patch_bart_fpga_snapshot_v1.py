#!/usr/bin/env python3
"""Read-only Bart snapshot FPGA patch for locked Minimig 2026-11-09 sources.

Apply after the proven Rick ERSY v4 one-line patch. No datapath or disk
semantics changes. Snapshot registers are only read with SPI E7xx command.
"""
from pathlib import Path
import subprocess
import sys

PINNED = "7d5d3c2f685af4ce3eb361c22893fccd153f2d87"

def once(s, before, after, name):
    n = s.count(before)
    if n != 1:
        raise RuntimeError(f"{name}: expected exactly one source anchor; found {n}")
    return s.replace(before, after, 1)

def patch(root):
    actual = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual != PINNED:
        raise RuntimeError(f"wrong upstream FPGA revision: {actual}")
    paths = {
        k: root / p for k, p in {
            "top": "Minimig.sv",
            "cpu": "rtl/cpu_wrapper.v",
            "minimig": "rtl/minimig.v",
            "paula": "rtl/paula.v",
            "floppy": "rtl/paula_floppy.v",
        }.items()
    }
    d = {k: p.read_text() for k, p in paths.items()}

    # Two 68k CPU implementations: TG68K busstate=0 is fetch, fx68k FC
    # function code ending in 10 is program space. No generic data address
    # is labelled 'PC'. 'last_fetch' is a *qualified fetch bus address*.
    d["cpu"] = once(d["cpu"],
        "\toutput reg        ar_fetch = 0,  // an instruction fetch outside $A80000-$AFFFFF (one clock)",
        "\toutput reg        ar_fetch = 0,  // an instruction fetch outside $A80000-$AFFFFF (one clock)\n"
        "\toutput reg [31:0] bart_fetch_count,\n"
        "\toutput reg [31:0] bart_last_fetch,\n"
        "\toutput reg [31:0] bart_prev_fetch,",
        "CPU output ports")
    d["cpu"] = once(d["cpu"], "\nreg inflight;\n",
        """
// Bart diagnostic only. Both paths qualify program fetch, not arbitrary bus
// address. TG68K: 0=code fetch; fx68k: FC[1:0]=2 is program space.
// This samples the initiating bus address, *not* internal microcode PC.
wire bart_fetch_evt = (cpucfg[1:0] != 0)
    ? (clkena_p_throttled && cpustate_p == 2'd0 && !skip_rd && !req_gate)
    : (as_o_d && !as_o && fc_o[1:0] == 2'b10);
wire [31:0] bart_fetch_addr = (cpucfg[1:0] != 0)
    ? cpu_addr_m : {8'd0, cpu_addr_o, 1'b0};
always @(posedge clk) begin
    if (~reset) begin
        bart_fetch_count <= 0;
        bart_last_fetch <= 0;
        bart_prev_fetch <= 0;
    end else if (bart_fetch_evt) begin
        bart_fetch_count <= bart_fetch_count + 32'd1;
        bart_prev_fetch <= bart_last_fetch;
        bart_last_fetch <= bart_fetch_addr;
    end
end

reg inflight;
""", "CPU fetch tap")

    # Top-level wires and both consumers of the ar_fetch signal.
    d["top"] = once(d["top"], "cpu_wrapper cpu_wrapper\n",
        "wire [31:0] bart_fetch_count;\n"
        "wire [31:0] bart_last_fetch;\n"
        "wire [31:0] bart_prev_fetch;\n\n"
        "cpu_wrapper cpu_wrapper\n", "top diagnostic wires")
    needle = "\t.ar_fetch     (ar_fetch        ),\n"
    if d["top"].count(needle) != 2:
        raise RuntimeError("Expected exactly two ar_fetch hookups in top")
    d["top"] = d["top"].replace(needle,
        needle +
        "\t.bart_fetch_count(bart_fetch_count),\n"
        "\t.bart_last_fetch(bart_last_fetch),\n"
        "\t.bart_prev_fetch(bart_prev_fetch),\n")

    d["minimig"] = once(d["minimig"],
        "\tinput         ar_fetch,    // the CPU fetched an instruction outside $A80000-$AFFFFF",
        "\tinput         ar_fetch,    // the CPU fetched an instruction outside $A80000-$AFFFFF\n"
        "\tinput [31:0] bart_fetch_count,\n"
        "\tinput [31:0] bart_last_fetch,\n"
        "\tinput [31:0] bart_prev_fetch,",
        "minimig top input ports")
    d["minimig"] = once(d["minimig"],
        "\t.IO_DOUT(IO_DOUT_PAULA),\n",
        "\t.IO_DOUT(IO_DOUT_PAULA),\n"
        "\t.bart_fetch_count(bart_fetch_count),\n"
        "\t.bart_last_fetch(bart_last_fetch),\n"
        "\t.bart_prev_fetch(bart_prev_fetch),\n",
        "minimig Paula hookups")

    d["paula"] = once(d["paula"],
        "\toutput [15:0] IO_DOUT,\n",
        "\toutput [15:0] IO_DOUT,\n"
        "\tinput [31:0] bart_fetch_count,\n"
        "\tinput [31:0] bart_last_fetch,\n"
        "\tinput [31:0] bart_prev_fetch,\n",
        "Paula module input ports")
    d["paula"] = once(d["paula"],
        "\t.IO_DOUT(IO_DOUT),\n\t.fdd_led(fdd_led),",
        "\t.IO_DOUT(IO_DOUT),\n"
        "\t.bart_fetch_count(bart_fetch_count),\n"
        "\t.bart_last_fetch(bart_last_fetch),\n"
        "\t.bart_prev_fetch(bart_prev_fetch),\n"
        "\t.fdd_led(fdd_led),",
        "Paula floppy hookups")

    d["floppy"] = once(d["floppy"],
        "\toutput reg [15:0] IO_DOUT,\n",
        "\toutput reg [15:0] IO_DOUT,\n"
        "\tinput [31:0] bart_fetch_count,\n"
        "\tinput [31:0] bart_last_fetch,\n"
        "\tinput [31:0] bart_prev_fetch,\n",
        "Floppy module input ports")

    # Old v3 experimental source proved 0xE7xx can be decoded separately
    # from floppy command 0x0xxx. Main only issues it on demand.
    d["floppy"] = once(d["floppy"],
        "reg [15:0] rx_data;\t//received data from HPS\n"
        "reg [15:0] tx_data;\t//data to be send to HPS",
        "reg [15:0] rx_data;\t//received data from HPS\n"
        "reg [15:0] tx_data;\t//data to be send to HPS\n"
        "reg bart_diag_command;\n"
        "reg [5:0] bart_diag_reg;\n"
        "reg [15:0] bart_diag_word;\n"
        "always @(posedge clk) begin\n"
        "    if (clk7_en) begin\n"
        "        if (reset || !IO_ENA) bart_diag_command <= 0;\n"
        "        else if (stb7 && cmd_cnt == 2'd0) begin\n"
        "            bart_diag_command <= (rx_data[15:8] == 8'hE7);\n"
        "            bart_diag_reg <= rx_data[5:0];\n"
        "        end\n"
        "    end\n"
        "end",
        "diagnostic SPI decode")

    d["floppy"] = once(d["floppy"],
        "//transmit data multiplexer\nalways @(*) begin\n"
        "\tcasex ({cmd_cnt, cmd_fdd, hostRead,  sel_external ? 1'b0 : trackwr })",
        "//transmit data multiplexer\nalways @(*) begin\n"
        "    if (bart_diag_command && cmd_cnt != 2'd0)\n"
        "        tx_data = bart_diag_word;\n"
        "    else\n"
        "\tcasex ({cmd_cnt, cmd_fdd, hostRead,  sel_external ? 1'b0 : trackwr })",
        "read-only SPI response mux")

    # Only 8 independent small counters, reset with the core; the readout
    # is combinatorial and does not perturb the Amiga disk-controller path.
    code = r'''
// Bart standalone-IPF read-only snapshot register bank.
// Signature B4A6 / version 1; the original SPI protocol is unchanged.
reg [31:0] bart_dma_arms;
reg [31:0] bart_dma_done;
reg [31:0] bart_sync_irqs;
reg [31:0] bart_sync_events;
reg [31:0] bart_dmal_cycles;
reg [31:0] bart_len_writes;
reg [31:0] bart_active_empty_cycles;
reg [31:0] bart_read_cycles;
reg bart_dmaen_prev;
reg bart_syncint_prev;
reg bart_extsync_prev;
always @(posedge clk) if (clk7_en) begin
    if (reset) begin
        bart_dma_arms <= 0;
        bart_dma_done <= 0;
        bart_sync_irqs <= 0;
        bart_sync_events <= 0;
        bart_dmal_cycles <= 0;
        bart_len_writes <= 0;
        bart_active_empty_cycles <= 0;
        bart_read_cycles <= 0;
        bart_dmaen_prev <= 0;
        bart_syncint_prev <= 0;
        bart_extsync_prev <= 0;
    end else begin
        bart_dmaen_prev <= dmaen;
        bart_syncint_prev <= syncint;
        bart_extsync_prev <= ext_floppy_sync;
        if (dmaen && !bart_dmaen_prev) bart_dma_arms <= bart_dma_arms + 32'd1;
        if (blckint) bart_dma_done <= bart_dma_done + 32'd1;
        if (syncint && !bart_syncint_prev) bart_sync_irqs <= bart_sync_irqs + 32'd1;
        if (ext_floppy_sync && !bart_extsync_prev) bart_sync_events <= bart_sync_events + 32'd1;
        if (flux_inuse && dmal) bart_dmal_cycles <= bart_dmal_cycles + 32'd1;
        if (reg_address_in[8:1] == DSKLEN[8:1]) bart_len_writes <= bart_len_writes + 32'd1;
        if (flux_inuse && dskstate == DISKDMA_ACTIVE && selected_fifo_empty)
            bart_active_empty_cycles <= bart_active_empty_cycles + 32'd1;
        if (flux_inuse && trackrd) bart_read_cycles <= bart_read_cycles + 32'd1;
    end
end

wire [15:0] bart_status = {
    flux_inuse, virtualFloppyMode, wordsync, dmaen, dmaon,
    trackrd, trackrdok, selected_fifo_empty, lenzero,
    fifo_wr_delay, blckint, syncint, ext_floppy_sync,
    dskstate[1:0], enable
};
always @(*) begin
    case (bart_diag_reg)
        6'd0: bart_diag_word = 16'hB4A6;
        6'd1: bart_diag_word = 16'd1;
        6'd2: bart_diag_word = bart_status;
        6'd3: bart_diag_word = dsksync;
        6'd4: bart_diag_word = {dmaen, dsklen[14:0]};
        6'd5: bart_diag_word = {8'd0, track};
        6'd6: bart_diag_word = {4'd0, fifo_cnt};
        6'd7: bart_diag_word = {14'd0, dskstate};
        6'd8: bart_diag_word = bart_fetch_count[15:0];
        6'd9: bart_diag_word = bart_fetch_count[31:16];
        6'd10: bart_diag_word = bart_last_fetch[15:0];
        6'd11: bart_diag_word = bart_last_fetch[31:16];
        6'd12: bart_diag_word = bart_prev_fetch[15:0];
        6'd13: bart_diag_word = bart_prev_fetch[31:16];
        6'd14: bart_diag_word = bart_dma_arms[15:0];
        6'd15: bart_diag_word = bart_dma_arms[31:16];
        6'd16: bart_diag_word = bart_dma_done[15:0];
        6'd17: bart_diag_word = bart_dma_done[31:16];
        6'd18: bart_diag_word = bart_sync_irqs[15:0];
        6'd19: bart_diag_word = bart_sync_irqs[31:16];
        6'd20: bart_diag_word = bart_sync_events[15:0];
        6'd21: bart_diag_word = bart_sync_events[31:16];
        6'd22: bart_diag_word = bart_dmal_cycles[15:0];
        6'd23: bart_diag_word = bart_dmal_cycles[31:16];
        6'd24: bart_diag_word = bart_len_writes[15:0];
        6'd25: bart_diag_word = bart_len_writes[31:16];
        6'd26: bart_diag_word = bart_active_empty_cycles[15:0];
        6'd27: bart_diag_word = bart_active_empty_cycles[31:16];
        6'd28: bart_diag_word = bart_read_cycles[15:0];
        6'd29: bart_diag_word = bart_read_cycles[31:16];
        default: bart_diag_word = 16'hDEAD;
    endcase
end
'''
    d["floppy"] = once(d["floppy"], "\nendmodule\n",
                        "\n"+code+"\nendmodule\n", "Floppy snapshot register bank")

    for k,p in paths.items():
        p.write_text(d[k])
    print("Read-only Bart CPU/Paula FPGA snapshot patch written:")
    for p in paths.values(): print(" ",p)

if __name__=="__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: patch_bart_fpga_snapshot_v1.py <pinned FPGA source directory>")
    patch(Path(sys.argv[1]))
