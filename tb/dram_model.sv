// Simulation only. Timing is checked with independent event timestamps.
module dram_model #(
    parameter integer ROWS=256, COLS=64, DATA_W=32, READ_LATENCY=3,
    parameter integer T_RCD=3, T_RP=3, T_RAS=6, T_CCD=2, T_WR=3,
    parameter integer ROW_W=$clog2(ROWS), COL_W=$clog2(COLS)
) (
    input wire clk, rst, cmd_valid,
    input wire [1:0] cmd_op, cmd_bank,
    input wire [ROW_W-1:0] cmd_row,
    input wire [COL_W-1:0] cmd_col,
    input wire [DATA_W-1:0] cmd_wdata,
    output wire rd_valid,
    output wire [DATA_W-1:0] rd_data
);
    reg [DATA_W-1:0] memory [0:4*ROWS*COLS-1];
    reg [3:0] opened;
    integer row [0:3];
    integer last_act [0:3], last_pre [0:3], last_write [0:3];
    integer last_column, cycle, address;
    reg [READ_LATENCY-1:0] valid_pipe;
    reg [DATA_W-1:0] data_pipe [0:READ_LATENCY-1];
    assign rd_valid=valid_pipe[READ_LATENCY-1] && !rst;
    assign rd_data=data_pipe[READ_LATENCY-1];
    initial begin
        for (integer a=0;a<4*ROWS*COLS;a=a+1)
            memory[a]=DATA_W'(32'(a)*32'h9e3779b9 ^ 32'h51c0ffee);
    end
    always @(posedge clk) begin
        if (rst) begin
            cycle=0; opened=0; last_column=-1000000; valid_pipe<=0;
            for (integer b=0;b<4;b=b+1) begin
                row[b]=0; last_act[b]=-1000000; last_pre[b]=-1000000; last_write[b]=-1000000;
            end
            for (integer k=0;k<READ_LATENCY;k=k+1) data_pipe[k]<=0;
        end else begin
            valid_pipe[0]<=0;
            for (integer k=1;k<READ_LATENCY;k=k+1) begin
                valid_pipe[k]<=valid_pipe[k-1]; data_pipe[k]<=data_pipe[k-1];
            end
            if (cmd_valid) begin
                address=(integer'(cmd_row)*COLS+integer'(cmd_col))*4+integer'(cmd_bank);
                case (cmd_op)
                    0: begin
                        if (opened[cmd_bank]) $fatal(1,"MODEL ACT open bank");
                        if (cycle-last_pre[cmd_bank]<T_RP) $fatal(1,"MODEL tRP");
                        opened[cmd_bank]=1; row[cmd_bank]=integer'(cmd_row); last_act[cmd_bank]=cycle;
                    end
                    1,2: begin
                        if (!opened[cmd_bank] || row[cmd_bank]!=integer'(cmd_row)) $fatal(1,"MODEL wrong row");
                        if (cycle-last_act[cmd_bank]<T_RCD) $fatal(1,"MODEL tRCD");
                        if (cycle-last_column<T_CCD) $fatal(1,"MODEL tCCD");
                        last_column=cycle;
                        if (cmd_op==2) begin memory[address]=cmd_wdata; last_write[cmd_bank]=cycle; end
                        else begin valid_pipe[0]<=1; data_pipe[0]<=memory[address]; end
                    end
                    3: begin
                        if (!opened[cmd_bank]) $fatal(1,"MODEL PRE closed bank");
                        if (cycle-last_act[cmd_bank]<T_RAS) $fatal(1,"MODEL tRAS");
                        if (cycle-last_write[cmd_bank]<T_WR) $fatal(1,"MODEL tWR");
                        opened[cmd_bank]=0; last_pre[cmd_bank]=cycle;
                    end
                endcase
            end
            cycle=cycle+1;
        end
    end
endmodule
