// Reduced two-slot mixed read/write control proof. No host-response fairness assumption.
module formal_progress(input wire clk);
    reg rst=1;
    always @(posedge clk) rst<=0;
    (* anyseq *) reg req_valid, req_write, rsp_ready;
    (* anyseq *) reg [3:0] req_addr;
    (* anyseq *) reg req_tag;
    wire [7:0] req_wdata=0;
    wire req_ready, rsp_valid, rsp_write, rsp_tag, cmd_valid;
    wire [1:0] cmd_op, cmd_bank;
    wire cmd_row, cmd_col;
    wire [7:0] rsp_rdata, cmd_wdata;
    reg rd_valid=0;
    wire [7:0] rd_data=0;
    mc_top #(.ROWS(2),.COLS(2),.DATA_W(8),.TAG_W(1),.Q_DEPTH(2),.READ_LATENCY(1),
        .T_RCD(1),.T_RP(1),.T_RAS(2),.T_CCD(1),.T_WR(2),.AGE_LIMIT(3),
        .SCHED_POLICY(1),.AGING_ENABLE(1)) dut (.*);
    reg [1:0] busy;
    reg past_valid=0;
    always @(posedge clk) begin
        past_valid<=1;
        if (rst) begin busy<=0; rd_valid<=0; end
        else begin
            rd_valid<=cmd_valid && cmd_op==1;
            if (past_valid && !$past(rst) && $past(req_valid && !req_ready)) begin
                assume (req_valid); assume ($stable({req_addr,req_tag}));
            end
            if (req_valid) assume (!busy[req_tag]);
            if (rsp_valid) begin
                assert (busy[rsp_tag]); assert (rsp_rdata==0);
                if (rsp_ready) busy[rsp_tag]<=0;
            end
            if (req_valid && req_ready) busy[req_tag]<=1;
        end
    end
endmodule
