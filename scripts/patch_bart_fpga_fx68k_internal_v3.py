#!/usr/bin/env python3
"""Read-only fx68k internal HALT/microcode/PSW/exception snapshot v3.

Apply on top of proven v1 and timing-clean v2 patches. The A500-selected
fx68k exports diagnostic-only wires; no CPU microcode, memory, bus control,
chipset clock, Paula or physical-floppy behaviour is changed.
"""
from pathlib import Path
import subprocess
import sys

PINNED = "7d5d3c2f685af4ce3eb361c22893fccd153f2d87"

def once(s, old, new, label):
    if s.count(old) != 1:
        raise ValueError(f"{label}: expected one anchor, found {s.count(old)}")
    return s.replace(old, new, 1)

def apply(root):
    actual = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual != PINNED:
        raise ValueError(f"Wrong official FPGA source commit: {actual}")
    files = {
        "fx": root / "rtl/fx68k/fx68k.sv",
        "cpu": root / "rtl/cpu_wrapper.v",
        "top": root / "Minimig.sv",
        "minimig": root / "rtl/minimig.v",
        "paula": root / "rtl/paula.v",
        "floppy": root / "rtl/paula_floppy.v",
    }
    d = {k: p.read_text() for k, p in files.items()}
    if "16'hB4A7" not in d["floppy"] or "bart_bus_events" not in d["cpu"]:
        raise ValueError("Apply existing Bart CPU/Paula v1 and CPU bus v2 patches first.")

    # Expose already-existing fx68k HALT output and selected registered
    # internal indicators. This only adds observation fanout.
    d["fx"] = once(
        d["fx"],
        "\toutput oRESETn, output oHALTEDn,\n\tinput DTACKn,",
        "\toutput oRESETn, output oHALTEDn,\n"
        "\toutput [9:0] oDbgMicroAddr,\n"
        "\toutput [15:0] oDbgPsw,\n"
        "\toutput [15:0] oDbgIrd,\n"
        "\toutput [7:0] oDbgErrorFlags,\n"
        "\tinput DTACKn,",
        "fx68k internal observation outputs"
    )
    d["fx"] = once(
        d["fx"], "\tassign oHALTEDn = !oHalted;",
        "\tassign oHALTEDn = !oHalted;\n"
        "\tassign oDbgMicroAddr = microAddr;\n"
        "\tassign oDbgPsw = psw;\n"
        "\tassign oDbgIrd = Ird;\n"
        "// {A0Err, latchedGroup0, latchedAddrErr, latchedBusErr,\n"
        "//  rawAddrErr, BerrA, latchedResetException, halted}\n"
        "\tassign oDbgErrorFlags = {A0Err, inGrp0Exc, rExcAdrErr, rExcBusErr,\n"
        "\t                        rAddrErr, BerrA, rExcRst, oHalted};",
        "fx68k debug-only assign"
    )

    outputs = (
        "\toutput reg [15:0] bart_fx_halt,\n"
        "\toutput reg [15:0] bart_fx_microaddr,\n"
        "\toutput reg [15:0] bart_fx_psw,\n"
        "\toutput reg [15:0] bart_fx_ird,\n"
        "\toutput reg [15:0] bart_fx_err,\n"
    )
    d["cpu"] = once(
        d["cpu"], "\toutput reg [31:0] bart_bus_events,",
        "\toutput reg [31:0] bart_bus_events,\n"+outputs.rstrip("\n"),
        "cpu wrapper debug outputs"
    )
    d["cpu"] = once(
        d["cpu"], "wire        reset_out_o;",
        "wire        reset_out_o;\n"
        "wire        bart_fx_halt_n;\n"
        "wire [9:0]  bart_fx_uaddr_wire;\n"
        "wire [15:0] bart_fx_psw_wire;\n"
        "wire [15:0] bart_fx_ird_wire;\n"
        "wire [7:0]  bart_fx_err_wire;",
        "fx observation wires"
    )
    d["cpu"] = once(
        d["cpu"], "\t.oRESETn(reset_out_o),",
        "\t.oRESETn(reset_out_o),\n"
        "\t.oHALTEDn(bart_fx_halt_n),\n"
        "\t.oDbgMicroAddr(bart_fx_uaddr_wire),\n"
        "\t.oDbgPsw(bart_fx_psw_wire),\n"
        "\t.oDbgIrd(bart_fx_ird_wire),\n"
        "\t.oDbgErrorFlags(bart_fx_err_wire),",
        "fx68k named port hooks"
    )
    # Register observed values for stable asynchronous SPI transfer.
    capture = r'''
// V3 internal CPU state, observation-only at clk.
always @(posedge clk) begin
    bart_fx_halt      <= {15'd0, ~bart_fx_halt_n};
    bart_fx_microaddr <= {6'd0, bart_fx_uaddr_wire};
    bart_fx_psw       <= bart_fx_psw_wire;
    bart_fx_ird       <= bart_fx_ird_wire;
    bart_fx_err       <= {8'd0, bart_fx_err_wire};
end
'''
    d["cpu"] = once(
        d["cpu"], "\nreg inflight;\n",
        "\n"+capture+"\nreg inflight;\n",
        "v3 sampled CPU internal state"
    )

    wires = (
        "wire [15:0] bart_fx_halt;\n"
        "wire [15:0] bart_fx_microaddr;\n"
        "wire [15:0] bart_fx_psw;\n"
        "wire [15:0] bart_fx_ird;\n"
        "wire [15:0] bart_fx_err;\n"
    )
    d["top"] = once(
        d["top"], "cpu_wrapper cpu_wrapper\n",
        wires+"\ncpu_wrapper cpu_wrapper\n",
        "top-level internal CPU observation wires"
    )
    hook = (
        "\t.bart_fx_halt(bart_fx_halt),\n"
        "\t.bart_fx_microaddr(bart_fx_microaddr),\n"
        "\t.bart_fx_psw(bart_fx_psw),\n"
        "\t.bart_fx_ird(bart_fx_ird),\n"
        "\t.bart_fx_err(bart_fx_err),\n"
    )
    tail="\t.bart_bus_events(bart_bus_events),\n"
    if d["top"].count(tail) != 2:
        raise ValueError("Expected two top-level Bart v2 CPU bus connections")
    d["top"] = d["top"].replace(tail,tail+hook)

    inputports = (
        "\tinput [15:0] bart_fx_halt,\n"
        "\tinput [15:0] bart_fx_microaddr,\n"
        "\tinput [15:0] bart_fx_psw,\n"
        "\tinput [15:0] bart_fx_ird,\n"
        "\tinput [15:0] bart_fx_err,\n"
    )
    for name in ("minimig", "paula", "floppy"):
        d[name] = once(
            d[name],
            "\tinput [31:0] bart_bus_events,",
            "\tinput [31:0] bart_bus_events,\n"+inputports.rstrip("\n"),
            f"{name} v3 input ports"
        )
    for name in ("minimig", "paula"):
        d[name] = once(
            d[name],tail,tail+hook,
            f"{name} v3 output forwarding"
        )
    d["floppy"] = once(
        d["floppy"], "6'd0: bart_diag_word = 16'hB4A7;",
        "6'd0: bart_diag_word = 16'hB4A8;",
        "signature version v3"
    )
    d["floppy"] = once(
        d["floppy"], "6'd1: bart_diag_word = 16'd2;",
        "6'd1: bart_diag_word = 16'd3;",
        "protocol version v3"
    )
    d["floppy"] = once(
        d["floppy"], "        6'd39: bart_diag_word = bart_bus_events[31:16];\n"
                    "        default: bart_diag_word = 16'hDEAD;",
        "        6'd39: bart_diag_word = bart_bus_events[31:16];\n"
        "        6'd40: bart_diag_word = bart_fx_halt;\n"
        "        6'd41: bart_diag_word = bart_fx_microaddr;\n"
        "        6'd42: bart_diag_word = bart_fx_psw;\n"
        "        6'd43: bart_diag_word = bart_fx_ird;\n"
        "        6'd44: bart_diag_word = bart_fx_err;\n"
        "        default: bart_diag_word = 16'hDEAD;",
        "floppy read-only registers 40-44"
    )
    for name,p in files.items():
        p.write_text(d[name])
    print("Applied fx68k internal HALT/PSW/uADDR/instruction and exception probe v3.")

if __name__=="__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: patch_bart_fpga_fx68k_internal_v3.py <pinned FPGA source>")
    apply(Path(sys.argv[1]).resolve())
