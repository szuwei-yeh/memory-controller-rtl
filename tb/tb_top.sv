`timescale 1ns/1ps
module tb_top;
    parameter integer ROWS=8, COLS=8, Q_DEPTH=16, READ_LATENCY=3;
    parameter integer T_RCD=3, T_RP=3, T_RAS=6, T_CCD=2, T_WR=3;
    parameter integer SCHED_POLICY=1, AGING_ENABLE=1, AGE_LIMIT=128;
    localparam integer ROW_W=$clog2(ROWS), COL_W=$clog2(COLS), ADDR_W=ROW_W+COL_W+2;
    localparam integer TB_TAGS=Q_DEPTH+1;
    localparam integer MEM_WORDS=4*ROWS*COLS;
    localparam integer SERVICE_BOUND=AGE_LIMIT+2*Q_DEPTH*(T_RAS+T_WR+T_RP+T_RCD+T_CCD+8);
    reg clk=0;
    always #5 clk=~clk;
    reg rst=1, req_valid=0, req_write=0, rsp_ready=1;
    reg [ADDR_W-1:0] req_addr=0;
    reg [31:0] req_wdata=0;
    reg [7:0] req_tag=0;
    wire req_ready, rsp_valid, rsp_write, cmd_valid, rd_valid;
    wire [7:0] rsp_tag;
    wire [31:0] rsp_rdata, cmd_wdata, rd_data;
    wire [1:0] cmd_op, cmd_bank;
    wire [ROW_W-1:0] cmd_row;
    wire [COL_W-1:0] cmd_col;
    mc_top #(.ROWS(ROWS),.COLS(COLS),.Q_DEPTH(Q_DEPTH),.READ_LATENCY(READ_LATENCY),
        .T_RCD(T_RCD),.T_RP(T_RP),.T_RAS(T_RAS),.T_CCD(T_CCD),.T_WR(T_WR),
        .SCHED_POLICY(SCHED_POLICY),.AGING_ENABLE(AGING_ENABLE),.AGE_LIMIT(AGE_LIMIT)) dut (.*);
    dram_model #(.ROWS(ROWS),.COLS(COLS),.READ_LATENCY(READ_LATENCY),
        .T_RCD(T_RCD),.T_RP(T_RP),.T_RAS(T_RAS),.T_CCD(T_CCD),.T_WR(T_WR)) memory_i (.*);

    reg [31:0] ref_mem [0:MEM_WORDS-1];
    bit busy [0:TB_TAGS-1], unissued [0:TB_TAGS-1], is_write [0:TB_TAGS-1];
    integer addr [0:TB_TAGS-1], seqno [0:TB_TAGS-1], accepted_at [0:TB_TAGS-1], issued_at [0:TB_TAGS-1];
    integer completed_at [0:TB_TAGS-1], eligible_at [0:TB_TAGS-1], presented_at [0:TB_TAGS-1], offered_at [0:TB_TAGS-1];
    reg [31:0] expected_data [0:TB_TAGS-1], write_value [0:TB_TAGS-1];
    integer first_kind [0:TB_TAGS-1];
    bit opened [0:3];
    integer rows [0:3], owner [0:3], act_at [0:3], pre_at [0:3], write_at [0:3];
    integer col_at, cycle=0, next_seq=0, accepted=0, responded=0, outstanding=0;
    integer protected_tag=-1, protected_start=0;
    integer trace_fd=0, trace_offer=0;
    integer cycles_full=0, commands [0:3], protections=0, max_wait=0;
    integer same_addr_block=0, independent_bypass=0, read_write_overlap=0, full_seen=0;
    integer bank_overlap=0, idle_empty=0, idle_timing=0, idle_policy=0, idle_dependency=0;
    integer protected_owner_block=0;
    longint occupancy_sum=0;
    bit held_response=0;
    reg [40:0] held_payload;
    integer last_consumed_seq [0:MEM_WORDS-1];
    integer seed=1, total=10000, workload=3, load_pct=100, ready_pct=80, warmup=0;
    integer offer_interval=1;
    string trace_path;
    reg [31:0] random_state=1;
    bit reset_test=0;

    function automatic integer bank_of(input integer a); return a%4; endfunction
    function automatic integer row_of(input integer a); return a/(4*COLS); endfunction
    function automatic bit dependency_free(input integer t);
        bit ok;
        ok=1;
        for (integer j=0;j<TB_TAGS;j=j+1)
            if (busy[j] && unissued[j] && addr[j]==addr[t] && seqno[j]<seqno[t]) ok=0;
        return ok;
    endfunction
    function automatic integer operation(input integer t);
        integer b;
        b=bank_of(addr[t]);
        if (!opened[b]) return 0;
        if (rows[b]!=row_of(addr[t])) return 3;
        return is_write[t] ? 2 : 1;
    endfunction
    function automatic bit ready_command(input integer t);
        integer b, op;
        if (t<0) return 0;
        b=bank_of(addr[t]); op=operation(t);
        if (!unissued[t] || !dependency_free(t) || (owner[b]>=0 && owner[b]!=t)) return 0;
        case (op)
            0: return cycle-pre_at[b]>=T_RP;
            1,2: return cycle-act_at[b]>=T_RCD && cycle-col_at>=T_CCD;
            3: return cycle-act_at[b]>=T_RAS && cycle-write_at[b]>=T_WR;
        endcase
        return 0;
    endfunction
    function automatic bit timing_ready(input integer t);
        integer b;
        b=bank_of(addr[t]);
        case (operation(t))
            0: return cycle-pre_at[b]>=T_RP;
            1,2: return cycle-act_at[b]>=T_RCD && cycle-col_at>=T_CCD;
            3: return cycle-act_at[b]>=T_RAS && cycle-write_at[b]>=T_WR;
        endcase
        return 0;
    endfunction
    function automatic integer older_tag(input integer a, input integer b);
        if (a<0) return b;
        if (b<0) return a;
        return seqno[a]<seqno[b] ? a : b;
    endfunction
    function automatic reg [31:0] rnd();
        random_state=random_state ^ (random_state<<13);
        random_state=random_state ^ (random_state>>17);
        random_state=random_state ^ (random_state<<5);
        return random_state;
    endfunction

    // Independent scheduler/reference state: no DUT timing or eligibility signals.
    always @(posedge clk) begin : scoreboard
        integer oldest, expected_tag, best_col, best_prep, candidate, best_hit, best_any;
        integer target, service, bank, actual, op, return_tag, active_banks, open_mask, owner_mask, idle_reason;
        bit force_mode, blocked, timing_possible;
        if (rst) begin
            outstanding=0; protected_tag=-1; cycle=0; col_at=-1000000; held_response=0;
            accepted=0; responded=0; next_seq=0;
            for (integer t=0;t<TB_TAGS;t=t+1) begin
                busy[t]=0; unissued[t]=0; completed_at[t]=-1; eligible_at[t]=-1; presented_at[t]=-1;
            end
            for (integer b=0;b<4;b=b+1) begin
                opened[b]=0; rows[b]=0; owner[b]=-1;
                act_at[b]=-1000000; pre_at[b]=-1000000; write_at[b]=-1000000;
            end
            for (integer a=0;a<MEM_WORDS;a=a+1) last_consumed_seq[a]=-1;
        end else begin
            oldest=-1; best_col=-1; best_prep=-1; expected_tag=-1;
            for (integer t=0;t<TB_TAGS;t=t+1)
                if (busy[t] && unissued[t]) oldest=older_tag(oldest,t);
            target=protected_tag;
            if (target<0 && oldest>=0 && cycle-accepted_at[oldest]-1>=AGE_LIMIT) target=oldest;
            force_mode=SCHED_POLICY==1 && AGING_ENABLE!=0 && target>=0;
            if (force_mode && protected_tag<0) begin
                protections=protections+1; protected_start=cycle;
                if (owner[bank_of(addr[target])]>=0 && owner[bank_of(addr[target])]!=target)
                    protected_owner_block=protected_owner_block+1;
                if (trace_fd!=0) $fdisplay(trace_fd,"P,%0d,%0d",cycle,seqno[target]);
            end
            if (SCHED_POLICY==0) begin
                if (oldest>=0 && ready_command(oldest)) expected_tag=oldest;
            end else begin
                for (integer b=0;b<4;b=b+1) begin
                    best_hit=-1; best_any=-1;
                    for (integer t=0;t<TB_TAGS;t=t+1)
                        if (busy[t] && unissued[t] && bank_of(addr[t])==b && dependency_free(t) &&
                            (owner[b]<0 || owner[b]==t)) begin
                            best_any=older_tag(best_any,t);
                            if (opened[b] && rows[b]==row_of(addr[t])) best_hit=older_tag(best_hit,t);
                        end
                    candidate=(best_hit>=0) ? best_hit : best_any;
                    if (candidate>=0 && ready_command(candidate)) begin
                        op=operation(candidate);
                        if (!force_mode || (b!=bank_of(addr[target]) && (op==0 || op==3))) begin
                            if (op==1 || op==2) best_col=older_tag(best_col,candidate);
                            else best_prep=older_tag(best_prep,candidate);
                        end
                    end
                end
                expected_tag=(best_col>=0) ? best_col : best_prep;
                if (force_mode) begin
                    bank=bank_of(addr[target]); service=owner[bank]>=0 ? owner[bank] : target;
                    if (ready_command(service)) expected_tag=service;
                end
            end
            if (cmd_valid != (expected_tag>=0))
                $fatal(1,"scheduler validity cycle=%0d expected_tag=%0d valid=%0d",cycle,expected_tag,cmd_valid);
            if (cmd_valid) begin
                actual=integer'(dut.tags[integer'(dut.select_slot)*8+:8]);
                if (actual!=expected_tag || integer'(cmd_op)!=operation(expected_tag))
                    $fatal(1,"scheduler choice cycle=%0d actual=%0d expected=%0d",cycle,actual,expected_tag);
                if ({cmd_row,cmd_col,cmd_bank}!=ADDR_W'(addr[actual])) $fatal(1,"command address");
                if (cmd_op==2 && cmd_wdata!=write_value[actual]) $fatal(1,"command write payload");
            end
            if (held_response && (!rsp_valid || {rsp_tag,rsp_write,rsp_rdata}!=held_payload))
                $fatal(1,"response changed under backpressure");
            held_response=rsp_valid && !rsp_ready;
            held_payload={rsp_tag,rsp_write,rsp_rdata};
            if (rsp_valid) begin
                actual=integer'(rsp_tag);
                if (!busy[actual] || completed_at[actual]<0) $fatal(1,"unknown or incomplete response");
                for (integer j=0;j<TB_TAGS;j=j+1)
                    if (busy[j] && addr[j]==addr[actual] && seqno[j]<seqno[actual])
                        $fatal(1,"same-address response bypass");
                if (presented_at[actual]<0) presented_at[actual]=cycle;
                if (rsp_write!=is_write[actual] || rsp_rdata!=expected_data[actual])
                    $fatal(1,"response data tag=%0d got=%h expected=%h",actual,rsp_rdata,expected_data[actual]);
                if (rsp_ready) begin
                    if (seqno[actual]<=last_consumed_seq[addr[actual]]) $fatal(1,"response sequence");
                    for (integer j=0;j<TB_TAGS;j=j+1)
                        if (busy[j] && seqno[j]<seqno[actual]) independent_bypass=independent_bypass+1;
                    last_consumed_seq[addr[actual]]=seqno[actual];
                    if (trace_fd!=0) $fdisplay(trace_fd,"R,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d",
                        cycle,seqno[actual],addr[actual],is_write[actual],offered_at[actual],accepted_at[actual],
                        issued_at[actual],completed_at[actual],eligible_at[actual],presented_at[actual],first_kind[actual]);
                    busy[actual]=0; outstanding=outstanding-1; responded=responded+1;
                end
            end
            return_tag=-1;
            for (integer t=0;t<TB_TAGS;t=t+1)
                if (busy[t] && !unissued[t] && !is_write[t] && issued_at[t]+READ_LATENCY==cycle) begin
                    if (return_tag>=0) $fatal(1,"two read returns");
                    return_tag=t;
                end
            if (rd_valid != (return_tag>=0)) $fatal(1,"independent read latency");
            if (rd_valid) begin
                if (rd_data!=expected_data[return_tag]) $fatal(1,"read snapshot mismatch");
                completed_at[return_tag]=cycle;
                if (trace_fd!=0) $fdisplay(trace_fd,"D,%0d,%0d",cycle,seqno[return_tag]);
                if (cmd_valid && cmd_op==2) read_write_overlap=read_write_overlap+1;
            end
            if (force_mode) protected_tag=target;
            if (cmd_valid) begin
                actual=expected_tag; bank=bank_of(addr[actual]); op=integer'(cmd_op);
                commands[op]=commands[op]+1;
                if (first_kind[actual]<0) first_kind[actual]=(op==0) ? 1 : ((op==3) ? 2 : 0);
                if (trace_fd!=0) $fdisplay(trace_fd,"C,%0d,%0d,%0d,%0d,%0d",cycle,seqno[actual],op,bank,row_of(addr[actual]));
                case (op)
                    0: begin opened[bank]=1; rows[bank]=row_of(addr[actual]); act_at[bank]=cycle; owner[bank]=actual; end
                    3: begin opened[bank]=0; pre_at[bank]=cycle; owner[bank]=actual; end
                    1,2: begin
                        unissued[actual]=0; issued_at[actual]=cycle; col_at=cycle; owner[bank]=-1;
                        if (op==2) begin
                            completed_at[actual]=cycle; write_at[bank]=cycle;
                            if (trace_fd!=0) $fdisplay(trace_fd,"D,%0d,%0d",cycle,seqno[actual]);
                        end
                        if (cycle-accepted_at[actual]>max_wait) max_wait=cycle-accepted_at[actual];
                        if (force_mode && actual==target) begin
                            if (cycle-protected_start>2*(T_RAS+T_WR+T_RP+T_RCD+T_CCD+8)) $fatal(1,"protected bound");
                            if (trace_fd!=0) $fdisplay(trace_fd,"E,%0d,%0d,%0d",cycle,seqno[actual],cycle-protected_start);
                            protected_tag=-1;
                        end
                    end
                endcase
            end else begin
                blocked=0; timing_possible=0;
                for (integer t=0;t<TB_TAGS;t=t+1)
                    if (busy[t] && unissued[t]) begin
                        if (ready_command(t)) blocked=1;
                        if (timing_ready(t)) timing_possible=1;
                    end
                if (oldest<0) begin idle_empty=idle_empty+1; idle_reason=0; end
                else if (blocked) begin idle_policy=idle_policy+1; idle_reason=2; end
                else if (timing_possible) begin idle_dependency=idle_dependency+1; idle_reason=3; end
                else begin idle_timing=idle_timing+1; idle_reason=1; end
                if (trace_fd!=0) $fdisplay(trace_fd,"I,%0d,%0d",cycle,idle_reason);
            end
            if (req_valid && req_ready) begin
                actual=integer'(req_tag);
                if (busy[actual]) $fatal(1,"tag reused early");
                busy[actual]=1; unissued[actual]=1; is_write[actual]=req_write;
                addr[actual]=integer'(req_addr); seqno[actual]=next_seq; next_seq=next_seq+1;
                accepted_at[actual]=cycle; offered_at[actual]=trace_offer;
                issued_at[actual]=-1; completed_at[actual]=-1; eligible_at[actual]=-1;
                presented_at[actual]=-1; first_kind[actual]=-1; write_value[actual]=req_wdata;
                expected_data[actual]=req_write ? 0 : ref_mem[req_addr];
                if (req_write) ref_mem[req_addr]=req_wdata;
                accepted=accepted+1; outstanding=outstanding+1;
                if (trace_fd!=0) $fdisplay(trace_fd,"A,%0d,%0d,%0d,%0d",cycle,seqno[actual],addr[actual],req_write);
            end
            for (integer t=0;t<TB_TAGS;t=t+1) begin
                if (busy[t] && unissued[t] && (SCHED_POLICY==0 || AGING_ENABLE!=0) &&
                    cycle-accepted_at[t]>SERVICE_BOUND) $fatal(1,"accepted request service bound");
                if (busy[t] && completed_at[t]>=0 && eligible_at[t]<0) begin
                    blocked=0;
                    for (integer j=0;j<TB_TAGS;j=j+1)
                        if (busy[j] && addr[j]==addr[t] && seqno[j]<seqno[t]) blocked=1;
                    if (!blocked) eligible_at[t]=cycle;
                    else same_addr_block=same_addr_block+1;
                end
            end
            if (outstanding>Q_DEPTH || outstanding<0) $fatal(1,"capacity");
            occupancy_sum=occupancy_sum+64'(outstanding);
            if (outstanding==Q_DEPTH) begin cycles_full=cycles_full+1; full_seen=1; end
            active_banks=0; open_mask=0; owner_mask=0;
            for (integer b=0;b<4;b=b+1) begin
                if (owner[b]>=0) begin active_banks=active_banks+1; owner_mask=owner_mask | (1<<b); end
                if (opened[b]) open_mask=open_mask | (1<<b);
            end
            if (active_banks>1) bank_overlap=bank_overlap+1;
            if (trace_fd!=0) $fdisplay(trace_fd,"O,%0d,%0d,%0d,%0d,%0d",cycle,outstanding,active_banks,open_mask,owner_mask);
            cycle=cycle+1;
        end
    end

    task automatic send_request(input integer a, input bit wr, input reg [31:0] data);
        integer tag;
        tag=-1;
        while (tag<0) begin
            @(negedge clk);
            for (integer t=TB_TAGS-1;t>=0;t=t-1) if (!busy[t]) tag=t;
        end
        req_valid=1; req_addr=ADDR_W'(a); req_write=wr; req_wdata=data; req_tag=8'(tag);
        trace_offer=cycle;
        do @(posedge clk); while (!req_ready);
        @(negedge clk); req_valid=0;
    endtask
    task automatic drain;
        integer waited;
        waited=0;
        while (outstanding!=0) begin
            @(negedge clk); waited=waited+1;
            if (waited>100000) $fatal(1,"drain timeout");
        end
    endtask

    initial begin : stimulus
        integer tag, sent, a, next_offer, value;
        bit wr, handshake;
        void'($value$plusargs("seed=%d",seed));
        void'($value$plusargs("n=%d",total));
        void'($value$plusargs("workload=%d",workload));
        void'($value$plusargs("load=%d",load_pct));
        void'($value$plusargs("ready=%d",ready_pct));
        void'($value$plusargs("warmup=%d",warmup));
        void'($value$plusargs("interval=%d",offer_interval));
        reset_test=$test$plusargs("reset_test");
        random_state=32'(seed); if (random_state==0) random_state=1;
        if ($value$plusargs("trace=%s",trace_path)) begin
            trace_fd=$fopen(trace_path,"w"); if (trace_fd==0) $fatal(1,"trace open failed");
        end
        for (integer a0=0;a0<MEM_WORDS;a0=a0+1) ref_mem[a0]=32'(a0)*32'h9e3779b9 ^ 32'h51c0ffee;
        for (integer op=0;op<4;op=op+1) commands[op]=0;
        repeat (4) @(negedge clk);
        rst=0;
        // Directed ordering, row conflict, interbank work, held-response pressure.
        rsp_ready=0;
        fork
            begin repeat (150) @(negedge clk); rsp_ready=1; end
            begin
                send_request(0,0,0);
                send_request(0,1,32'd7);
                send_request(0,0,0);
                send_request(0,1,32'd9);
                send_request(1,1,32'h12345678);
                send_request(1,0,0);
                send_request(4*COLS,1,32'h87654321);
                send_request(4*COLS,0,0);
                send_request(2,0,0);
                send_request(3,0,0);
            end
        join
        drain();
        if (reset_test) begin
            send_request(0,1,32'haabbccdd); drain();
            rsp_ready=0;
            send_request(0,0,0); send_request(4*COLS,0,0);
            repeat (2) @(negedge clk);
            rst=1; req_valid=0;
            repeat (3) @(negedge clk);
            // Synchronize the acceptance-order model to actual committed storage after cancellation.
            for (integer x=0;x<MEM_WORDS;x=x+1) ref_mem[x]=memory_i.memory[x];
            rst=0; rsp_ready=1;
            send_request(0,0,0); drain();
        end
        sent=0; next_offer=cycle;
        // Use sequence-indexed traffic RNG; response backpressure uses deterministic cycle patterns.
        @(negedge clk);
        while (sent<total+warmup) begin
            rsp_ready=(cycle%100)<ready_pct;
            if (cycle>=next_offer && (cycle%100)<load_pct) begin
                tag=-1;
                for (integer t=TB_TAGS-1;t>=0;t=t-1) if (!busy[t]) tag=t;
                if (tag>=0) begin
                    value=integer'(rnd() & 32'h7fffffff);
                    wr=(sent%4)==0;
                    case (workload)
                        0: a=(sent%COLS)*4; // same-row bank 0
                        1: a=sent%MEM_WORDS;
                        2: a=(sent%2)*4*COLS;
                        3: a=value%MEM_WORDS;
                        4: a=(sent%16==0) ? 4*COLS : (sent%COLS)*4;
                        5: a=(sent%4==0) ? ((sent/4)%ROWS)*4*COLS : sent%4;
                        6: begin a=value%MEM_WORDS; wr=0; end
                        7: begin a=value%MEM_WORDS; wr=(sent%2)==0; end
                        8: begin a=value%MEM_WORDS; wr=1; end
                        9: a=0;
                        default: a=value%MEM_WORDS;
                    endcase
                    req_valid=1; req_tag=8'(tag); req_addr=ADDR_W'(a); req_write=wr;
                    req_wdata=32'(value) ^ 32'(sent); trace_offer=next_offer;
                    do begin
                        @(posedge clk);
                        handshake=req_ready;
                        @(negedge clk); rsp_ready=(cycle%100)<ready_pct;
                    end while (!handshake);
                    req_valid=0;
                    sent=sent+1; next_offer=next_offer+offer_interval;
                end else @(negedge clk);
            end else @(negedge clk);
        end
        rsp_ready=1; drain();
        if (accepted!=responded) $fatal(1,"final accounting");
        if (trace_fd!=0) $fclose(trace_fd);
        $display("PASS policy=%0d aging=%0d seed=%0d accepted=%0d cycles=%0d act=%0d read=%0d write=%0d pre=%0d protection=%0d max_wait=%0d same_addr_block=%0d independent_bypass=%0d overlap=%0d full=%0d bank_overlap=%0d idle_empty=%0d idle_timing=%0d idle_policy=%0d idle_dependency=%0d protected_owner_block=%0d",
            SCHED_POLICY,AGING_ENABLE,seed,accepted,cycle,commands[0],commands[1],commands[2],commands[3],
            protections,max_wait,same_addr_block,independent_bypass,read_write_overlap,full_seen,
            bank_overlap,idle_empty,idle_timing,idle_policy,idle_dependency,protected_owner_block);
        $finish;
    end
    initial begin #100000000; $fatal(1,"watchdog"); end
endmodule
