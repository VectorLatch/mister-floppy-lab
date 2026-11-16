#!/usr/bin/env python3
"""Bart CPU bus state snapshot v2 overlay (AFTER Bart snapshot v1 patch).

No changes to CPU execution, disk DMA, memory, clock, reset, or interrupts.
Taps the 68000 bus interface, records two additional fetch addresses,
and provides a non-fetch bus activity counter. Readout is on-demand
through the already-established experimental E7xx FPGA SPI diagnostics.
"""
from pathlib import Path
import subprocess
import sys

PINNED = "7d5d3c2f685af4ce3eb361c22893fccd153f2d87"

def replace_one(source, old, new, label):
    count = source.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected one source anchor, found {count}")
    return source.replace(old, new, 1)

def apply(root):
    sha = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    if sha != PINNED:
        raise ValueError(f"Wrong official FPGA source commit: {sha}")
    paths = {
        "cpu": root / "rtl/cpu_wrapper.v",
        "top": root / "Minimig.sv",
        "minimig": root / "rtl/minimig.v",
        "paula": root / "rtl/paula.v",
        "floppy": root / "rtl/paula_floppy.v",
    }
    d = {k: p.read_text() for k, p in paths.items()}
    if "bart_fetch_count" not in d["cpu"] or "16'hB4A6" not in d["floppy"]:
        raise ValueError("Apply original Bart FPGA snapshot v1 first")

    ports = (
        "\toutput reg [31:0] bart_raw_bus_addr,\n"
        "\toutput reg [15:0] bart_bus_flags,\n"
        "\toutput reg [15:0] bart_bus_detail,\n"
        "\toutput reg [23:0] bart_fetch_hist2,\n"
        "\toutput reg [23:0] bart_fetch_hist3,\n"
        "\toutput reg [31:0] bart_bus_events,\n"
    )
    d["cpu"] = replace_one(
        d["cpu"],
        "\toutput reg [31:0] bart_prev_fetch,",
        "\toutput reg [31:0] bart_prev_fetch,\n" + ports.rstrip("\n"),
        "cpu_wrapper CPU v2 tap ports"
    )
    # The primary CPU ports continue to come from the v1 source.
    # Do not infer a PC from a raw memory bus address.
    cpu_logic = r'''
// Bart V2 read-only CPU status. Sample at the base 28 MHz clock only;
// bus interface values and output registers do not drive any CPU controls.
always @(posedge clk) begin
    bart_raw_bus_addr <= cpu_addr;
    // [15] reset input (active high for fx68k extReset inversion)
    // [14] reset_out, [13] non-fx CPU selected,
    // [12] fx ASn, [11] chip ASn, [10] chip DTACKn,
    // [9] RAM select, [8] RAM ready, [7] CPU request,
    // [6] TG bus clock enable, [5] request gate,
    // [4] chip ready, [3] fx R/W, [2:0] fx function code.
    bart_bus_flags <= {
        reset, reset_out, (cpucfg[1:0] != 0), as_o,
        chip_as, chip_dtack, ramsel, ramready,
        cpu_req, clkena_p_throttled, req_gate, chipready,
        wr_o, fc_o
    };
    // [15:14] zero; [13:11] chip interrupt level lines (active low),
    // [10:8] fx function code, [7:6] TG busstate,
    // [5:4] selected CPU busstate, [3:2] ph1/ph2,
    // [1:0] external chip/RAM fast completion signals.
    bart_bus_detail <= {
        2'b00, chip_ipl, fc_o, cpustate_p,
        cpustate, ph1, ph2, fastchip_ready, fastchip_selack
    };
end
// Only two additional 24-bit history taps beyond the existing latest
// and previous fetches; historical 68000 addresses are 24-bit.
always @(posedge clk) begin
    if (~reset) begin
        bart_fetch_hist2 <= 0;
        bart_fetch_hist3 <= 0;
        bart_bus_events <= 0;
    end else begin
        if (bart_fetch_evt) begin
            bart_fetch_hist3 <= bart_fetch_hist2;
            bart_fetch_hist2 <= bart_prev_fetch[23:0];
        end
        // fx68k: falling address strobe qualifies a bus-cycle start.
        // TG68K: accepted CPU memory request cycles (not instructions).
        if ((cpucfg[1:0] == 0)
            ? (as_o_d && !as_o)
            : (clkena_p_throttled && cpu_req && !req_gate))
            bart_bus_events <= bart_bus_events + 32'd1;
    end
end
'''
    d["cpu"] = replace_one(
        d["cpu"], "\nreg inflight;\n",
        "\n" + cpu_logic + "\nreg inflight;\n",
        "CPU bus instrumentation"
    )

    wires = (
        "wire [31:0] bart_raw_bus_addr;\n"
        "wire [15:0] bart_bus_flags;\n"
        "wire [15:0] bart_bus_detail;\n"
        "wire [23:0] bart_fetch_hist2;\n"
        "wire [23:0] bart_fetch_hist3;\n"
        "wire [31:0] bart_bus_events;\n"
    )
    d["top"] = replace_one(
        d["top"], "cpu_wrapper cpu_wrapper\n",
        wires + "\ncpu_wrapper cpu_wrapper\n", "top-level read-only CPU buses"
    )
    # v1 adds these ports to BOTH CPU and Minimig instances in top:
    # use exact endpoint-specific anchor, not fragile whitespace patterns.
    old = "\t.bart_prev_fetch(bart_prev_fetch),\n"
    count = d["top"].count(old)
    if count != 2:
        raise ValueError(f"Expected exactly two top bart_prev_fetch hookups, found {count}")
    hooks = (
        "\t.bart_raw_bus_addr(bart_raw_bus_addr),\n"
        "\t.bart_bus_flags(bart_bus_flags),\n"
        "\t.bart_bus_detail(bart_bus_detail),\n"
        "\t.bart_fetch_hist2(bart_fetch_hist2),\n"
        "\t.bart_fetch_hist3(bart_fetch_hist3),\n"
        "\t.bart_bus_events(bart_bus_events),\n"
    )
    d["top"] = d["top"].replace(old, old + hooks)

    mini_ports = (
        "\tinput [31:0] bart_raw_bus_addr,\n"
        "\tinput [15:0] bart_bus_flags,\n"
        "\tinput [15:0] bart_bus_detail,\n"
        "\tinput [23:0] bart_fetch_hist2,\n"
        "\tinput [23:0] bart_fetch_hist3,\n"
        "\tinput [31:0] bart_bus_events,\n"
    )
    d["minimig"] = replace_one(
        d["minimig"], "\tinput [31:0] bart_prev_fetch,",
        "\tinput [31:0] bart_prev_fetch,\n" + mini_ports.rstrip("\n"),
        "Minimig CPU bus input ports"
    )
    d["minimig"] = replace_one(
        d["minimig"], "\t.bart_prev_fetch(bart_prev_fetch),\n",
        "\t.bart_prev_fetch(bart_prev_fetch),\n" + hooks,
        "Minimig->Paula port wiring"
    )
    for name in ("paula", "floppy"):
        d[name] = replace_one(
            d[name], "\tinput [31:0] bart_prev_fetch,",
            "\tinput [31:0] bart_prev_fetch,\n" + mini_ports.rstrip("\n"),
            name + " diagnostic inputs"
        )
    d["paula"] = replace_one(
        d["paula"], "\t.bart_prev_fetch(bart_prev_fetch),\n",
        "\t.bart_prev_fetch(bart_prev_fetch),\n" + hooks,
        "Paula->Floppy port wiring"
    )

    # Each read uses a separate selector, with no writes to Paula or CPU
    # state. v2 deliberately changes the signature and protocol version.
    d["floppy"] = replace_one(
        d["floppy"], "6'd0: bart_diag_word = 16'hB4A6;",
        "6'd0: bart_diag_word = 16'hB4A7;", "FPGA v2 signature"
    )
    d["floppy"] = replace_one(
        d["floppy"], "6'd1: bart_diag_word = 16'd1;",
        "6'd1: bart_diag_word = 16'd2;", "FPGA v2 version"
    )
    reglist = r'''        6'd30: bart_diag_word = bart_raw_bus_addr[15:0];
        6'd31: bart_diag_word = bart_raw_bus_addr[31:16];
        6'd32: bart_diag_word = bart_bus_flags;
        6'd33: bart_diag_word = bart_bus_detail;
        6'd34: bart_diag_word = bart_fetch_hist2[15:0];
        6'd35: bart_diag_word = {8'd0, bart_fetch_hist2[23:16]};
        6'd36: bart_diag_word = bart_fetch_hist3[15:0];
        6'd37: bart_diag_word = {8'd0, bart_fetch_hist3[23:16]};
        6'd38: bart_diag_word = bart_bus_events[15:0];
        6'd39: bart_diag_word = bart_bus_events[31:16];
'''
    d["floppy"] = replace_one(
        d["floppy"],
        "        6'd29: bart_diag_word = bart_read_cycles[31:16];\n"
        "        default: bart_diag_word = 16'hDEAD;",
        "        6'd29: bart_diag_word = bart_read_cycles[31:16];\n"
        + reglist + "        default: bart_diag_word = 16'hDEAD;",
        "FPGA v2 snapshot registers 30-39"
    )
    for name, path in paths.items():
        path.write_text(d[name])
    print("Applied read-only CPU bus/status/fetch-history snapshot v2 to pinned FPGA.")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: patch_bart_fpga_cpu_bus_v2.py <FPGA source directory>")
    apply(Path(sys.argv[1]).resolve())
