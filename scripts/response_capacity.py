#!/usr/bin/env python3
"""Measure response throughput with row hits and configurable column spacing."""
import argparse
import csv
import json
from pathlib import Path
from run import build, simulate, POLICIES, COMMANDS
from log_experiment import append_entry

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--label',required=True,choices=['before','after'])
    args=p.parse_args()
    results=[]; status='失敗或中斷'
    try:
        for spacing in [1,2]:
            for policy in POLICIES:
                params={'COLS':64,'T_CCD':spacing}
                binary=build(policy,params)
                result=simulate(binary,policy,42,5000,workload=0,ready=100,trace=True,warmup=200,
                                label=f'response_capacity_{args.label}_{policy}_ccd{spacing}')
                result['parameters']=params
                cycles=[]
                with (ROOT/result['path']/'events.csv').open() as f:
                    for row in csv.reader(f):
                        if row[0]=='R' and 210<=int(row[2])<5210: cycles.append(int(row[1]))
                longest=streak=1
                for a,b in zip(cycles,cycles[1:]):
                    streak=streak+1 if b==a+1 else 1
                    longest=max(longest,streak)
                result['longest_consecutive_handshakes']=longest
                result['response_window_rate']=(len(cycles)-1)/(cycles[-1]-cycles[0])
                result['build']=json.loads((binary.parent/'build_config.json').read_text())
                results.append(result)
                print(f'{args.label} {policy} tCCD={spacing}: '
                      f'cohort={result["metrics"]["responses_per_cycle"]:.6f}, '
                      f'window={result["response_window_rate"]:.6f}, streak={longest}',flush=True)
        out=ROOT/'results'/f'response_capacity_{args.label}.json'
        out.write_text(json.dumps({'label':args.label,'results':results},indent=2)+'\n')
        status=f'通過；結果：{out.relative_to(ROOT)}'
    finally:
        append_entry(f'回應路徑吞吐量比較：{args.label}',
                     '區分回應仲裁上限與全域 tCCD 命令間距上限。',
                     '以相同資料序列測量三種排程器在 tCCD=1 與 tCCD=2 的行為。',
                     f'results/response_capacity_{args.label}.json', '\n'.join(COMMANDS),status,
                     '若未通過，請參閱對應模擬輸出。',
                     '僅變更測試參數，不變更控制器預設 DRAM 時序；保留端點區間吞吐量與連續握手長度。',
                     '完成正確性驗證後比較修改前後結果。')

if __name__=='__main__': main()
