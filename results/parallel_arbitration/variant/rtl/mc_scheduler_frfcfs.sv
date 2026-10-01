module mc_scheduler_frfcfs #(
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
    input wire [3:0] owner_valid,
    input wire [Q_DEPTH-1:0] candidate_mask,
    input wire [4*SLOT_W-1:0] owners,
    output reg select_valid,
    output reg [Q_DEPTH-1:0] select_mask,
    output reg [SLOT_W-1:0] select_slot,
    output wire protection_active,
    output wire [SLOT_W-1:0] protection_slot
);
    reg protected_valid;
    reg [SLOT_W-1:0] protected_slot;
    reg oldest_valid, scan_older, force_valid;
    reg [SLOT_W-1:0] oldest_slot, target, service;
    reg [1:0] target_bank;
    reg [Q_DEPTH-1:0] eligible, columns, preparations, column_winners, prep_winners, winners;
    assign protection_active=force_valid;
    assign protection_slot=target;
    always @* begin
        oldest_valid=0; oldest_slot=0; scan_older=0;
        for (integer i=0;i<Q_DEPTH;i=i+1) begin
            scan_older=0;
            for (integer j=0;j<Q_DEPTH;j=j+1)
                if (pending[j] && older[j*Q_DEPTH+i]) scan_older=1;
            if (pending[i] && !scan_older) begin oldest_valid=1; oldest_slot=SLOT_W'(i); end
        end
        force_valid=(AGING_ENABLE!=0) && (protected_valid ||
            (oldest_valid && ages[integer'(oldest_slot)*AGE_W+:AGE_W]==AGE_W'(AGE_LIMIT)));
        target=protected_valid ? protected_slot : oldest_slot;
        target_bank=addresses[integer'(target)*ADDR_W+:2];
        service=owner_valid[target_bank] ? owners[integer'(target_bank)*SLOT_W+:SLOT_W] : target;
        eligible=0; columns=0; preparations=0;
        for (integer i=0;i<Q_DEPTH;i=i+1) begin
            if (candidate_mask[i] && legal[i] &&
                (!force_valid || (addresses[i*ADDR_W+:2]!=target_bank &&
                (next_ops[i*2+:2]==0 || next_ops[i*2+:2]==3)))) eligible[i]=1;
            columns[i]=eligible[i] && (next_ops[i*2+:2]==1 || next_ops[i*2+:2]==2);
            preparations[i]=eligible[i] && !columns[i];
        end
        // Arbitrate command classes independently before column-first selection.
        column_winners=0; prep_winners=0;
        for (integer i=0;i<Q_DEPTH;i=i+1) begin
            scan_older=0;
            for (integer j=0;j<Q_DEPTH;j=j+1)
                if (columns[j] && older[j*Q_DEPTH+i]) scan_older=1;
            column_winners[i]=columns[i] && !scan_older;
            scan_older=0;
            for (integer j=0;j<Q_DEPTH;j=j+1)
                if (preparations[j] && older[j*Q_DEPTH+i]) scan_older=1;
            prep_winners[i]=preparations[i] && !scan_older;
        end
        // Presence, not winner existence, preserves cyclic-order behavior.
        winners=(columns!=0) ? column_winners : prep_winners;
        select_valid=0; select_slot=0; select_mask=0;
        for (integer i=0;i<Q_DEPTH;i=i+1)
            if (winners[i]) begin select_valid=1; select_slot=SLOT_W'(i); end
        // Preserve last-assignment priority for incomparable winners.
        for (integer i=0;i<Q_DEPTH;i=i+1)
            select_mask[i]=winners[i] && ((winners >> (i+1))==0);
        // Command payloads still expose slot zero when no request is selected.
        if (winners==0) select_mask[0]=1;
        if (force_valid && legal[service]) begin
            select_valid=1; select_slot=service;
            for (integer i=0;i<Q_DEPTH;i=i+1)
                select_mask[i]=(service==SLOT_W'(i));
        end
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
