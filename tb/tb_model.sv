`timescale 1ns/1ps
module tb_model;
    reg clk=0;
    always #5 clk=~clk;
    reg rst=1, cmd_valid=0;
    reg [1:0] cmd_op=0, cmd_bank=0;
    reg cmd_row=0, cmd_col=0;
    reg [31:0] cmd_wdata=32'hfeed1234;
    wire rd_valid;
    wire [31:0] rd_data;
    integer test_case;
    dram_model #(.ROWS(2),.COLS(2),.READ_LATENCY(2),.T_RCD(2),.T_RP(2),
        .T_RAS(4),.T_CCD(2),.T_WR(3)) dut (.*);
    task automatic step(input bit valid, input reg [1:0] op);
        cmd_valid=valid; cmd_op=op; @(negedge clk);
    endtask
    initial begin
        test_case=0; void'($value$plusargs("case=%d",test_case));
        repeat (3) @(negedge clk);
        rst=0;
        if (test_case==8) step(1,3);
        step(1,0); // C0 ACT
        if (test_case==9) begin
            step(0,0); step(0,0); step(0,0); step(1,3); // C4 exact tRAS
            $display("PASS model exact tRAS boundary"); $finish;
        end
        if (test_case==1) step(1,1);
        if (test_case==7) step(1,0);
        step(0,0); // C1
        if (test_case==3) begin step(0,0); step(1,3); end // C3: tRAS-1
        if (test_case==6) cmd_row=1;
        step(1,2); // C2 WRITE
        if (test_case==4) step(1,1);
        step(0,0); // C3
        if (test_case==5) step(1,3); // C4 satisfies tRAS, violates tWR
        step(1,1); // C4 READ snapshot
        step(1,3); // C5 PRE exact tWR
        if (test_case==2) step(1,0); // C6 too early
        if (!rd_valid || rd_data!=32'hfeed1234) $fatal(1,"legal snapshot/latency");
        step(0,0); // C6
        step(1,0); // C7 exact tRP
        step(0,0); step(1,1); // C9 exact tRCD
        step(0,0); step(0,0);
        if (test_case!=0) $fatal(1,"negative test unexpectedly reached end");
        $display("PASS model legal boundaries and snapshot"); $finish;
    end
endmodule
