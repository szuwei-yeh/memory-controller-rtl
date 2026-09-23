module mc_candidates #(
    parameter integer Q_DEPTH=16, ROW_W=8, COL_W=6,
    parameter integer ADDR_W=ROW_W+COL_W+2,
    parameter integer SLOT_W=(Q_DEPTH>1 ? $clog2(Q_DEPTH) : 1)
) (
    input wire [Q_DEPTH-1:0] pending, writes,
    input wire [Q_DEPTH*ADDR_W-1:0] addresses,
    input wire [Q_DEPTH*Q_DEPTH-1:0] older,
    input wire [3:0] bank_open, owner_valid, can_act, can_col, can_pre,
    input wire [4*ROW_W-1:0] open_rows,
    input wire [4*SLOT_W-1:0] owners,
    output reg [Q_DEPTH-1:0] eligible, legal, hit,
    output reg [Q_DEPTH*2-1:0] next_ops,
    output reg [3:0] candidate_valid,
    output reg [4*SLOT_W-1:0] candidate_slots
);
    integer bank;
    reg blocked, has_older, any_hit;
    reg [Q_DEPTH-1:0] choices;
    always @* begin
        eligible=0; legal=0; hit=0; next_ops=0;
        candidate_valid=0; candidate_slots=0; choices=0;
        bank=0; blocked=0; has_older=0; any_hit=0;
        for (integer i=0;i<Q_DEPTH;i=i+1) begin
            bank=integer'(addresses[i*ADDR_W+:2]);
            blocked=0;
            for (integer j=0;j<Q_DEPTH;j=j+1)
                if (pending[j] && older[j*Q_DEPTH+i] &&
                    addresses[j*ADDR_W+:ADDR_W]==addresses[i*ADDR_W+:ADDR_W]) blocked=1;
            eligible[i]=pending[i] && !blocked &&
                (!owner_valid[bank] || owners[bank*SLOT_W+:SLOT_W]==SLOT_W'(i));
            hit[i]=bank_open[bank] &&
                open_rows[bank*ROW_W+:ROW_W]==addresses[i*ADDR_W+COL_W+2+:ROW_W];
            if (!bank_open[bank]) begin next_ops[i*2+:2]=0; legal[i]=eligible[i] && can_act[bank]; end
            else if (!hit[i]) begin next_ops[i*2+:2]=3; legal[i]=eligible[i] && can_pre[bank]; end
            else begin next_ops[i*2+:2]=writes[i] ? 2'd2 : 2'd1; legal[i]=eligible[i] && can_col[bank]; end
        end
        for (integer b=0;b<4;b=b+1) begin
            choices=0;
            for (integer i=0;i<Q_DEPTH;i=i+1)
                choices[i]=eligible[i] && addresses[i*ADDR_W+:2]==2'(b) && hit[i];
            any_hit=(choices!=0);
            for (integer i=0;i<Q_DEPTH;i=i+1)
                choices[i]=eligible[i] && addresses[i*ADDR_W+:2]==2'(b) && (!any_hit || hit[i]);
            for (integer i=0;i<Q_DEPTH;i=i+1) begin
                has_older=0;
                for (integer j=0;j<Q_DEPTH;j=j+1)
                    if (choices[j] && older[j*Q_DEPTH+i]) has_older=1;
                if (choices[i] && !has_older) begin
                    candidate_valid[b]=1;
                    candidate_slots[b*SLOT_W+:SLOT_W]=SLOT_W'(i);
                end
            end
        end
    end
endmodule
