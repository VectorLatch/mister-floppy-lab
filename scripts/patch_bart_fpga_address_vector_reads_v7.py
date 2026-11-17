#!/usr/bin/env python3
"""Read-only fx68k vector #3 ($00000C/$00000E) bus data diagnostic v7.

Layer after v1/v2/v3 + v6 first-DF trace overlays against the pinned
upstream FPGA and Rick ERSY beam fix. Reuses all 19 existing v6 SPI words
(45..63), without changing CPU, memory, floppy, exception or SPI control.

Capture the latest qualified CPU input-bus samples for read cycles at
24-bit $00000C and $00000E, including the actual cpu_din net connected
to fx68k.iEdb, FC, UDS/LDS, RAM route and bus event sequence. Freeze
these with first program-space fetch into $DFxxxx.
"""
from pathlib import Path
import subprocess
import sys

PINNED="7d5d3c2f685af4ce3eb361c22893fccd153f2d87"

def once(s,old,new,label):
    n=s.count(old)
    if n != 1:
        raise ValueError(f"{label}: expected one match, found {n}")
    return s.replace(old,new,1)

def apply(root):
    actual=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    if actual!=PINNED:
        raise ValueError(f"Wrong pinned official FPGA commit {actual}")

    cp=root/"rtl/cpu_wrapper.v"
    fl=root/"rtl/paula_floppy.v"
    cpu=cp.read_text()
    floppy=fl.read_text()
    if "DF_TRACE" in cpu or "bart_df_roll0" not in cpu or "16'hB4AB" not in floppy:
        raise ValueError("Apply v1,v2,v3,v6 FPGA patches (and NOT v4/v5) first")

    start_marker="// Bart V6 first *qualified program-space fetch* into $DF0000-$DFFFFF."
    end_marker="\nreg inflight;\n"
    start=cpu.find(start_marker)
    end=cpu.find(end_marker,start)
    if start<0 or end<0 or cpu.find(start_marker,start+1)>=0:
        raise ValueError("Failed to locate unique frozen v6 CPU trace block")

    # v6 already exported exactly 7 32-bit plus one 32-bit and
    # three 16-bit registers, all the way through the existing SPI
    # mux. Reuse those existing physical registers for v7 fields,
    # leaving functional CPU and other v1/v2/v3 outputs unchanged.
    logic="""
// Bart V7: address-error exception vector 3, input-bus observations.
// The fx68k core's iEdb is wired directly to cpu_din below.
// Sample on the same enPhi2 (=ph2) clock-enable edge as dataIo's
// potential iEdb read, when AS active and the selected DTACKn is low.
// This is a CPU input-bus value, *not* an assertion that a particular
// internal register definitively consumed this value.
wire bart_vec_dtackn = ramsel ? ~ramready : chip_dtack;
wire bart_vec_is_c = (cpu_addr[23:0] == 24'h00000C);
wire bart_vec_is_e = (cpu_addr[23:0] == 24'h00000E);
wire bart_vec_ack = (cpucfg[1:0] == 2'b00) && ph2 && !as_o
                    && wr_o && !uds_o && !lds_o
                    && !bart_vec_dtackn;
// The 16-bit bus metadata is:
// [15:13]=FC, [12:11]=RAM input source selector,
// [10]=ramsel, [9]=ramready, [8]=chip_dtack (active low),
// [7]=read/write (1=read), [6]=UDSn, [5]=LDSn,
// [4]=ph2, [3]=cpu_req, [2:0]=0.
wire [15:0] bart_vec_meta = {
    fc_o, ramdat_sel, ramsel, ramready, chip_dtack,
    wr_o, uds_o, lds_o, ph2, cpu_req, 3'b000
};

// The original v6 first-DF program-fetch trigger is reused.
wire bart_vec_first_df = (cpucfg[1:0] == 2'b00)
    && bart_fetch_evt && (bart_fetch_addr[23:16] == 8'hDF)
    && !bart_df_flags[0];

// v6's read-only, 19-word transport slots are repurposed:
// addr0: last C read bus-event sequence, addr1: last E read sequence,
// addr2: first DF fetch event sequence, addr3: first DF fetch address,
// addr4: CPU's internal PC at last C read,
// addr5: CPU's internal PC at last E read,
// addr6: {C_cpu_din,E_cpu_din}, pc: {C_metadata,E_metadata},
// psw: C read count, ird: E read count, flags: snapshot status.
// We only count once per address-strobe assertion, not every phi2.
reg bart_vec_cycle_taken;
reg bart_vec_c_seen;
reg bart_vec_e_seen;

always @(posedge clk) begin
    if (~reset) begin
        bart_vec_cycle_taken <= 1'b0;
        bart_vec_c_seen <= 1'b0;
        bart_vec_e_seen <= 1'b0;
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
        if (as_o)
            bart_vec_cycle_taken <= 1'b0;

        if (!bart_df_flags[0] && !bart_vec_cycle_taken &&
            bart_vec_ack && (bart_vec_is_c || bart_vec_is_e)) begin
            bart_vec_cycle_taken <= 1'b1;
            if (bart_vec_is_c) begin
                bart_vec_c_seen <= 1'b1;
                if (bart_df_psw != 16'hFFFF)
                    bart_df_psw <= bart_df_psw + 16'd1;
                bart_df_addr0 <= bart_bus_events;
                bart_df_addr4 <= bart_pc_internal_wire;
                bart_df_addr6[31:16] <= cpu_din;
                bart_df_pc[31:16] <= bart_vec_meta;
            end else begin
                bart_vec_e_seen <= 1'b1;
                if (bart_df_ird != 16'hFFFF)
                    bart_df_ird <= bart_df_ird + 16'd1;
                bart_df_addr1 <= bart_bus_events;
                bart_df_addr5 <= bart_pc_internal_wire;
                bart_df_addr6[15:0] <= cpu_din;
                bart_df_pc[15:0] <= bart_vec_meta;
            end
        end

        if (bart_vec_first_df) begin
            bart_df_addr2 <= bart_bus_events;
            bart_df_addr3 <= bart_fetch_addr;
            // Bit0 first DF captured; bit1 C read observed; bit2 E
            // read observed; bit3 latest C preceding latest E;
            // bit4 fx68k selected; bit5 C/E pointer (low 24) matches
            // first DF fetch; bit6 both FC codes supervisor data 101.
            bart_df_flags <= {
                9'd0,
                (bart_df_pc[31:29] == 3'b101 &&
                 bart_df_pc[15:13] == 3'b101 &&
                 bart_vec_c_seen && bart_vec_e_seen),
                (bart_vec_c_seen && bart_vec_e_seen &&
                 bart_df_addr6[23:0] == bart_fetch_addr[23:0]),
                1'b1,
                (bart_vec_c_seen && bart_vec_e_seen &&
                 bart_df_addr0 < bart_df_addr1),
                bart_vec_e_seen,
                bart_vec_c_seen,
                1'b1
            };
        end
    end
end
"""
    cpu=cpu[:start]+logic+cpu[end:]
    floppy=once(floppy,
        "6'd0: bart_diag_word = 16'hB4AB;",
        "6'd0: bart_diag_word = 16'hB4AC;",
        "v7 read-only SPI signature")
    floppy=once(floppy,
        "6'd1: bart_diag_word = 16'd6;",
        "6'd1: bart_diag_word = 16'd7;",
        "v7 on-demand SPI protocol version")

    # The existing transport has 64 slots (6-bit selector). Keep the
    # exact map and use a different paired Main decoder for v7's fields.
    expected=[
        "6'd45: bart_diag_word = bart_df_addr0[15:0];",
        "6'd58: bart_diag_word = bart_df_addr6[31:16];",
        "6'd59: bart_diag_word = bart_df_pc[15:0];",
        "6'd63: bart_diag_word = bart_df_flags;",
    ]
    if not all(x in floppy for x in expected):
        raise ValueError("Unexpected v6 FPGA 64-word diagnostic transport")
    if cpu.count("wire bart_vec_first_df")!=1 or cpu.count("bart_vec_ack")<2:
        raise ValueError("Vector ack recorder not present exactly once")
    cp.write_text(cpu)
    fl.write_text(floppy)
    print("Applied Bart V7 CPU-visible address-error vector read diagnostic.")
    print("64 words; signature B4AC protocol 7; CPU and disk datapaths unchanged.")

if __name__=="__main__":
    if len(sys.argv)!=2:
        raise SystemExit("Usage: patch_bart_fpga_address_vector_reads_v7.py <pinned FPGA source>")
    apply(Path(sys.argv[1]).resolve())
