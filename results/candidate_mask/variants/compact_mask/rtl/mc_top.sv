module mc_top #(
    parameter integer ROWS=256, COLS=64, DATA_W=32, Q_DEPTH=16, TAG_W=8,
    parameter integer READ_LATENCY=3, T_RCD=3, T_RP=3, T_RAS=6, T_CCD=2, T_WR=3,
    parameter integer AGE_LIMIT=128, SCHED_POLICY=1, AGING_ENABLE=1,
    parameter integer ROW_W=$clog2(ROWS), COL_W=$clog2(COLS), ADDR_W=ROW_W+COL_W+2,
    parameter integer SLOT_W=(Q_DEPTH>1 ? $clog2(Q_DEPTH) : 1),
    parameter integer AGE_W=(AGE_LIMIT>0 ? $clog2(AGE_LIMIT+1) : 1)
) (
    input wire clk, rst,
    input wire req_valid, req_write,
    output wire req_ready,
    input wire [ADDR_W-1:0] req_addr,
    input wire [DATA_W-1:0] req_wdata,
    input wire [TAG_W-1:0] req_tag,
    output wire rsp_valid, rsp_write,
    input wire rsp_ready,
    output wire [TAG_W-1:0] rsp_tag,
    output wire [DATA_W-1:0] rsp_rdata,
    output wire cmd_valid,
    output wire [1:0] cmd_op, cmd_bank,
    output wire [ROW_W-1:0] cmd_row,
    output wire [COL_W-1:0] cmd_col,
    output wire [DATA_W-1:0] cmd_wdata,
    input wire rd_valid,
    input wire [DATA_W-1:0] rd_data
);
    wire [Q_DEPTH-1:0] occupied, pending, done, writes, eligible, legal, hit, response_eligible;
    wire [Q_DEPTH*ADDR_W-1:0] addresses;
    wire [Q_DEPTH*DATA_W-1:0] write_data, read_data;
    wire [Q_DEPTH*TAG_W-1:0] tags;
    wire [Q_DEPTH*Q_DEPTH-1:0] older;
    wire [Q_DEPTH*Q_DEPTH-1:0] same_address;
    wire [Q_DEPTH*AGE_W-1:0] ages;
    wire [Q_DEPTH*2-1:0] next_ops;
    wire [3:0] bank_open, owner_valid, can_act, can_col, can_pre;
    wire [4*ROW_W-1:0] open_rows;
    wire [4*SLOT_W-1:0] owners;
    wire [Q_DEPTH-1:0] candidate_mask;
    wire select_valid, retire_valid, protection_active;
    wire [SLOT_W-1:0] select_slot, retire_slot, protection_slot;
    wire [ADDR_W-1:0] selected_addr=addresses[integer'(select_slot)*ADDR_W+:ADDR_W];
    wire issue_column=cmd_valid && (cmd_op==1 || cmd_op==2);

    // Share address equality only. Command and response dependency lifetimes
    // remain separate: the consumers qualify this matrix with pending/occupied.
    for (genvar i=0;i<Q_DEPTH;i=i+1) begin : address_match
        for (genvar j=0;j<Q_DEPTH;j=j+1) begin : pair_match
            if (i==j) begin : diagonal
                assign same_address[i*Q_DEPTH+j]=1'b1;
            end else if (i<j) begin : compare_pair
                assign same_address[i*Q_DEPTH+j]=
                    addresses[i*ADDR_W+:ADDR_W]==addresses[j*ADDR_W+:ADDR_W];
            end else begin : mirror_pair
                assign same_address[i*Q_DEPTH+j]=same_address[j*Q_DEPTH+i];
            end
        end
    end

    mc_transaction_table #(.Q_DEPTH(Q_DEPTH),.ADDR_W(ADDR_W),.DATA_W(DATA_W),.TAG_W(TAG_W),
        .READ_LATENCY(READ_LATENCY),.AGE_LIMIT(AGE_LIMIT)) table_i (
        .clk,.rst,.req_valid,.req_write,.req_ready,.req_addr,.req_wdata,.req_tag,
        .issue_valid(issue_column),.issue_slot(select_slot),.rd_valid,.rd_data,
        .retire_valid,.retire_slot,.occupied,.pending,.done,.writes,.addresses,.write_data,
        .read_data,.tags,.older,.ages);
    mc_bank_tracker #(.ROW_W(ROW_W),.SLOT_W(SLOT_W),.T_RCD(T_RCD),.T_RP(T_RP),
        .T_RAS(T_RAS),.T_CCD(T_CCD),.T_WR(T_WR)) banks_i (
        .clk,.rst,.issue_valid(cmd_valid),.issue_op(cmd_op),.issue_bank(cmd_bank),
        .issue_row(cmd_row),.issue_slot(select_slot),.bank_open,.owner_valid,.open_rows,
        .owners,.can_act,.can_col,.can_pre);
    mc_candidates #(.Q_DEPTH(Q_DEPTH),.ROW_W(ROW_W),.COL_W(COL_W)) candidates_i (
        .pending,.writes,.addresses,.same_address,.older,.bank_open,.owner_valid,.can_act,.can_col,.can_pre,
        .open_rows,.owners,.eligible,.legal,.hit,.next_ops,.candidate_mask);
    if (SCHED_POLICY==0) begin : strict_fcfs
        mc_scheduler_strict_fcfs #(.Q_DEPTH(Q_DEPTH)) scheduler_i (
            .pending,.legal,.older,.select_valid,.select_slot);
        assign protection_active=0;
        assign protection_slot=0;
    end else begin : frfcfs
        mc_scheduler_frfcfs #(.Q_DEPTH(Q_DEPTH),.ADDR_W(ADDR_W),.AGE_LIMIT(AGE_LIMIT),
            .AGING_ENABLE(AGING_ENABLE)) scheduler_i (
            .clk,.rst,.pending,.legal,.next_ops,.addresses,.older,.ages,.candidate_mask,
            .owner_valid,.owners,.select_valid,.select_slot,.protection_active,.protection_slot);
    end
    mc_response #(.Q_DEPTH(Q_DEPTH),.DATA_W(DATA_W),.TAG_W(TAG_W)) response_i (
        .clk,.rst,.occupied,.done,.writes,.same_address,.read_data,.tags,.older,.rsp_ready,
        .rsp_valid,.rsp_write,.rsp_tag,.rsp_rdata,.retire_valid,.retire_slot,.response_eligible);
    assign cmd_valid=select_valid && !rst;
    assign cmd_op=next_ops[integer'(select_slot)*2+:2];
    assign cmd_bank=selected_addr[1:0];
    assign cmd_col=selected_addr[2+:COL_W];
    assign cmd_row=selected_addr[2+COL_W+:ROW_W];
    assign cmd_wdata=write_data[integer'(select_slot)*DATA_W+:DATA_W];
`ifdef FORMAL
`ifdef PROGRESS_CHECK
    localparam integer BOUND=AGE_LIMIT+2*Q_DEPTH*(T_RAS+T_WR+T_RP+T_RCD+T_CCD+8);
    localparam integer WAIT_W=$clog2(BOUND+2);
    reg [WAIT_W-1:0] waiting_cycles [0:Q_DEPTH-1];
    always @(posedge clk) begin
        for (integer i=0;i<Q_DEPTH;i=i+1) begin
            if (rst || !pending[i]) waiting_cycles[i]<=0;
            else begin
                waiting_cycles[i]<=waiting_cycles[i]+1'b1;
                assert (waiting_cycles[i]<WAIT_W'(BOUND));
            end
        end
    end
`endif
    always @(posedge clk) if (!rst) begin
        if (cmd_valid) assert (legal[select_slot]);
        if (issue_column)
            for (integer j=0;j<Q_DEPTH;j=j+1)
                assert (!(pending[j] && older[j*Q_DEPTH+integer'(select_slot)] &&
                    addresses[j*ADDR_W+:ADDR_W]==selected_addr));
        for (integer b=0;b<4;b=b+1)
            if (owner_valid[b]) begin
                assert (pending[owners[b*SLOT_W+:SLOT_W]]);
                assert (addresses[integer'(owners[b*SLOT_W+:SLOT_W])*ADDR_W+:2]==2'(b));
            end
    end
`endif
`ifndef SYNTHESIS
    initial begin
        if (ROWS<2 || (ROWS & (ROWS-1))!=0 || COLS<2 || (COLS & (COLS-1))!=0)
            $fatal(1,"rows and columns must be powers of two >=2");
        if (DATA_W<8 || DATA_W%8!=0 || Q_DEPTH<1 || TAG_W<1 || READ_LATENCY<1 || AGE_LIMIT<1)
            $fatal(1,"invalid dimensions");
        if (T_RCD<1 || T_RP<1 || T_RAS<1 || T_CCD<1 || T_WR<1 || SCHED_POLICY<0 || SCHED_POLICY>1)
            $fatal(1,"invalid timing or policy");
    end
`endif
endmodule
