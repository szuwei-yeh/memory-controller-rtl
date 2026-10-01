#!/usr/bin/env python3
"""Optional local sanity synthesis and reproducible UCSB DC/PrimeTime runs."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
POLICIES={'strict_fcfs':(0,0),'frfcfs':(1,0),'frfcfs_aging':(1,1)}

def manifest():
    files=(ROOT/'synth/rtl_files.f').read_text().split()
    if not files or len(files)!=len(set(files)): raise RuntimeError('Invalid RTL manifest')
    for f in files:
        path=(ROOT/f).resolve()
        if path.parent != ROOT/'rtl' or path.suffix!='.sv' or not path.is_file():
            raise RuntimeError(f'Non-controller file in synthesis manifest: {f}')
    return files

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['local','dc','pt'])
    p.add_argument('--lab',action='store_true',help='On the lab server: save run metadata, never create a private notebook')
    p.add_argument('--config',type=Path,default=Path('synth/lab_config.tcl'))
    p.add_argument('--run',type=Path,help='Existing DC run directory for PrimeTime')
    p.add_argument('--baseline',action='store_true',help='DC only: run frfcfs_aging, Q=16, 5 ns instead of the full sweep')
    p.add_argument('--policy',choices=POLICIES,help='DC sweep: restrict execution to one policy in an isolated workspace')
    p.add_argument('--point',nargs=2,metavar=('Q','NS'),help='DC only: one queue depth/clock point; requires --policy')
    args=p.parse_args(); files=manifest(); status='失敗或中斷'; commands=[]
    if args.baseline and args.action!='dc': p.error('--baseline requires dc')
    if args.policy and (args.action!='dc' or args.baseline): p.error('--policy requires dc without --baseline')
    point=None
    if args.point:
        if args.action!='dc' or not args.policy or args.baseline:
            p.error('--point requires dc --policy, without --baseline')
        try:
            depth=int(args.point[0]); period=float(args.point[1])
            if depth<1 or not math.isfinite(period) or period<=0: raise ValueError
        except ValueError:
            p.error('--point requires a positive integer Q and finite positive clock period')
        point=(args.policy,depth,int(period) if period.is_integer() else period)
    try:
        tool={'local':'yosys','dc':'dc_shell','pt':'pt_shell'}[args.action]
        if not shutil.which(tool): raise RuntimeError(f'{tool} is not available in this environment')
        if args.action!='local' and not args.config.resolve().is_file():
            raise RuntimeError('Provide --config with the lab technology library/corner and unit settings')
        revision=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True).stdout.strip() or 'uncommitted'
        hashes={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}
        if args.action=='local':
            experiments=[('frfcfs_aging',16,5)]
        elif args.action=='dc':
            experiments=[(p,16,c) for p in POLICIES for c in [20,10,8,5,4,3,2]]
            experiments += [(p,q,5) for p in POLICIES for q in [4,8,32]]
            if args.baseline: experiments=[('frfcfs_aging',16,5)]
            if args.policy: experiments=[point for point in experiments if point[0]==args.policy]
            if point is not None: experiments=[point]
        else:
            if not args.run: raise RuntimeError('--run is required for PrimeTime')
            experiments=[('existing',0,0)]
        for policy,depth,period in experiments:
            out=(args.run.resolve()/'pt' if args.action=='pt' else ROOT/'build/synth'/args.action/f'{policy}_q{depth}_{period}ns')
            out.mkdir(parents=True,exist_ok=True)
            if args.action=='dc' and (out/'work').exists(): shutil.rmtree(out/'work')
            env=os.environ.copy(); env['MC_OUT']=str(out)
            if args.action=='local':
                script='read_verilog -sv -D SYNTHESIS '+' '.join(files)+'; hierarchy -check -top mc_top; synth -top mc_top; check -assert; stat; write_json '+str(out/'netlist.json')
                cmd=['yosys','-Q','-T','-p',script]
            else:
                env['MC_LAB_CONFIG']=str(args.config.resolve())
                if args.action=='dc':
                    scheduling,aging=POLICIES[policy]
                    env.update(MC_POLICY=str(scheduling),MC_AGING=str(aging),MC_Q=str(depth),MC_CLOCK_NS=str(period))
                    cmd=[tool,'-f','synth/dc/run.tcl']
                else:
                    env['MC_DC_RUN']=str(args.run.resolve()); cmd=[tool,'-f','synth/pt/run.tcl']
            commands.append(' '.join(cmd)); started=time.time()
            metadata={'action':args.action,'policy':policy,'queue_depth':depth,'clock_ns':period,
                      'rtl_revision':revision,'rtl_sha256':hashes,'command':cmd,
                      'status':'RUNNING','start_unix':started}
            if args.action!='local':
                metadata['lab_config_sha256']=hashlib.sha256(args.config.resolve().read_bytes()).hexdigest()
                metadata['flow_sha256']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                    for name in ['scripts/synth.py','synth/rtl_files.f','synth/constraints/controller.sdc',
                                 'synth/'+args.action+'/run.tcl']}
                metadata['hostname']=os.uname().nodename
            (out/'run.json').write_text(json.dumps(metadata,indent=2)+'\n')
            with (out/'tool.log').open('w') as f:
                run=subprocess.run(cmd,cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT)
            # DC can report Tcl errors without a nonzero process status; require script completion marker.
            ok=run.returncode==0 and (args.action=='local' or (out/'SUCCESS').exists())
            if ok and args.action=='local':
                netlist=json.loads((out/'netlist.json').read_text())
                latch_types={cell['type'] for module in netlist['modules'].values()
                             for cell in module.get('cells',{}).values() if 'latch' in cell['type'].lower()}
                ok=not latch_types
                metadata['latch_types']=sorted(latch_types)
            metadata.update(status='PASS' if ok else 'FAIL',elapsed_s=time.time()-started)
            (out/'run.json').write_text(json.dumps(metadata,indent=2)+'\n')
            if not ok: raise RuntimeError(f'Synthesis/STA failed; inspect {out}/tool.log')
            print(f'PASS {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}',flush=True)
        status='通過；本機 Yosys 結果僅代表可綜合性檢查。' if args.action=='local' else '工具流程完成；需檢視面積、時序與約束報告。'
    finally:
        if not args.lab:
            from log_experiment import append_entry
            append_entry(f'綜合／時序流程：{args.action}','建立可重現的控制器綜合證據。',
                         '驗證控制器專用檔案清單並執行工具。','無（僅建置產物）','\n'.join(commands),status,
                         '若未完成，請參閱工具輸出；不可將缺失結果視為通過。',
                         '模型、測試平台、工作負載與筆記不納入 ASIC 綜合。',
                         '分析關鍵路徑並將實際結果整理成公開報告。')

if __name__=='__main__': main()
