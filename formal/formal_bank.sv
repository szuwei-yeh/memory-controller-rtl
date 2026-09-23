module formal_bank(input wire clk);
    reg rst=1;
    always @(posedge clk) rst<=0;
    (* anyseq *) reg issue_valid;
    (* anyseq *) reg [1:0] issue_op, issue_bank;
    (* anyseq *) reg issue_row, issue_slot;
    wire [3:0] bank_open, owner_valid, can_act, can_col, can_pre, open_rows, owners;
    mc_bank_tracker #(.ROW_W(1),.SLOT_W(1),.T_RCD(3),.T_RP(2),.T_RAS(4),.T_CCD(2),.T_WR(3)) dut (.*);
    reg [3:0] reference_open, reference_row;
    reg [3:0] age_act [0:3], age_pre [0:3], age_write [0:3];
    reg [3:0] age_col;
    always @(posedge clk) begin
        if (rst) begin
            reference_open<=0; reference_row<=0; age_col<=15;
            for (integer b=0;b<4;b=b+1) begin age_act[b]<=15; age_pre[b]<=15; age_write[b]<=15; end
        end else begin
            assert (bank_open==reference_open);
            for (integer b=0;b<4;b=b+1) begin
                assert (can_act[b]==(!reference_open[b] && age_pre[b]>=2));
                assert (can_col[b]==(reference_open[b] && age_act[b]>=3 && age_col>=2));
                assert (can_pre[b]==(reference_open[b] && age_act[b]>=4 && age_write[b]>=3));
                if (reference_open[b]) assert (open_rows[b]==reference_row[b]);
                if (age_act[b]!=15) age_act[b]<=age_act[b]+1'b1;
                if (age_pre[b]!=15) age_pre[b]<=age_pre[b]+1'b1;
                if (age_write[b]!=15) age_write[b]<=age_write[b]+1'b1;
            end
            if (age_col!=15) age_col<=age_col+1'b1;
            if (issue_valid) begin
                if (owner_valid[issue_bank]) assume (issue_slot==owners[issue_bank]);
                case (issue_op)
                    0: begin
                        assume (can_act[issue_bank]); reference_open[issue_bank]<=1;
                        reference_row[issue_bank]<=issue_row; age_act[issue_bank]<=1;
                    end
                    1,2: begin
                        assume (can_col[issue_bank]); assume (issue_row==open_rows[issue_bank]);
                        age_col<=1; if (issue_op==2) age_write[issue_bank]<=1;
                    end
                    3: begin assume (can_pre[issue_bank]); reference_open[issue_bank]<=0; age_pre[issue_bank]<=1; end
                endcase
            end
        end
    end
endmodule
