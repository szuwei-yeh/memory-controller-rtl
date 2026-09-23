module formal_top(input wire clk);
    parameter integer POLICY=1, AGING=1;
    reg rst=1;
    always @(posedge clk) rst<=0;
    (* anyseq *) reg req_valid, req_write, rsp_ready;
    (* anyseq *) reg [3:0] req_addr;
    (* anyseq *) reg [7:0] req_wdata;
    (* anyseq *) reg [1:0] req_tag;
    wire req_ready, rsp_valid, rsp_write, cmd_valid;
    wire [1:0] rsp_tag, cmd_op, cmd_bank;
    wire [7:0] rsp_rdata, cmd_wdata;
    wire cmd_row, cmd_col;
    reg rd_valid;
    reg [7:0] rd_data;
    mc_top #(.ROWS(2),.COLS(2),.DATA_W(8),.TAG_W(2),.Q_DEPTH(2),.READ_LATENCY(1),
        .T_RCD(1),.T_RP(1),.T_RAS(2),.T_CCD(1),.T_WR(2),.AGE_LIMIT(3),
        .SCHED_POLICY(POLICY),.AGING_ENABLE(AGING)) dut (.*);
    reg [7:0] memory [0:15];
    reg [7:0] reference_memory [0:15];
    reg [7:0] expected [0:3];
    reg [3:0] busy, operations;
    reg [3:0] addresses [0:3];
    reg [6:0] wait_age [0:3];
    reg [3:0] waiting;
    reg past_valid=0;
    reg [3:0] older_tags [0:3];
    wire [3:0] command_address={cmd_row,cmd_col,cmd_bank};
    integer count;
    always @(posedge clk) begin
        past_valid<=1;
        if (rst) begin
            busy<=0; waiting<=0; operations<=0; rd_valid<=0; rd_data<=0;
            for (integer i=0;i<16;i=i+1) begin memory[i]<=0; reference_memory[i]<=0; end
            for (integer t=0;t<4;t=t+1) begin expected[t]<=0; addresses[t]<=0; wait_age[t]<=0; older_tags[t]<=0; end
        end else begin
            if (past_valid && !$past(rst) && $past(req_valid && !req_ready)) begin
                assume (req_valid);
                assume ($stable({req_addr,req_write,req_wdata,req_tag}));
            end
            if (req_valid) assume (!busy[req_tag]);
            count=0;
            for (integer t=0;t<4;t=t+1) begin
                if (busy[t]) count=count+1;
                if (waiting[t]) begin
                    wait_age[t]<=wait_age[t]+1'b1;
                    if (AGING || POLICY==0) assert (wait_age[t]<=7'd63);
                end
            end
            assert (count<=2);
            rd_valid<=cmd_valid && cmd_op==1;
            if (cmd_valid && cmd_op==1) rd_data<=memory[command_address];
            if (cmd_valid && cmd_op==2) memory[command_address]<=cmd_wdata;
            // There is exactly one oldest waiting same-address operation on column issue.
            for (integer t=0;t<4;t=t+1)
                if (cmd_valid && (cmd_op==1 || cmd_op==2) && waiting[t] && addresses[t]==command_address &&
                    (older_tags[t] & waiting)==0) waiting[t]<=0;
            if (rsp_valid) begin
                assert (busy[rsp_tag]);
                assert (rsp_write==operations[rsp_tag]);
                assert (rsp_rdata==expected[rsp_tag]);
                assert ((older_tags[rsp_tag] & busy)==0);
                if (rsp_ready) begin busy[rsp_tag]<=0; waiting[rsp_tag]<=0; end
            end
            if (req_valid && req_ready) begin
                busy[req_tag]<=1; waiting[req_tag]<=1; wait_age[req_tag]<=0;
                addresses[req_tag]<=req_addr; operations[req_tag]<=req_write;
                expected[req_tag]<=req_write ? 8'd0 : reference_memory[req_addr];
                if (req_write) reference_memory[req_addr]<=req_wdata;
                for (integer t=0;t<4;t=t+1)
                    older_tags[req_tag][t]<=busy[t] && addresses[t]==req_addr && !(rsp_valid && rsp_ready && rsp_tag==t);
            end
            // Clear consumed tags from all dependency sets before they can be reused.
            if (rsp_valid && rsp_ready)
                for (integer t=0;t<4;t=t+1) older_tags[t][rsp_tag]<=0;
            cover (count==2 && rsp_valid && !rsp_ready);
        end
    end
endmodule
