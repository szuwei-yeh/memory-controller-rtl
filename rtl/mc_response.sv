module mc_response #(
    parameter integer Q_DEPTH=16, ADDR_W=16, DATA_W=32, TAG_W=8,
    parameter integer SLOT_W=(Q_DEPTH>1 ? $clog2(Q_DEPTH) : 1)
) (
    input wire clk, rst,
    input wire [Q_DEPTH-1:0] occupied, done, writes,
    input wire [Q_DEPTH*ADDR_W-1:0] addresses,
    input wire [Q_DEPTH*DATA_W-1:0] read_data,
    input wire [Q_DEPTH*TAG_W-1:0] tags,
    input wire [Q_DEPTH*Q_DEPTH-1:0] older,
    input wire rsp_ready,
    output wire rsp_valid, rsp_write,
    output wire [TAG_W-1:0] rsp_tag,
    output wire [DATA_W-1:0] rsp_rdata,
    output wire retire_valid,
    output wire [SLOT_W-1:0] retire_slot,
    output reg [Q_DEPTH-1:0] response_eligible
);
    reg held_valid;
    reg [SLOT_W-1:0] held_slot;
    reg winner_valid, blocked;
    reg [SLOT_W-1:0] winner;
    reg [Q_DEPTH-1:0] selectable;
    always @* begin
        response_eligible=0; selectable=0; winner_valid=0; winner=0; blocked=0;
        for (integer i=0;i<Q_DEPTH;i=i+1) begin
            blocked=0;
            for (integer j=0;j<Q_DEPTH;j=j+1)
                if (occupied[j] && older[j*Q_DEPTH+i] &&
                    addresses[j*ADDR_W+:ADDR_W]==addresses[i*ADDR_W+:ADDR_W]) blocked=1;
            response_eligible[i]=occupied[i] && done[i] && !blocked;
            // Exclude only the held response from replacement arbitration. Its
            // occupied slot still blocks same-address successors above.
            selectable[i]=response_eligible[i] && (!held_valid || held_slot!=SLOT_W'(i));
        end
        for (integer i=0;i<Q_DEPTH;i=i+1) begin
            blocked=0;
            for (integer j=0;j<Q_DEPTH;j=j+1)
                if (selectable[j] && older[j*Q_DEPTH+i]) blocked=1;
            if (selectable[i] && !blocked) begin winner_valid=1; winner=SLOT_W'(i); end
        end
    end
    assign rsp_valid=held_valid && !rst;
    assign rsp_write=writes[held_slot];
    assign rsp_tag=tags[integer'(held_slot)*TAG_W+:TAG_W];
    assign rsp_rdata=read_data[integer'(held_slot)*DATA_W+:DATA_W];
    assign retire_valid=rsp_valid && rsp_ready;
    assign retire_slot=held_slot;
`ifdef FORMAL
    reg past_valid=0;
    always @(posedge clk) begin
        past_valid<=1;
        if (!rst && held_valid) assert (response_eligible[held_slot]);
        if (!rst && held_valid && winner_valid) assert (winner!=held_slot);
        if (past_valid && !rst && !$past(rst) && $past(held_valid && rsp_ready && winner_valid)) begin
            assert (held_valid);
            assert (held_slot==$past(winner));
        end
        if (past_valid && !rst && !$past(rst) && $past(rsp_valid && !rsp_ready)) begin
            assert (rsp_valid);
            assert ($stable({rsp_tag,rsp_write,rsp_rdata}));
        end
    end
`endif
    always @(posedge clk) begin
        if (rst) begin held_valid<=0; held_slot<=0; end
        else if (!held_valid || rsp_ready) begin
            held_valid<=winner_valid;
            held_slot<=winner;
        end
    end
endmodule
