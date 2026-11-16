#!/usr/bin/env python3
"""First-two misaligned memory access capture for fx68k, v4.

Layer on exact v1, v2, v3 read-only patches. Observe internal CPU AOB
(including A0), internal PC, Ird, PSW and microcode address when the
existing busAddrErr signal is qualified at an active address cycle.
No control-path behaviour is changed.
"""
from pathlib import Path
import subprocess, sys

PINNED="7d5d3c2f685af4ce3eb361c22893fccd153f2d87"
def once(s,old,new,label):
    if s.count(old)!=1: raise ValueError(f"{label}: expected 1 anchor found {s.count(old)}")
    return s.replace(old,new,1)

def apply(root):
    sha=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    if sha!=PINNED: raise ValueError(f"Wrong upstream FPGA source commit {sha}")
    paths=dict(fx=root/"rtl/fx68k/fx68k.sv",cpu=root/"rtl/cpu_wrapper.v",
               top=root/"Minimig.sv",minimig=root/"rtl/minimig.v",
               paula=root/"rtl/paula.v",floppy=root/"rtl/paula_floppy.v")
    d={k:p.read_text() for k,p in paths.items()}
    d["fx"]=paths["fx"].read_bytes().decode("utf-8")
    if "16'hB4A8" not in d["floppy"] or "oDbgErrorFlags" not in d["fx"]:
        raise ValueError("Apply v1, v2 and v3 FPGA source patches first")

    # ExcUnit retains full 32-bit address operand, including the missing A0,
    # plus the internal PC registers. Output ports only, no feedback.
    d["fx"]=once(d["fx"], "\toutput logic [23:1] eab);",
        "\toutput logic [23:1] eab,\n"
        "\toutput wire [31:0] oDbgPc,\n"
        "\toutput wire [31:0] oDbgAddress);",
        "excUnit debug ports")
    d["fx"]=once(d["fx"],"\treg [15:0] PcL, PcH;",
        "\treg [15:0] PcL, PcH;\n\tassign oDbgPc = {PcH, PcL};",
        "excUnit live PC")
    d["fx"]=once(d["fx"],"\treg [31:0] auReg, aob;",
        "\treg [31:0] auReg, aob;\n\tassign oDbgAddress = aob;",
        "excUnit live 32-bit address")
    d["fx"]=once(d["fx"],"\treg [15:0] ftu;",
        "\treg [15:0] ftu;\n"
        "\twire [31:0] bart_fault_live_pc;\n"
        "\twire [31:0] bart_fault_live_address;",
        "fx68k observation wires")
    d["fx"]=once(d["fx"],"\t\t.alue, .ccr);",
        "\t\t.alue, .ccr,\n"
        "\t\t.oDbgPc(bart_fault_live_pc), .oDbgAddress(bart_fault_live_address));",
        "fx68k->excUnit observation hook")

    fields=[
        ("fault_count",16,"FaultCount"),
        ("fault1_addr",32,"Fault1Address"),
        ("fault1_pc",32,"Fault1Pc"),
        ("fault1_psw",16,"Fault1Psw"),
        ("fault1_ird",16,"Fault1Ird"),
        ("fault1_uaddr",16,"Fault1Uaddr"),
        ("fault2_addr",32,"Fault2Address"),
        ("fault2_pc",32,"Fault2Pc"),
        ("fault2_psw",16,"Fault2Psw"),
        ("fault2_ird",16,"Fault2Ird"),
        ("fault2_uaddr",16,"Fault2Uaddr"),
    ]

    fxports="".join(
        "\toutput reg [%d:0] oDbg%s,\r\n"%(width-1,fxname)
        for name,width,fxname in fields
    )
    d["fx"]=once(d["fx"],"\toutput [7:0] oDbgErrorFlags,\r\n\tinput DTACKn,",
        "\toutput [7:0] oDbgErrorFlags,\r\n"+fxports+"\tinput DTACKn,",
        "fx68k output port list")

    latch = """
// Read-only first-two address error recorder. Existing fx68k internal
// busAddrErr = aob0 & ~bciByte; qualify it with active address cycle.
// Capture the first two distinct episodes after CPU reset; do not
// overwrite these records later during exception and HALT.
reg bart_addrerr_prev;
wire bart_addrerr_active = busAddrErr && addrOe;
always @(posedge clk) begin
    if (Clks.extReset) begin
        bart_addrerr_prev <= 1'b0;
        oDbgFaultCount <= 16'd0;
        oDbgFault1Address <= 32'd0;
        oDbgFault1Pc <= 32'd0;
        oDbgFault1Psw <= 16'd0;
        oDbgFault1Ird <= 16'd0;
        oDbgFault1Uaddr <= 16'd0;
        oDbgFault2Address <= 32'd0;
        oDbgFault2Pc <= 32'd0;
        oDbgFault2Psw <= 16'd0;
        oDbgFault2Ird <= 16'd0;
        oDbgFault2Uaddr <= 16'd0;
    end else if (Clks.enPhi1) begin
        bart_addrerr_prev <= bart_addrerr_active;
        if (bart_addrerr_active && !bart_addrerr_prev) begin
            if (oDbgFaultCount != 16'hFFFF)
                oDbgFaultCount <= oDbgFaultCount + 16'd1;
            if (oDbgFaultCount == 16'd0) begin
                oDbgFault1Address <= bart_fault_live_address;
                oDbgFault1Pc <= bart_fault_live_pc;
                oDbgFault1Psw <= psw;
                oDbgFault1Ird <= Ird;
                oDbgFault1Uaddr <= {6'd0, microAddr};
            end else if (oDbgFaultCount == 16'd1) begin
                oDbgFault2Address <= bart_fault_live_address;
                oDbgFault2Pc <= bart_fault_live_pc;
                oDbgFault2Psw <= psw;
                oDbgFault2Ird <= Ird;
                oDbgFault2Uaddr <= {6'd0, microAddr};
            end
        end
    end
end
"""
    d["fx"]=once(d["fx"],"\tassign oDbgMicroAddr = microAddr;",
        latch+"\n\tassign oDbgMicroAddr = microAddr;",
        "fx68k first/second odd access capture")

    cpu_ports="".join("\toutput reg [%d:0] bart_fx_%s,\n"%(w-1,n)
                      for n,w,_ in fields)
    d["cpu"]=once(d["cpu"],"\toutput reg [15:0] bart_fx_err,",
        "\toutput reg [15:0] bart_fx_err,\n"+cpu_ports.rstrip("\n"),
        "cpu wrapper diagnostic outputs")
    wires="".join("wire [%d:0] fx_fault_%s;\n"%(w-1,n) for n,w,_ in fields)
    d["cpu"]=once(d["cpu"],"wire        bart_fx_halt_n;",
        "wire        bart_fx_halt_n;\n"+wires.rstrip("\n"),
        "CPU wrapper read-only fx signals")
    fxhooks="".join("\t.oDbg%s(fx_fault_%s),\n"%(fxn,n)
                    for n,w,fxn in fields)
    d["cpu"]=once(d["cpu"],"\t.oHALTEDn(bart_fx_halt_n),",
        "\t.oHALTEDn(bart_fx_halt_n),\n"+fxhooks.rstrip("\n"),
        "fx68k signal outputs")
    samples="".join("    bart_fx_%s <= fx_fault_%s;\n"%(n,n)
                    for n,w,fxn in fields)
    d["cpu"]=once(d["cpu"],"    bart_fx_err       <= {8'd0, bart_fx_err_wire};",
        "    bart_fx_err       <= {8'd0, bart_fx_err_wire};\n"+samples.rstrip("\n"),
        "cpu wrapper sampling registers")

    topwires="".join("wire [%d:0] bart_fx_%s;\n"%(w-1,n)
                     for n,w,_ in fields)
    d["top"]=once(d["top"],"cpu_wrapper cpu_wrapper\n",
        topwires+"\ncpu_wrapper cpu_wrapper\n",
        "top diagnostic wire declarations")
    topinputs="".join("\tinput [%d:0] bart_fx_%s,\n"%(w-1,n)
                       for n,w,_ in fields)
    tophooks="".join("\t.bart_fx_%s(bart_fx_%s),\n"%(n,n)
                      for n,w,_ in fields)
    anchor="\t.bart_fx_err(bart_fx_err),\n"
    if d["top"].count(anchor)!=2:
        raise ValueError("Expected two v3 fx68k hooks in top")
    d["top"]=d["top"].replace(anchor,anchor+tophooks)

    for name in ("minimig","paula","floppy"):
        d[name]=once(d[name],"\tinput [15:0] bart_fx_err,",
            "\tinput [15:0] bart_fx_err,\n"+topinputs.rstrip("\n"),
            f"{name} v4 ports")
    for name in ("minimig","paula"):
        d[name]=once(d[name],anchor,anchor+tophooks,
                     f"{name} v4 forwarding")

    d["floppy"]=once(d["floppy"],
        "6'd0: bart_diag_word = 16'hB4A8;",
        "6'd0: bart_diag_word = 16'hB4A9;","v4 SPI signature")
    d["floppy"]=once(d["floppy"],
        "6'd1: bart_diag_word = 16'd3;",
        "6'd1: bart_diag_word = 16'd4;","v4 SPI version")

    regmap=[
        "        6'd45: bart_diag_word = bart_fx_fault_count;",
        "        6'd46: bart_diag_word = bart_fx_fault1_addr[15:0];",
        "        6'd47: bart_diag_word = bart_fx_fault1_addr[31:16];",
        "        6'd48: bart_diag_word = bart_fx_fault1_pc[15:0];",
        "        6'd49: bart_diag_word = bart_fx_fault1_pc[31:16];",
        "        6'd50: bart_diag_word = bart_fx_fault1_psw;",
        "        6'd51: bart_diag_word = bart_fx_fault1_ird;",
        "        6'd52: bart_diag_word = bart_fx_fault1_uaddr;",
        "        6'd53: bart_diag_word = bart_fx_fault2_addr[15:0];",
        "        6'd54: bart_diag_word = bart_fx_fault2_addr[31:16];",
        "        6'd55: bart_diag_word = bart_fx_fault2_pc[15:0];",
        "        6'd56: bart_diag_word = bart_fx_fault2_pc[31:16];",
        "        6'd57: bart_diag_word = bart_fx_fault2_psw;",
        "        6'd58: bart_diag_word = bart_fx_fault2_ird;",
        "        6'd59: bart_diag_word = bart_fx_fault2_uaddr;",
    ]
    d["floppy"]=once(d["floppy"],
        "        6'd44: bart_diag_word = bart_fx_err;\n"
        "        default: bart_diag_word = 16'hDEAD;",
        "        6'd44: bart_diag_word = bart_fx_err;\n"
        +"\n".join(regmap)+"\n"
        "        default: bart_diag_word = 16'hDEAD;",
        "FPGA v4 60-word snapshot map")

    for name,p in paths.items():
        if name=="fx": p.write_bytes(d[name].encode("utf-8"))
        else: p.write_text(d[name])
    print("Read-only first/second misaligned CPU address and PC recorder v4 applied.")
    print("SPI B4A9 protocol v4, 60 words.")

if __name__=="__main__":
    if len(sys.argv)!=2: raise SystemExit("Usage: patch_bart_fpga_first_address_fault_v4.py <FPGA source>")
    apply(Path(sys.argv[1]).resolve())
