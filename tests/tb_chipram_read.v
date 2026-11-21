// Reproduce bridge read-data capture across a DMA-owned phase.
// Uses REAL pinned upstream minimig_m68k_bridge and amiga_clk modules.
// The data_in path models gary.v: cpu_data_in = dbr ? 16'h0000 :
// custom_data_out | ram_data_out (both other outputs zero).
// This is an isolated handshake test, NOT Bart/game emulation.
`timescale 1ns/1ps
module tb_chipram_read;
    reg clk=0;
    always #10 clk=~clk;
    reg reset_n=0;
    wire clk7_en,clk7n_en,c1,c3,cck;
    wire [9:0] eclk;
    amiga_clk timing (
        .clk_28(clk), .reset_n(reset_n),
        .clk7_en(clk7_en), .clk7n_en(clk7n_en),
        .c1(c1), .c3(c3), .cck(cck), .eclk(eclk)
    );

    reg as_n=1;
    reg phase_dma=0;
    reg [15:0] expected_data=16'hCAFE;
    wire dbr = phase_dma && !cck;
    wire [15:0] data_in = dbr ? 16'h0000 : expected_data;

    wire dtack_n, rd, hwr,lwr,rd_cyc,long_en,bls;
    wire [23:1] address_out;
    wire [15:0] external_data,data_out,host_rdat;
    wire host_ack;
    minimig_m68k_bridge dut (
        .clk(clk),.clk7_en(clk7_en),.clk7n_en(clk7n_en),
        .c1(c1),.c3(c3),.eclk(eclk),
        .vpa(1'b0),.dbr(dbr),.dbs(1'b1),.xbs(1'b1),
        .nrdy(1'b0),.bls(bls),.blit_nasty(1'b0),.cck(cck),
        .memory_config(4'd0),
        ._as(as_n),._lds(1'b0),._uds(1'b0),.r_w(1'b1),
        .cpu_long(1'b0),.long_en(long_en),
        ._dtack(dtack_n),.rd(rd),.hwr(hwr),.lwr(lwr),
        .address(23'h000200),.address_out(address_out),
        .data(external_data),.cpudatain(16'd0),.data_out(data_out),
        .data_in(data_in),.rd_cyc(rd_cyc),
        ._cpu_reset(1'b1),.cpu_halt(1'b0),
        .host_cs(1'b0),.host_adr(23'd0),.host_we(1'b0),
        .host_bs(2'b00),.host_wdat(16'd0),
        .host_rdat(host_rdat),.host_ack(host_ack)
    );

    integer expect_corrected=0;
    reg [15:0] observed;
    initial begin
        if ($test$plusargs("expect_corrected")) expect_corrected=1;
        #100000;
        $fatal(1,"TIMED OUT: CPU never acknowledged or testbench hung");
    end

    task run_read(input integer dma_phase,input [15:0] word);
    begin
        // change the memory word ONLY while no CPU cycle is active
        @(negedge clk);
        as_n=1'b1;
        phase_dma=dma_phase;
        expected_data=word;
        repeat(24) @(negedge clk);
        as_n=1'b0;
        wait(dtack_n===1'b0);
        #1;
        observed=external_data;
        $display("RESULT phase_dma=%0d expected=%04h observed=%04h cck=%b dbr=%b rd=%b",
                 dma_phase,word,observed,cck,dbr,rd);
        if (!dma_phase && observed !== word)
            $fatal(1,"CONTROL FAILURE: CPU read wrong word without DMA");
        if (dma_phase) begin
            if (!expect_corrected && observed === word)
                $fatal(1,"CONTROL FAILURE: stale read not reproduced");
            if (expect_corrected && observed !== word)
                $fatal(1,"FIX FAILURE: corrected bridge still returned wrong word");
        end
        @(negedge clk);
        as_n=1'b1;
        repeat(24) @(negedge clk);
    end
    endtask

    initial begin
        repeat(10) @(negedge clk);
        reset_n=1;
        repeat(20) @(negedge clk);
        run_read(0,16'hCAFE);
        run_read(1,16'hBEEF);
        if(expect_corrected)
            $display("PASS: model's CPU returns correct data even with intervening DMA-owned phase");
        else
            $display("REPRODUCED: raw bridge acknowledges a CPU read with invalid/stale data under selected DMA phase");
        $finish;
    end
endmodule
