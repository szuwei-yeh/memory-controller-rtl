#!/usr/bin/env python3
"""Execute the frozen UCSB sweep in three isolated policy workspaces."""
import os
import hashlib
import json
import shlex
import subprocess
import tarfile
import time
from pathlib import Path

from dc_sweep_report import POLICIES, parse_run, write_summaries
from log_experiment import append_entry

ROOT=Path(__file__).resolve().parents[1]
LOCAL=ROOT/'build/dc_sweep'
TARGET=os.environ.get('LAB_SSH_TARGET')
CONTROL=os.environ.get('LAB_SSH_CONTROL_PATH')
OLD=os.environ.get('LAB_BASELINE_DIR')
SSH=['ssh',*(['-o','ControlPath='+CONTROL] if CONTROL else []),'-o','BatchMode=yes',TARGET or '']
REPORTS=['run.json','SUCCESS','tool.log','environment.rpt','check_design.rpt','check_timing.rpt','design.rpt',
         'area.rpt','timing.rpt','hold.rpt','constraints.rpt','qor.rpt','references.rpt','mapped.v','mapped.ddc','mapped.sdc']


def ssh(command):
    return subprocess.run(SSH+[command],check=True,text=True,capture_output=True).stdout


def main():
    if not TARGET or not OLD:
        raise SystemExit('Set LAB_SSH_TARGET and LAB_BASELINE_DIR to your private lab connection and baseline workspace.')
    LOCAL.mkdir(parents=True,exist_ok=True)
    remote=ssh('mktemp -d /tmp/memory-controller-sweep-XXXXXXXX').strip()
    state={'remote_root':remote,'policies':POLICIES,'start_unix':time.time()}
    (LOCAL/'session.json').write_text(json.dumps(state,indent=2)+'\n')
    subprocess.run(['scp',*(['-o','ControlPath='+CONTROL] if CONTROL else []),str(ROOT/'build/lab_bundle.tar.gz'),
                    TARGET+':'+remote+'/bundle.tar.gz'],check=True)
    processes={}; logs=[]
    for policy in POLICIES:
        root=remote+'/'+policy
        command=f'mkdir {shlex.quote(root)} && tar xzf {shlex.quote(remote+"/bundle.tar.gz")} -C {shlex.quote(root)} && cp {shlex.quote(OLD+"/synth/lab_config.tcl")} {shlex.quote(root+"/synth/lab_config.tcl")}'
        ssh(command)
        verify='import json,hashlib,pathlib; d=json.load(open("source_hashes.json")); assert all(hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()==h for p,h in d.items())'
        ssh(f'cd {shlex.quote(root)} && /usr/bin/python3.11 -c {shlex.quote(verify)}')
        command=f'cd {shlex.quote(root)} && /usr/bin/python3.11 scripts/synth.py dc --lab --policy {policy} --config synth/lab_config.tcl'
        log=(LOCAL/(policy+'.launch.log')).open('w');logs.append(log)
        processes[policy]=subprocess.Popen(SSH+[command],stdout=log,stderr=subprocess.STDOUT)
    state['launch_commands']={p:f'cd {remote}/{p} && /usr/bin/python3.11 scripts/synth.py dc --lab --policy {p} --config synth/lab_config.tcl' for p in POLICIES}
    (LOCAL/'session.json').write_text(json.dumps(state,indent=2)+'\n')
    append_entry('啟動固定 Design Compiler 比較矩陣','執行 30 個不同點，固定 RTL、SDC、庫與編譯設定。',
        '三政策各自使用隔離工作目錄，同時各執行一個 DC；每政策十個點依序執行。傳輸清單與雜湊已驗證。',
        'scripts/dc_sweep.py、scripts/dc_sweep_report.py、scripts/synth.py、synth/dc/run.tcl；build/dc_sweep/。',
        'python3 scripts/dc_sweep.py；\n'+'\n'.join(state['launch_commands'].values()),
        '已啟動，結果待逐點匯入。', '無。',
        '只新增政策篩選與高精度 hold/constraint 報告；compile -map_effort medium 和所有約束不變。私人筆記不傳輸。',
        '逐次保存報告、附加中文結果，再彙整最快通過的已測 setup 目標。')
    collected={}
    poll_code=f'import pathlib,json; print(json.dumps([dict(json.load(p.open()),_path=str(p.parent)) for p in pathlib.Path({remote!r}).glob("*/build/synth/dc/*/run.json")]))'
    try:
        while len(collected)<30:
            records=json.loads(ssh('/usr/bin/python3.11 -c '+shlex.quote(poll_code)))
            for record in records:
                key=Path(record['_path']).name
                if key in collected or record['status']=='RUNNING': continue
                if record['status']!='PASS': raise RuntimeError('DC flow failed: '+record['_path'])
                destination=LOCAL/'runs'/key;destination.mkdir(parents=True,exist_ok=True)
                archive=LOCAL/(key+'.tar.gz')
                with archive.open('wb') as f:
                    subprocess.run(SSH+[shlex.join(['tar','czf','-','-C',record['_path'],*REPORTS])],stdout=f,check=True)
                with tarfile.open(archive) as t:
                    assert set(t.getnames())==set(REPORTS) and all(m.isfile() for m in t.getmembers())
                    for name in REPORTS:
                        (destination/name).write_bytes(t.extractfile(name).read())
                archive.unlink()
                row=parse_run(destination)
                (destination/'parsed.json').write_text(json.dumps(row,indent=2)+'\n')
                collected[key]=row
                verdict='setup 通過' if row['setup_pass'] else 'setup 未通過'
                append_entry(f'DC sweep：{key}',
                    '在固定 typical 庫與 medium effort 下量測面積與時序，不修改 RTL。',
                    '工具流程完成且完整報告已取回本機；逐項保留警告與違例。',
                    '無原始碼修改；產物 '+str(destination.relative_to(ROOT)),
                    f"dc_shell -f synth/dc/run.tcl；MC_POLICY={dict(strict_fcfs=0,frfcfs=1,frfcfs_aging=1)[row['policy']]}，MC_AGING={int(row['policy']=='frfcfs_aging')}，MC_Q={row['queue_depth']}，MC_CLOCK_NS={row['clock_ns']}；完整指令與來源雜湊見 run.json。",
                    f"{verdict}；面積 {row['area_um2']:.6f} µm²，組合 {row['combinational_area_um2']:.6f}，循序 {row['sequential_area_um2']:.6f}；setup WNS/TNS {row['setup_wns_ns']:.6f}/{row['setup_tns_ns']:.6f} ns，違例 {row['setup_violation_count']}；最差 hold {row['worst_hold_slack_ns']:.6f} ns，違例 {row['hold_violation_count']}；未約束端點 {row['unconstrained_endpoint_count']}。",
                    f"max-cap 違例 {row['max_capacitance_violation_count']}，其中零上限 {row['zero_allowed_load_violation_count']}；警告分類 {json.dumps(row['warning_counts'])}。",
                    f"關鍵路徑 {row['critical_startpoint']} → {row['critical_endpoint']}。setup 通過不代表 hold 或電氣限制通過；保留庫的原始限制，不改 RTL。",
                    '完成其餘固定實驗並比較面積／時序；不由單點宣稱精確最高頻率。')
                print(f"{len(collected)}/30 {key}: area={row['area_um2']:.2f} setup_slack={row['setup_worst_slack_ns']:.6f} hold={row['worst_hold_slack_ns']:.6f}",flush=True)
            if all(p.poll() is not None for p in processes.values()) and len(collected)<30:
                raise RuntimeError('Launch processes ended before all reports were collected; inspect launch logs')
            if len(collected)<30: time.sleep(20)
        for p in processes.values():
            assert p.wait()==0
        result=write_summaries(list(collected.values()))
        print('COMPLETE '+json.dumps(result['fastest_tested_setup_passing_q16']),flush=True)
    except BaseException as exc:
        append_entry('DC sweep 收集流程未完成','保留真實狀態與已完成結果。',f'已匯入 {len(collected)} 個實驗。',
            'build/dc_sweep/；私人逐點記錄已附加。','python3 scripts/dc_sweep.py',
            '失敗或中斷；尚不可宣告矩陣完成。',str(exc),'不修改 RTL，不覆蓋已完成結果；遠端子程序可能仍在執行。','檢查現有 session 與產物後繼續收集，不盲目重跑。')
        raise
    finally:
        for log in logs: log.close()


if __name__=='__main__': main()
