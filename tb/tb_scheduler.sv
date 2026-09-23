`timescale 1ns/1ps
// Explicitly exercise the defensive existing-owner branch of aging arbitration.
module tb_scheduler;
    reg clk=0;
    always #5 clk=~clk;
    reg rst=1;
    reg [2:0] pending=0, legal=0;
    reg [5:0] next_ops=0;
    reg [11:0] addresses=0;
    reg [8:0] older=0;
    reg [5:0] ages=0;
    reg [3:0] candidate_valid=0, owner_valid=0;
    reg [7:0] candidate_slots=0, owners=0;
    wire select_valid, protection_active;
    wire [1:0] select_slot, protection_slot;
    mc_scheduler_frfcfs #(.Q_DEPTH(3),.ADDR_W(4),.AGE_LIMIT(2)) dut (.*);
    task automatic check(input bit valid, input reg [1:0] slot);
        @(posedge clk);
        if (select_valid!=valid || (valid && select_slot!=slot))
            $fatal(1,"directed scheduler expected valid=%0d slot=%0d, got %0d/%0d",valid,slot,select_valid,select_slot);
        @(negedge clk);
    endtask
    initial begin
        repeat (2) @(negedge clk); rst=0;
        // 0 is oldest conflict in bank 0; 1 is its younger existing owner;
        // 2 is an unrelated bank-1 row hit. Only owner 1 may consume tCCD.
        pending=3'b111; older[1]=1; older[2]=1; older[5]=1;
        addresses[0+:4]=4'b1000; addresses[4+:4]=0; addresses[8+:4]=1;
        ages[0+:2]=2; next_ops[0+:2]=3; next_ops[2+:2]=1; next_ops[4+:2]=1;
        owner_valid=1; owners[0+:2]=1;
        candidate_valid=3; candidate_slots[0+:2]=1; candidate_slots[2+:2]=2;
        legal=3'b110;
        check(1,1);
        // Owner completed; protected conflict waits. Unrelated READ is suppressed.
        pending=3'b101; owner_valid=0; candidate_slots[0+:2]=0; legal=3'b100;
        check(0,0);
        // An unrelated ACT may use an otherwise idle cycle.
        next_ops[4+:2]=0;
        check(1,2);
        // Protected PRE takes priority when ready, then ACT, then column command.
        legal=3'b101;
        check(1,0);
        next_ops[0+:2]=0; check(1,0);
        next_ops[0+:2]=2; check(1,0);
        pending=3'b100; ages=0; legal=3'b100; candidate_valid=2;
        next_ops[4+:2]=1;
        check(1,2);
        if (protection_active) $fatal(1,"protection did not release");
        $display("PASS aging existing-owner drain, column suppression, preparation bypass and release");
        $finish;
    end
endmodule
