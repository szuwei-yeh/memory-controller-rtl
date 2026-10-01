module mc_transaction_table #(
    parameter integer Q_DEPTH=16, ADDR_W=16, DATA_W=32, TAG_W=8,
    parameter integer READ_LATENCY=3, AGE_LIMIT=128,
    parameter integer SLOT_W=(Q_DEPTH>1 ? $clog2(Q_DEPTH) : 1),
    parameter integer AGE_W=(AGE_LIMIT>0 ? $clog2(AGE_LIMIT+1) : 1)
) (
    input wire clk, rst,
    input wire req_valid, req_write,
    output wire req_ready,
    input wire [ADDR_W-1:0] req_addr,
    input wire [DATA_W-1:0] req_wdata,
    input wire [TAG_W-1:0] req_tag,
    input wire issue_valid,
    input wire [SLOT_W-1:0] issue_slot,
    input wire rd_valid,
    input wire [DATA_W-1:0] rd_data,
    input wire retire_valid,
    input wire [SLOT_W-1:0] retire_slot,
    output reg [Q_DEPTH-1:0] occupied, pending, done, writes,
    output reg [Q_DEPTH*ADDR_W-1:0] addresses,
    output reg [Q_DEPTH*DATA_W-1:0] write_data, read_data,
    output reg [Q_DEPTH*TAG_W-1:0] tags,
    output reg [Q_DEPTH*Q_DEPTH-1:0] older,
    output reg [Q_DEPTH*AGE_W-1:0] ages
);
    reg free_valid;
    reg [SLOT_W-1:0] free_slot;
    reg [READ_LATENCY-1:0] return_valid;
    reg [SLOT_W-1:0] return_slot [0:READ_LATENCY-1];
    always @* begin
        free_valid=0; free_slot=0;
        for (integer i=0; i<Q_DEPTH; i=i+1)
            if (!occupied[i] && !free_valid) begin
                free_valid=1; free_slot=SLOT_W'(i);
            end
    end
    assign req_ready=free_valid && !rst;
`ifdef FORMAL
    always @(posedge clk) if (!rst) begin
        assert ((pending & ~occupied)==0);
        assert ((done & ~occupied)==0);
        assert ((done & pending)==0);
        assert (rd_valid==return_valid[READ_LATENCY-1]);
        if (issue_valid) assert (pending[issue_slot]);
        if (retire_valid) assert (done[retire_slot]);
        for (integer i=0;i<Q_DEPTH;i=i+1) begin
            assert (!older[i*Q_DEPTH+i]);
            for (integer j=i+1;j<Q_DEPTH;j=j+1)
                if (occupied[i] && occupied[j]) assert (older[i*Q_DEPTH+j] != older[j*Q_DEPTH+i]);
        end
    end
`endif
    always @(posedge clk) begin
        if (rst) begin
            occupied<=0; pending<=0; done<=0; writes<=0;
            addresses<=0; write_data<=0; read_data<=0; tags<=0;
            older<=0; ages<=0; return_valid<=0;
            for (integer k=0; k<READ_LATENCY; k=k+1) return_slot[k]<=0;
        end else begin
            return_valid[0]<=issue_valid && !writes[issue_slot];
            return_slot[0]<=issue_slot;
            for (integer k=1; k<READ_LATENCY; k=k+1) begin
                return_valid[k]<=return_valid[k-1];
                return_slot[k]<=return_slot[k-1];
            end
            for (integer i=0; i<Q_DEPTH; i=i+1)
                if (pending[i] && ages[i*AGE_W+:AGE_W]<AGE_W'(AGE_LIMIT))
                    ages[i*AGE_W+:AGE_W]<=ages[i*AGE_W+:AGE_W]+1'b1;
            if (retire_valid) begin
                occupied[retire_slot]<=0; pending[retire_slot]<=0;
                for (integer j=0; j<Q_DEPTH; j=j+1) begin
                    older[integer'(retire_slot)*Q_DEPTH+j]<=0;
                    older[j*Q_DEPTH+integer'(retire_slot)]<=0;
                end
            end
            if (req_valid && req_ready) begin
                occupied[free_slot]<=1; pending[free_slot]<=1;
                writes[free_slot]<=req_write;
                addresses[integer'(free_slot)*ADDR_W+:ADDR_W]<=req_addr;
                write_data[integer'(free_slot)*DATA_W+:DATA_W]<=req_wdata;
                tags[integer'(free_slot)*TAG_W+:TAG_W]<=req_tag;
                ages[integer'(free_slot)*AGE_W+:AGE_W]<=0;
                for (integer j=0; j<Q_DEPTH; j=j+1) begin
                    older[integer'(free_slot)*Q_DEPTH+j]<=0;
                    older[j*Q_DEPTH+integer'(free_slot)]<=occupied[j] &&
                        !(retire_valid && retire_slot==SLOT_W'(j));
                end
            end
            if (issue_valid) begin
                pending[issue_slot]<=0;
            end
            // Decode writes at each fixed slot; preserve retire < allocate <
            // write issue < read return priority when events coincide.
            for (integer i=0; i<Q_DEPTH; i=i+1) begin
                if (retire_valid && retire_slot==SLOT_W'(i)) done[i]<=0;
                if (req_valid && req_ready && free_slot==SLOT_W'(i)) begin
                    done[i]<=0;
                    read_data[i*DATA_W+:DATA_W]<=0;
                end
                if (issue_valid && issue_slot==SLOT_W'(i) && writes[i]) begin
                    done[i]<=1;
                    read_data[i*DATA_W+:DATA_W]<=0;
                end
                if (rd_valid && return_valid[READ_LATENCY-1] &&
                    return_slot[READ_LATENCY-1]==SLOT_W'(i)) begin
                    done[i]<=1;
                    read_data[i*DATA_W+:DATA_W]<=rd_data;
                end
            end
`ifndef SYNTHESIS
            assert (rd_valid==return_valid[READ_LATENCY-1]) else $fatal(1,"read return latency");
            if (issue_valid) assert (pending[issue_slot]) else $fatal(1,"issue nonpending");
            if (retire_valid) assert (done[retire_slot]) else $fatal(1,"retire incomplete");
            if (req_valid && req_ready)
                for (integer j=0; j<Q_DEPTH; j=j+1)
                    if (occupied[j]) assert (tags[j*TAG_W+:TAG_W]!=req_tag)
                        else $fatal(1,"duplicate outstanding tag");
`endif
        end
    end
endmodule
