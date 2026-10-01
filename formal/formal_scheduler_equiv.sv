// Sequential equivalence to the frozen scheduler, including aging state.
// No ordering, bank-match, uniqueness, or legal/pending relationship is assumed.
// The only input restriction is representable in-range slot indices.
module formal_scheduler_equiv(input wire clk);
    parameter integer Q_DEPTH=16, AGING_ENABLE=1;
    localparam integer SLOT_W=(Q_DEPTH>1 ? $clog2(Q_DEPTH) : 1);
    localparam integer ADDR_W=4, AGE_LIMIT=3, AGE_W=2;
    reg rst=1;
    always @(posedge clk) rst<=0;
    (* anyseq *) reg [Q_DEPTH-1:0] pending, legal;
    (* anyseq *) reg [Q_DEPTH*2-1:0] next_ops;
    (* anyseq *) reg [Q_DEPTH*ADDR_W-1:0] addresses;
    (* anyseq *) reg [Q_DEPTH*Q_DEPTH-1:0] older;
    (* anyseq *) reg [Q_DEPTH*AGE_W-1:0] ages;
    (* anyseq *) reg [3:0] candidate_valid, owner_valid;
    (* anyseq *) reg [4*SLOT_W-1:0] candidate_slots, owners;
    wire select_valid, protection_active, ref_select_valid, ref_protection_active;
    wire [SLOT_W-1:0] select_slot, protection_slot, ref_select_slot, ref_protection_slot;
    mc_scheduler_frfcfs #(.Q_DEPTH(Q_DEPTH),.ADDR_W(ADDR_W),.AGE_LIMIT(AGE_LIMIT),
        .AGING_ENABLE(AGING_ENABLE)) dut (.*);
    mc_scheduler_frfcfs_v1 #(.Q_DEPTH(Q_DEPTH),.ADDR_W(ADDR_W),.AGE_LIMIT(AGE_LIMIT),
        .AGING_ENABLE(AGING_ENABLE)) reference (
        .select_valid(ref_select_valid),.select_slot(ref_select_slot),
        .protection_active(ref_protection_active),.protection_slot(ref_protection_slot),.*);
    always @(posedge clk) begin
        for (integer b=0;b<4;b=b+1) begin
            assume (integer'(candidate_slots[b*SLOT_W+:SLOT_W])<Q_DEPTH);
            assume (integer'(owners[b*SLOT_W+:SLOT_W])<Q_DEPTH);
        end
        if (!rst) begin
            assert (select_valid==ref_select_valid);
            assert (select_slot==ref_select_slot);
            assert (protection_active==ref_protection_active);
            if (protection_active) assert (protection_slot==ref_protection_slot);
        end
    end
endmodule
