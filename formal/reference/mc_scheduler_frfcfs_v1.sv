// Frozen v1.1 reference (source SHA-256 in results/scheduler_optimization/summary.json).
// Verification only: intentionally retains the pre-optimization implementation.
module mc_scheduler_frfcfs_v1 #(
    parameter integer Q_DEPTH=16, ADDR_W=16, AGE_LIMIT=128, AGING_ENABLE=1,
    parameter integer SLOT_W=(Q_DEPTH>1 ? $clog2(Q_DEPTH) : 1),
    parameter integer AGE_W=(AGE_LIMIT>0 ? $clog2(AGE_LIMIT+1) : 1)
) (
    input wire clk, rst,
    input wire [Q_DEPTH-1:0] pending, legal,
    input wire [Q_DEPTH*2-1:0] next_ops,
    input wire [Q_DEPTH*ADDR_W-1:0] addresses,
    input wire [Q_DEPTH*Q_DEPTH-1:0] older,
    input wire [Q_DEPTH*AGE_W-1:0] ages,
    input wire [3:0] candidate_valid, owner_valid,
    input wire [4*SLOT_W-1:0] candidate_slots, owners,
    output reg select_valid,
    output reg [SLOT_W-1:0] select_slot,
    output wire protection_active,
    output wire [SLOT_W-1:0] protection_slot
);
    reg protected_valid;
    reg [SLOT_W-1:0] protected_slot;
    reg oldest_valid, has_older, force_valid;
    reg [SLOT_W-1:0] oldest_slot, target, service;
    reg [1:0] target_bank;
    reg [Q_DEPTH-1:0] choices, columns;
    integer idx;
    assign protection_active=force_valid;
    assign protection_slot=target;
    always @* begin
        oldest_valid=0; oldest_slot=0; has_older=0;
        for (integer i=0;i<Q_DEPTH;i=i+1) begin
            has_older=0;
            for (integer j=0;j<Q_DEPTH;j=j+1)
                if (pending[j] && older[j*Q_DEPTH+i]) has_older=1;
            if (pending[i] && !has_older) begin oldest_valid=1; oldest_slot=SLOT_W'(i); end
        end
        force_valid=(AGING_ENABLE!=0) && (protected_valid ||
            (oldest_valid && ages[integer'(oldest_slot)*AGE_W+:AGE_W]==AGE_W'(AGE_LIMIT)));
        target=protected_valid ? protected_slot : oldest_slot;
        target_bank=addresses[integer'(target)*ADDR_W+:2];
        service=owner_valid[target_bank] ? owners[integer'(target_bank)*SLOT_W+:SLOT_W] : target;
        choices=0; columns=0; idx=0;
        for (integer b=0;b<4;b=b+1) begin
            idx=integer'(candidate_slots[b*SLOT_W+:SLOT_W]);
            if (candidate_valid[b] && legal[idx]) begin
                if (!force_valid || (2'(b)!=target_bank &&
                    (next_ops[idx*2+:2]==0 || next_ops[idx*2+:2]==3))) choices[idx]=1;
            end
        end
        for (integer i=0;i<Q_DEPTH;i=i+1)
            columns[i]=choices[i] && (next_ops[i*2+:2]==1 || next_ops[i*2+:2]==2);
        if (columns!=0) choices=columns;
        select_valid=0; select_slot=0;
        for (integer i=0;i<Q_DEPTH;i=i+1) begin
            has_older=0;
            for (integer j=0;j<Q_DEPTH;j=j+1)
                if (choices[j] && older[j*Q_DEPTH+i]) has_older=1;
            if (choices[i] && !has_older) begin select_valid=1; select_slot=SLOT_W'(i); end
        end
        if (force_valid && legal[service]) begin select_valid=1; select_slot=service; end
    end
    always @(posedge clk) begin
        if (rst) begin protected_valid<=0; protected_slot<=0; end
        else begin
            if (force_valid) begin protected_valid<=1; protected_slot<=target; end
            if (select_valid && select_slot==target &&
                (next_ops[integer'(select_slot)*2+:2]==1 || next_ops[integer'(select_slot)*2+:2]==2))
                protected_valid<=0;
        end
    end
endmodule
