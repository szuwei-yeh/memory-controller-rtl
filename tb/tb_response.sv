`timescale 1ns/1ps
// Preloaded completion-table fixtures isolate response selection from DRAM timing.
module tb_response;
    localparam integer Q=8, AW=4, DW=32, TW=4, SW=3;
    reg clk=0;
    always #5 clk=~clk;
    reg rst=1, rsp_ready=0;
    reg [Q-1:0] occupied=0, done=0, writes=0;
    reg [Q*AW-1:0] addresses=0;
    reg [Q*DW-1:0] read_data=0;
    reg [Q*TW-1:0] tags=0;
    reg [Q*Q-1:0] older=0;
    wire rsp_valid, rsp_write, retire_valid;
    wire [TW-1:0] rsp_tag;
    wire [DW-1:0] rsp_rdata;
    wire [SW-1:0] retire_slot;
    wire [Q-1:0] response_eligible;
    integer count=0;
    mc_response #(.Q_DEPTH(Q),.ADDR_W(AW),.DATA_W(DW),.TAG_W(TW)) dut (.*);

    // The table frees the consumed slot on the same edge as the response register.
    always @(posedge clk) begin
        if (rst) count<=0;
        else if (retire_valid) begin
            assert (occupied[retire_slot] && done[retire_slot]) else $fatal(1,"duplicate/incomplete retirement");
            occupied[retire_slot]<=0;
            count<=count+1;
        end
    end
    task automatic fixture;
        @(negedge clk); rst=1; rsp_ready=0; occupied=0; done=0; writes=0; older=0;
        for (integer i=0;i<Q;i=i+1) begin
            addresses[i*AW+:AW]=AW'(i); tags[i*TW+:TW]=TW'(i);
            read_data[i*DW+:DW]=32'h12340000+32'(i);
            for (integer j=0;j<Q;j=j+1) older[i*Q+j]=(i<j);
        end
        repeat (2) @(negedge clk); rst=0;
    endtask
    task automatic check_response(input integer tag);
        assert (rsp_valid && rsp_tag==TW'(tag) && !rsp_write &&
                rsp_rdata==32'h12340000+32'(tag))
            else $fatal(1,"response expected tag=%0d got valid=%0d tag=%0d",tag,rsp_valid,rsp_tag);
    endtask
    task automatic first_response(input integer tag);
        do @(posedge clk); while (!rsp_valid);
        check_response(tag);
    endtask
    initial begin
        // Eight already-completed independent entries must drain on eight adjacent edges.
        fixture(); occupied='1; done='1; rsp_ready=1;
        first_response(0);
        for (integer i=1;i<Q;i=i+1) begin @(posedge clk); check_response(i); end
        @(negedge clk);
        assert (count==Q) else $fatal(1,"consecutive retirement count");
        @(posedge clk); assert (!rsp_valid) else $fatal(1,"last slot selected again");

        // Keep a held response stable while an older independent request completes.
        fixture(); occupied=8'h0f; done=8'h06;
        addresses[3*AW+:AW]=AW'(1); // Slot 3 is a same-address successor of held slot 1.
        first_response(1);
        @(negedge clk); done=8'h0f;
        repeat (3) begin @(posedge clk); check_response(1); end
        @(negedge clk); rsp_ready=1;
        @(posedge clk); check_response(1);
        @(posedge clk); check_response(0); // Oldest *other* eligible response refills.
        @(posedge clk); check_response(2);
        @(posedge clk); check_response(3);
        @(negedge clk); assert (count==4) else $fatal(1,"stall/reordering accounting");

        // A newly unblocked same-address successor retains the conservative bubble.
        fixture(); occupied=8'h03; done=8'h03; rsp_ready=1;
        addresses[AW+:AW]=0;
        first_response(0);
        @(posedge clk); assert (!rsp_valid) else $fatal(1,"same-edge same-address lookahead");
        @(posedge clk); check_response(1);
        @(negedge clk); assert (count==2) else $fatal(1,"same-address accounting");

        // Reset cancels a held response without a phantom retirement.
        fixture(); occupied=1; done=1;
        first_response(0);
        @(negedge clk); rst=1;
        @(posedge clk); assert (!rsp_valid && !retire_valid) else $fatal(1,"reset response");
        $display("PASS response refill: 8 consecutive handshakes, stall stability, independent bypass, same-address bubble, reset");
        $finish;
    end
    initial begin #10000; $fatal(1,"response test timeout"); end
endmodule
