// Strict Request FCFS: a blocked oldest request stalls the entire command bus.
module mc_scheduler_strict_fcfs #(
    parameter integer Q_DEPTH=16, SLOT_W=(Q_DEPTH>1 ? $clog2(Q_DEPTH) : 1)
) (
    input wire [Q_DEPTH-1:0] pending, legal,
    input wire [Q_DEPTH*Q_DEPTH-1:0] older,
    output reg select_valid,
    output reg [SLOT_W-1:0] select_slot
);
    reg has_older;
    always @* begin
        select_valid=0; select_slot=0; has_older=0;
        for (integer i=0;i<Q_DEPTH;i=i+1) begin
            has_older=0;
            for (integer j=0;j<Q_DEPTH;j=j+1)
                if (pending[j] && older[j*Q_DEPTH+i]) has_older=1;
            if (pending[i] && !has_older) begin
                select_slot=SLOT_W'(i); select_valid=legal[i];
            end
        end
    end
endmodule
