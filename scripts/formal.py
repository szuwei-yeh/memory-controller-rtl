#!/usr/bin/env python3
"""Run focused formal tasks; preserve explicit PASS/FAIL/timeout evidence."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from log_experiment import append_entry

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--task',choices=['strict','frfcfs','aging','bank','progress','all'],default='all')
    p.add_argument('--timeout',type=int,default=300)
    args=p.parse_args()
    sby=shutil.which('sby')
    if sby: executable=[sby]
    elif (ROOT/'.tools/sby/sbysrc/sby.py').exists():
        python=ROOT/'.tools/venv/bin/python'
        executable=[str(python) if python.exists() else sys.executable,str(ROOT/'.tools/sby/sbysrc/sby.py')]
    else: raise SystemExit('SymbiYosys missing. Install sby or clone YosysHQ/sby into .tools/sby.')
    results=[]
    for task in (['strict','frfcfs','aging','bank','progress'] if args.task=='all' else [args.task]):
        out=ROOT/'build/formal'/task; out.parent.mkdir(parents=True,exist_ok=True)
        config=f'formal/{task}.sby' if task in ['bank','progress'] else 'formal/controller.sby'
        cmd=[*executable,'-f','-d',str(out),config]
        if task not in ['bank','progress']: cmd.append(task)
        status='未完成'; output=''
        try:
            run=subprocess.run(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=args.timeout)
            output=run.stdout
            status=(out/'status').read_text().split()[0] if (out/'status').exists() else 'ERROR'
            if run.returncode: print(output[-6000:])
        except subprocess.TimeoutExpired as e:
            status='TIMEOUT'; output=(e.stdout or b'').decode() if isinstance(e.stdout,bytes) else e.stdout or ''
        finally:
            (out.parent/f'{task}.log').write_text(output)
            append_entry(f'形式驗證：{task}','檢查縮小配置的容量、排序與有限進度性質。',
                         '執行 SymbiYosys 並保存狀態與反例。','無（僅驗證產物）',' '.join(cmd),
                         status,'若非 PASS，不能宣稱性質已通過。',
                         '有限深度模型檢查不等同無界證明；明確保留模式、深度與工具版本。',
                         '檢視反例或增加歸納性不變量。')
        results.append({'task':task,'status':status,'mode':'prove' if task in ['bank','progress'] else 'bmc',
                        'depth':None if task in ['bank','progress'] else 12})
        print(task,status,flush=True)
    (ROOT/'build/formal/summary.json').write_text(json.dumps(results,indent=2)+'\n')
    if any(r['status']!='PASS' for r in results): raise SystemExit(1)

if __name__=='__main__': main()
