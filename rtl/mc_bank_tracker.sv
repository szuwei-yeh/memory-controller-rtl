module mc_bank_tracker #(
    parameter integer ROW_W=8, SLOT_W=4,
    parameter integer T_RCD=3, T_RP=3, T_RAS=6, T_CCD=2, T_WR=3
) (
    input wire clk, rst, issue_valid,
    input wire [1:0] issue_op, issue_bank,
    input wire [ROW_W-1:0] issue_row,
    input wire [SLOT_W-1:0] issue_slot,
    output reg [3:0] bank_open, owner_valid,
    output reg [4*ROW_W-1:0] open_rows,
    output reg [4*SLOT_W-1:0] owners,
    output wire [3:0] can_act, can_col, can_pre
);
    localparam integer RCD_W=(T_RCD>1 ? $clog2(T_RCD) : 1);
    localparam integer RP_W=(T_RP>1 ? $clog2(T_RP) : 1);
    localparam integer RAS_W=(T_RAS>1 ? $clog2(T_RAS) : 1);
    localparam integer CCD_W=(T_CCD>1 ? $clog2(T_CCD) : 1);
    localparam integer WR_W=(T_WR>1 ? $clog2(T_WR) : 1);
    reg [RCD_W-1:0] rcd [0:3];
    reg [RP_W-1:0] rp [0:3];
    reg [RAS_W-1:0] ras [0:3];
    reg [WR_W-1:0] wr [0:3];
    reg [CCD_W-1:0] ccd;
    for (genvar b=0; b<4; b=b+1) begin : legal
        assign can_act[b]=!bank_open[b] && rp[b]==0;
        assign can_col[b]=bank_open[b] && rcd[b]==0 && ccd==0;
        assign can_pre[b]=bank_open[b] && ras[b]==0 && wr[b]==0;
    end
    always @(posedge clk) begin
        if (rst) begin
            bank_open<=0; open_rows<=0; owner_valid<=0; owners<=0; ccd<=0;
            for (integer b=0;b<4;b=b+1) begin rcd[b]<=0; rp[b]<=0; ras[b]<=0; wr[b]<=0; end
        end else begin
            if (ccd!=0) ccd<=ccd-1'b1;
            for (integer b=0;b<4;b=b+1) begin
                if (rcd[b]!=0) rcd[b]<=rcd[b]-1'b1;
                if (rp[b]!=0) rp[b]<=rp[b]-1'b1;
                if (ras[b]!=0) ras[b]<=ras[b]-1'b1;
                if (wr[b]!=0) wr[b]<=wr[b]-1'b1;
            end
            if (issue_valid) begin
                case (issue_op)
                    2'd0: begin // ACT
                        bank_open[issue_bank]<=1;
                        open_rows[integer'(issue_bank)*ROW_W+:ROW_W]<=issue_row;
                        rcd[issue_bank]<=RCD_W'(T_RCD-1); ras[issue_bank]<=RAS_W'(T_RAS-1);
                        owner_valid[issue_bank]<=1;
                        owners[integer'(issue_bank)*SLOT_W+:SLOT_W]<=issue_slot;
                    end
                    2'd1, 2'd2: begin // READ, WRITE
                        ccd<=CCD_W'(T_CCD-1); owner_valid[issue_bank]<=0;
                        if (issue_op==2'd2) wr[issue_bank]<=WR_W'(T_WR-1);
                    end
                    2'd3: begin // PRE
                        bank_open[issue_bank]<=0; rp[issue_bank]<=RP_W'(T_RP-1);
                        owner_valid[issue_bank]<=1;
                        owners[integer'(issue_bank)*SLOT_W+:SLOT_W]<=issue_slot;
                    end
                endcase
            end
        end
    end
endmodule
