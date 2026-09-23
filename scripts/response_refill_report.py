#!/usr/bin/env python3
"""Compare retained pre-amendment evidence with verified response-refill results."""
from collections import Counter
import difflib
import json
from pathlib import Path
import re
import subprocess
from log_experiment import append_entry

ROOT=Path(__file__).resolve().parents[1]
BEFORE=ROOT/'build/response_refill/before'
SYNTH=Path('build/synth/local/frfcfs_aging_q16_5ns')

def netlist_stats(path):
    netlist=json.loads(path.read_text())
    counts=Counter(); response=Counter()
    for name,module in netlist['modules'].items():
        for cell in module.get('cells',{}).values():
            if cell['type'].startswith('$_'): counts[cell['type']]+=1
            if name.endswith('mc_response'): response[cell['type']]+=1
    return {'controller_cells':sum(counts.values()),
            'controller_flops':sum(v for k,v in counts.items() if 'DFF' in k),
            'response_cells':sum(response.values()),
            'response_flops':sum(v for k,v in response.items() if 'DFF' in k),
            'latches':sum(v for k,v in counts.items() if 'LATCH' in k),
            'response_cell_types':dict(response)}

def ltp(path, log):
    command=['yosys','-Q','-T','-p',f'read_json {path}; select *mc_response; ltp -noff']
    result=subprocess.run(command,cwd=ROOT,text=True,capture_output=True,check=True)
    log.write_text(result.stdout)
    return int(re.search(r'Longest topological path .*\(length=(\d+)\)',result.stdout).group(1))

def main():
    before_file=ROOT/'results/response_refill_before.json'
    if not before_file.exists():
        old=netlist_stats(BEFORE/SYNTH/'netlist.json')
        old['response_logic_depth']=ltp(BEFORE/SYNTH/'netlist.json',BEFORE/'response_ltp.log')
        run=json.loads((BEFORE/SYNTH/'run.json').read_text())
        baseline={'performance':json.loads((BEFORE/'build/perf_summary.json').read_text()),
                  'synthesis':old,'synthesis_run':{k:run[k] for k in
                      ['action','policy','queue_depth','clock_ns','rtl_sha256','status']},
                  'original_response_test_rejected_bubble':
                      'response expected tag=1 got valid=0' in
                      (ROOT/'build/response_refill/before_directed.log').read_text()}
        before_file.write_text(json.dumps(baseline,indent=2)+'\n')
    baseline=json.loads(before_file.read_text())
    after=netlist_stats(ROOT/SYNTH/'netlist.json')
    after['response_logic_depth']=ltp(ROOT/SYNTH/'netlist.json',ROOT/'build/response_refill/after_ltp.log')
    performance=json.loads((ROOT/'build/perf_summary.json').read_text())
    capacities={label:json.loads((ROOT/f'results/response_capacity_{label}.json').read_text())
                for label in ['before','after']}
    formal=json.loads((ROOT/'build/formal/summary.json').read_text())
    regression=json.loads((ROOT/'build/regress_summary.json').read_text())
    tests=json.loads((ROOT/'build/test_summary.json').read_text())
    assert all(r['status']=='PASS' for r in formal)
    assert len(regression['results'])==300
    assert 'PASS response refill' in (ROOT/'build/response_directed.log').read_text()
    assert baseline['original_response_test_rejected_bubble']
    comparison={'capacity':capacities,'synthesis_before':baseline['synthesis'], 'synthesis_after':after,
                'regression_runs':len(regression['results']),
                'accepted_transactions':sum(r['accepted'] for r in regression['results']),
                'directed_corner_runs':len(tests['results']),'formal':formal,'workload_changes':[]}
    key=lambda r:(r['policy_name'],r['workload'],r['ready_percent'],r['offered_interval'])
    old_runs={key(r):r for r in baseline['performance']['results']}
    for r in performance['results']:
        previous=old_runs[key(r)]
        comparison['workload_changes'].append({'policy':r['policy_name'],'workload':r['workload'],
            'ready_percent':r['ready_percent'],'offered_interval':r['offered_interval'],
            'before':previous['metrics'],'after':r['metrics']})
    (ROOT/'results/response_refill_comparison.json').write_text(json.dumps(comparison,indent=2)+'\n')
    if (BEFORE/'rtl/mc_response.sv').exists():
        old_source=(BEFORE/'rtl/mc_response.sv').read_text()
        new_source=(ROOT/'rtl/mc_response.sv').read_text()
        patch=''.join(difflib.unified_diff(old_source.splitlines(keepends=True),new_source.splitlines(keepends=True),
                                         fromfile='a/rtl/mc_response.sv',tofile='b/rtl/mc_response.sv'))
        (ROOT/'results/response_refill.patch').write_text(patch)
    cap_rows=[]
    for old,new in zip(capacities['before']['results'],capacities['after']['results']):
        assert (old['policy_name'],old['parameters'])==(new['policy_name'],new['parameters'])
        cap_rows.append(f'| {new["policy_name"]} | {new["parameters"]["T_CCD"]} | '
                        f'{old["response_window_rate"]:.6f} → {new["response_window_rate"]:.6f} | '
                        f'{old["metrics"]["responses_per_cycle"]:.6f} → {new["metrics"]["responses_per_cycle"]:.6f} | '
                        f'{old["longest_consecutive_handshakes"]} → {new["longest_consecutive_handshakes"]} |')
    workload_rows=[]
    for r in comparison['workload_changes']:
        if r['ready_percent']!=100 or r['offered_interval']!=1: continue
        b,a=r['before'],r['after']
        workload_rows.append(f'| {r["policy"]} | {r["workload"]} | '
                             f'{b["responses_per_cycle"]:.4f} → {a["responses_per_cycle"]:.4f} | '
                             f'{b["latency"]["end_to_end"]["mean"]:.2f} → {a["latency"]["end_to_end"]["mean"]:.2f} | '
                             f'{b["latency"]["end_to_end"]["p99"]} → {a["latency"]["end_to_end"]["p99"]} |')
    synth_rows='\n'.join(f'| {k} | {baseline["synthesis"][k]} | {after[k]} |'
                         for k in ['controller_cells','controller_flops','response_cells','response_flops','response_logic_depth','latches'])
    backpressure_rows=[]
    for r in comparison['workload_changes']:
        if r['policy']!='frfcfs_aging' or r['workload']!='random' or r['ready_percent']==100: continue
        b,a=r['before'],r['after']
        backpressure_rows.append(f'| {r["ready_percent"]}% | {b["responses_per_cycle"]:.4f} → {a["responses_per_cycle"]:.4f} | '
                                 f'{b["latency"]["end_to_end"]["mean"]:.2f} → {a["latency"]["end_to_end"]["mean"]:.2f} | '
                                 f'{b["latency"]["end_to_end"]["p99"]} → {a["latency"]["end_to_end"]["p99"]} |')
    text=f'''# Response-refill microarchitecture amendment

Only `rtl/mc_response.sv` changes in the controller. The exact patch is in
`results/response_refill.patch`. No scheduler, transaction table, timing, interface,
or default parameter changed. No global retirement buffer or additional registers
were introduced.

## Exact change

Previously, a valid/ready handshake cleared `held_valid`; selection occurred only
on a later edge with an empty register. Now a combinational `selectable` mask excludes
the currently held slot from both candidate selection and the oldest-candidate
comparison. On `!held_valid || rsp_ready`, the register loads that winner and its valid
bit. An occupied, stalled register is not updated.

Same-address eligibility still examines all pre-edge occupied entries, including
the consumed predecessor. Newly unblocked successors cannot refill on that edge.
Already-eligible independent transactions can refill immediately. This removes the
global selection bubble while preserving the conservative same-address rule and
stable payload under backpressure. `rsp_ready` does not feed combinational `rsp_valid`.

## Directed verification and complete checks

- The new `tb_response` fails on the original RTL's second expected consecutive response.
- It passes eight consecutive independent handshakes on the revised RTL.
- It covers a held response stalled while an older independent completion becomes ready,
  oldest-other replacement, same-address consumption order, the retained same-address
  bubble, final-entry non-duplication, and reset cancellation.
- Formal assertions check no reselection of the held slot and next-cycle occupancy/slot
  after a handshake with an available replacement; previous stability/order checks remain.
- {comparison['directed_corner_runs']} directed/workload/reset/corner runs passed, plus the response,
  scheduler and model unit tests. RTL lint passed.
- {comparison['regression_runs']} full regression runs passed: {comparison['accepted_transactions']:,}
  accepted transactions (100 × 10,000 requests × three policies, plus preludes).
- All five formal tasks passed: three depth-12 symbolic-data BMC tasks, bank timing PDR,
  and reduced mixed-read/write progress PDR. These proof scope limits are unchanged.
- Revised performance experiments were run after correctness passed. No UCSB DC/PT run
  was started for this amendment.

## Row-hit maximum throughput

Identical before/after workload: 64 columns, 16 slots, three-cycle READ latency,
seed 42, 200 warm-up and 5,000 measured requests, 75/25 read/write mix, ready always
asserted, one offered request per cycle. Only the test's tCCD changes between rows.

Response-window rate is `(N-1)/(last_response-first_response)`. Cohort throughput is
`N/(last_response-first_acceptance+1)` and includes drain/queue latency. The longest
consecutive sequence establishes actual adjacent-cycle handshakes, not just an average.

| Policy | tCCD | Response-window rate, old → new | Cohort rate, old → new | Longest consecutive handshakes, old → new |
|---|---:|---:|---:|---:|
{chr(10).join(cap_rows)}

The response path's capability is one response/cycle when independent eligible
completions exist. Default tCCD=2 still limits DRAM column commands to one every
two cycles, so removing the response bubble does not double default row-hit throughput.

## Default-timing workload changes

The regular 48-experiment suite retains its original eight-column geometry,
seed 42, 200 warm-up/2,000 measured requests, and tCCD=2. Table entries below use
ready=100% and one offered request/cycle. Full distributions and load/backpressure
sweeps are in `results/response_refill_comparison.json`.

| Policy | Workload | Responses/cycle, old → new | Mean latency, old → new | p99 latency, old → new |
|---|---|---:|---:|---:|
{chr(10).join(workload_rows)}

The benefit is larger while draining completions accumulated under backpressure.
For random traffic with FR-FCFS + aging (the same deterministic 100-cycle ready pattern):

| Ready duty cycle | Responses/cycle, old → new | Mean latency, old → new | p99 latency, old → new |
|---|---:|---:|---:|
{chr(10).join(backpressure_rows)}

Even with tCCD unchanged, response timing changes transaction-slot availability and
therefore which requests are visible to the scheduler. Throughput or tail latency
need not improve on every workload; no scheduler policy or aging rule was changed.

## Local Yosys implications

Paired default-Q=16 generic synthesis, identical source files except mc_response,
same Yosys flow and settings. Cells are generic one-bit mapped primitives, not
standard-cell ASIC area. Logic depth is Yosys `ltp -noff` for the response module.

| Metric | Before | After |
|---|---:|---:|
{synth_rows}

The mask adds held-slot exclusion to the arbitration cone. The register-update enable
now permits consume/refill; the held payload still comes from the existing table.
This changes a register-to-register feedback path from held slot/valid through winner
selection to the next held slot/valid. Cell-count and topological-depth differences
are structural observations only: Yosys has no lab library or SDC-based delay analysis
here. DC/PrimeTime must establish mapped setup slack and frequency; no Fmax is inferred.
The unchanged transaction table also maps to a different generic cell count in
these runs, so the whole-controller delta is not entirely added response logic.
No other controller RTL changed; mapping heuristics depend on the synthesis context.

## Reproduce

```sh
make lint test
make regress SEEDS=100 N=10000 JOBS=4
make formal
# Only after the correctness commands pass:
make perf
python3 scripts/response_capacity.py --label after
make synth-local-sanity
mkdir -p build/response_refill     # report log destination in a clean checkout
python3 scripts/response_refill_report.py
make report
```

The pre-change measurements, RTL hashes, and synthesis summary are retained in
`results/response_capacity_before.json` and `results/response_refill_before.json`.
To rebuild the old revision, reverse the published patch in a separate copy; do not
replace the working controller. Local raw baseline snapshots are under
`build/response_refill/before/`. The private Traditional Chinese notebook records the
decision, baseline, verification, and before/after experiment results; it is excluded
from Git and all export bundles.
'''
    (ROOT/'build/response_refill/report.md').write_text(text)
    rates=[f'{r["policy_name"]} tCCD={r["parameters"]["T_CCD"]}: '
           f'{r["response_window_rate"]:.6f} 回應／週期，最長 {r["longest_consecutive_handshakes"]} 筆連續握手'
           for r in capacities['after']['results']]
    append_entry('回應補入修訂的前後結果與公開報告',
                 '量化單一回應模組修訂的正確性、吞吐量與綜合代價。',
                 '產生前後比較、RTL 差異與公開說明文件。',
                 'build/response_refill/report.md、results/response_refill*',
                 'python3 scripts/response_refill_report.py；yosys read_json 與 ltp -noff',
                 '完整回歸與五項形式檢查通過。修改前端點區間吞吐量皆為 0.5。修改後：\n'+ '\n'.join(rates)+
                 f'\n回應模組通用元件：{baseline["synthesis"]["response_cells"]} → {after["response_cells"]}；'
                 f'拓樸深度：{baseline["synthesis"]["response_logic_depth"]} → {after["response_logic_depth"]}；'
                 f'暫存位元：{baseline["synthesis"]["response_flops"]} → {after["response_flops"]}。',
                 '預設 tCCD=2 仍限制命令吞吐量；通用網表不能推導 ASIC 頻率。',
                 '維持同位址保守解鎖規則與所有其他 RTL，只在握手時補入既有獨立合格交易。',
                 '使用更新後的控制器進行後續 UCSB 映射時序與面積分析。')

if __name__=='__main__': main()
