#!/usr/bin/env python3
"""Reproducible local builds, tests, regressions and performance experiments."""
import argparse
import concurrent.futures
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import statistics
import subprocess
import sys
import time
from log_experiment import append_entry

ROOT = Path(__file__).resolve().parents[1]
POLICIES = {'strict_fcfs': (0, 0), 'frfcfs': (1, 0), 'frfcfs_aging': (1, 1)}
WORKLOADS = ['row_hit', 'sequential', 'row_conflict', 'random', 'hot_cold', 'hol',
             'read_only', 'read_write_50', 'write_only', 'same_address']
FLAGS = ['-Wall', '-Wno-UNUSEDSIGNAL', '-Wno-BLKSEQ', '-Wno-TIMESCALEMOD']
COMMANDS = []

def execute(cmd, log=None, timeout=300):
    COMMANDS.append(shlex.join(map(str, cmd)))
    result = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=timeout)
    if log:
        Path(log).parent.mkdir(parents=True, exist_ok=True)
        Path(log).write_text(result.stdout)
    if result.returncode:
        raise RuntimeError(f'{shlex.join(map(str, cmd))}\n{result.stdout[-8000:]}')
    return result.stdout

def build(policy, params=None, top='tb_top', extra=None):
    params = dict(params or {})
    if top == 'tb_top':
        params.update(zip(['SCHED_POLICY', 'AGING_ENABLE'], POLICIES[policy]))
    files = (ROOT/'synth/rtl_files.f').read_text().split()
    files += ['tb/dram_model.sv', f'tb/{top}.sv']
    version = execute(['verilator', '--version']).strip()
    probe=subprocess.run(['verilator','-Wno-PROCASSINIT','--version'],capture_output=True)
    flags=FLAGS+(['-Wno-PROCASSINIT'] if probe.returncode==0 else [])
    digest = hashlib.sha256((version + json.dumps(params, sort_keys=True)).encode())
    for name in files:
        digest.update((ROOT/name).read_bytes())
    out = ROOT/'build/sim'/f'{policy}_{top}_{digest.hexdigest()[:12]}'
    binary = out/f'V{top}'
    if not binary.exists():
        out.mkdir(parents=True, exist_ok=True)
        cmd = ['verilator', '--binary', '--timing', '--assert', '-j', '4', '--top-module', top,
               *flags, *[f'-G{k}={v}' for k,v in params.items()], '-f', 'synth/rtl_files.f',
               'tb/dram_model.sv', f'tb/{top}.sv', '--Mdir', str(out)]
        execute(cmd, out/'build.log')
    (out/'build_config.json').write_text(json.dumps({'parameters':params,'verilator':version,
        'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files}},indent=2)+'\n')
    return binary

def simulate(binary, policy, seed, n, workload=3, ready=80, load=100, interval=1,
             trace=False, extra=None, label=None, warmup=0):
    label = label or f'{policy}_w{workload}_s{seed}_n{n}_r{ready}_l{load}_i{interval}'
    folder = ROOT/'build/runs'/label
    folder.mkdir(parents=True, exist_ok=True)
    cmd = [str(binary), f'+seed={seed}', f'+n={n}', f'+workload={workload}', f'+ready={ready}',
           f'+load={load}', f'+interval={interval}', f'+warmup={warmup}', *(extra or [])]
    if trace: cmd.append(f'+trace={folder/"events.csv"}')
    output = execute(cmd, folder/'simulation.log', timeout=300)
    line = next((line for line in output.splitlines() if line.startswith('PASS ')), None)
    if line is None: raise RuntimeError(f'Missing PASS: {folder}')
    result = {k:int(v) for k,v in re.findall(r'(\w+)=(-?\d+)', line)}
    result.update(policy_name=policy, workload=WORKLOADS[workload], path=str(folder.relative_to(ROOT)))
    configuration=json.loads((binary.parent/'build_config.json').read_text())
    (folder/'run.json').write_text(json.dumps({'command':cmd,'build':configuration,'result':result}, indent=2)+'\n')
    result['ready_percent']=ready; result['offered_interval']=interval
    if trace: result['metrics'] = analyze(folder/'events.csv', warmup, n)
    return result

def distribution(values):
    values = sorted(values)
    if not values: return {}
    return {'mean':statistics.mean(values), 'median':statistics.median(values),
            'p95':values[min(len(values)-1, int(.95*(len(values)-1)))],
            'p99':values[min(len(values)-1, int(.99*(len(values)-1)))], 'max':max(values)}

def analyze(path, warmup, n):
    # First ten directed requests precede the workload's warm-up.
    low, high = 10+warmup, 10+warmup+n
    responses=[]; commands=[]; occupancy=[]; protection=[]; completions=[]; accepts=[]; idle=[]; protected_duration=[]
    with path.open() as f:
        for row in csv.reader(f):
            kind=row[0]; data=list(map(int,row[1:]))
            if kind=='R' and low<=data[1]<high: responses.append(data)
            elif kind=='C': commands.append(data)
            elif kind=='O': occupancy.append(data)
            elif kind=='P': protection.append(data)
            elif kind=='D': completions.append(data)
            elif kind=='A': accepts.append(data)
            elif kind=='I': idle.append(data)
            elif kind=='E': protected_duration.append(data)
    if len(responses)!=n: raise RuntimeError('measurement response count mismatch')
    # R: consumed, seq, addr, write, offered, accepted, issued, done, eligible, presented, locality
    start=min(x[5] for x in responses); end=max(x[0] for x in responses); duration=end-start+1
    samples={
        'admission':[x[5]-x[4] for x in responses],
        'queue':[x[6]-x[5] for x in responses],
        'completion':[x[7]-x[5] for x in responses],
        'response_order':[x[8]-x[7] for x in responses],
        'response_arbitration':[x[9]-x[8] for x in responses],
        'host_backpressure':[x[0]-x[9] for x in responses],
        'end_to_end':[x[0]-x[5] for x in responses],
    }
    active_commands=[x for x in commands if start<=x[0]<=end]
    attributable=[x for x in commands if low<=x[1]<high]
    occ=[x for x in occupancy if start<=x[0]<=end]
    m={'requests':n,'measurement_cycles':duration,'responses_per_cycle':n/duration,
       'bytes_per_cycle':4*n/duration,'latency':{k:distribution(v) for k,v in samples.items()},
       'read_latency':distribution([x[0]-x[5] for x in responses if not x[3]]),
       'write_latency':distribution([x[0]-x[5] for x in responses if x[3]]),
       'row_hit_rate':sum(x[10]==0 for x in responses)/n,
       'closed_miss_rate':sum(x[10]==1 for x in responses)/n,
       'row_conflict_rate':sum(x[10]==2 for x in responses)/n,
       'act_per_request':sum(x[2]==0 for x in attributable)/n,
       'pre_per_request':sum(x[2]==3 for x in attributable)/n,
       'command_utilization':len(active_commands)/duration,
       'mean_occupancy':statistics.mean(x[1] for x in occ),
       'mean_preparing_banks':statistics.mean(x[2] for x in occ),
       'protection_activations':sum(start<=x[0]<=end for x in protection)}
    m['accepted_per_cycle']=sum(start<=x[0]<=end for x in accepts)/duration
    m['column_issues_per_cycle']=sum(x[2] in [1,2] for x in active_commands)/duration
    m['internal_completions_per_cycle']=sum(start<=x[0]<=end for x in completions)/duration
    m['bank_open_fraction']=[sum(bool(x[3] & (1<<b)) for x in occ)/len(occ) for b in range(4)]
    m['bank_preparing_fraction']=[sum(bool(x[4] & (1<<b)) for x in occ)/len(occ) for b in range(4)]
    m['idle_cycles']={name:sum(start<=x[0]<=end and x[1]==i for x in idle)
                     for i,name in enumerate(['empty','timing','policy','dependency_or_owner'])}
    m['protected_duration']=distribution([x[2] for x in protected_duration if start<=x[0]<=end])
    (path.parent/'metrics.json').write_text(json.dumps(m,indent=2)+'\n')
    return m

def lint():
    return execute(['verilator','--lint-only','--top-module','mc_top','-Wall',
                    '-Wno-UNUSEDSIGNAL','-f','synth/rtl_files.f'])

def test():
    results=[]
    for policy in POLICIES:
        binary=build(policy)
        for workload in range(len(WORKLOADS)):
            results.append(simulate(binary,policy,1,500,workload))
        results.append(simulate(binary,policy,7,100,extra=['+reset_test'],label=f'{policy}_reset'))
    for name,params in [
        ('minimum',dict(Q_DEPTH=1,ROWS=2,COLS=2,READ_LATENCY=1,T_RCD=1,T_RP=1,T_RAS=1,T_CCD=1,T_WR=1,AGE_LIMIT=1)),
        ('odd_queue',dict(Q_DEPTH=3,READ_LATENCY=7,T_CCD=1,AGE_LIMIT=8)),
        ('slow',dict(Q_DEPTH=4,READ_LATENCY=9,T_RCD=5,T_RP=4,T_RAS=13,T_CCD=3,T_WR=7,AGE_LIMIT=4)),
    ]:
        for policy in POLICIES:
            binary=build(policy,params)
            results.append(simulate(binary,policy,13,500,ready=30,label=f'{policy}_{name}'))
    negative_model_tests()
    scheduler=build('scheduler',top='tb_scheduler')
    execute([str(scheduler)], ROOT/'build/scheduler_directed.log')
    response=build('response',top='tb_response')
    execute([str(response)], ROOT/'build/response_directed.log')
    coverage={key:sum(r[key] for r in results) for key in
              ['protection','same_addr_block','independent_bypass','overlap','full','bank_overlap']}
    if not all(coverage.values()): raise RuntimeError(f'Missing required suite coverage: {coverage}')
    return results

def negative_model_tests():
    binary=build('model',top='tb_model')
    execute([str(binary),'+case=0'], ROOT/'build/model_legal.log')
    execute([str(binary),'+case=9'], ROOT/'build/model_tras_boundary.log')
    for case,expected in [(1,'tRCD'),(2,'tRP'),(3,'tRAS'),(4,'tCCD'),(5,'tWR'),(6,'wrong row'),(7,'ACT open'),(8,'PRE closed')]:
        cmd=[str(binary),f'+case={case}']; COMMANDS.append(shlex.join(cmd))
        r=subprocess.run(cmd,cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (ROOT/f'build/model_negative_{case}.log').write_text(r.stdout)
        if r.returncode==0 or f'MODEL {expected}' not in r.stdout:
            raise RuntimeError(f'Negative case {case} did not fail for {expected}: {r.stdout}')

def regress(seeds, n, jobs):
    binaries={p:build(p) for p in POLICIES}
    tasks=[(p,s) for p in POLICIES for s in range(1,seeds+1)]
    def worker(ps):
        p,s=ps
        return simulate(binaries[p],p,s,n,workload=(s-1)%len(WORKLOADS),ready=[100,80,30][s%3])
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        for result in pool.map(worker,tasks):
            results.append(result)
            if len(results)%10==0: print(f'Regression {len(results)}/{len(tasks)} passed',flush=True)
    return results

def performance(n):
    results=[]
    for p in POLICIES:
        binary=build(p)
        experiments=[(w,100,1) for w in range(len(WORKLOADS))]
        experiments += [(3,100,i) for i in [4,8,16]] + [(3,r,1) for r in [80,50,20]]
        for w,r,interval in experiments:
            result=simulate(binary,p,42,n,w,ready=r,interval=interval,trace=True,warmup=200)
            results.append(result)
            print(f'Performance {p} {WORKLOADS[w]} ready={r} interval={interval}: '
                  f'{result["metrics"]["responses_per_cycle"]:.3f} responses/cycle',flush=True)
    return results

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['lint','test','regress','perf','smoke'])
    parser.add_argument('--seeds',type=int,default=100)
    parser.add_argument('--n',type=int,default=None)
    parser.add_argument('--jobs',type=int,default=4)
    args=parser.parse_args(); os.chdir(ROOT); started=time.time(); status='失敗或中斷'
    result=None
    try:
        if args.action=='lint': result=lint()
        elif args.action=='test': result=test()
        elif args.action=='regress': result=regress(args.seeds,args.n or 10000,args.jobs)
        elif args.action=='perf': result=performance(args.n or 2000)
        else: result=[simulate(build(p),p,1,args.n or 1000) for p in POLICIES]
        out=ROOT/'build'/f'{args.action}_summary.json'; out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps({'action':args.action,'elapsed_s':time.time()-started,
                                  'verilator':execute(['verilator','--version']).strip(),'results':result},indent=2)+'\n')
        status=f'通過；結果：{out.relative_to(ROOT)}'
        print(status)
    finally:
        append_entry(f'本機 {args.action} 實驗', '執行可重現的 RTL 驗證或效能分析。',
                     '執行命令並保存輸出、設定及結果。','無（僅產生忽略的建置產物與本機日誌）',
                     '\n'.join(COMMANDS),status,'若失敗，請參閱對應建置或模擬輸出。',
                     '比較相同序列；所有測試使用獨立資料、排序與時間戳記檢查。',
                     '檢視結果並處理未覆蓋的情境。')

if __name__=='__main__': main()
