#!/usr/bin/env python3
"""Record downloaded lab runs in the local notebook; never sends files anywhere."""
import argparse
import hashlib
import json
from pathlib import Path
from log_experiment import append_entry

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory',type=Path,help='Local directory containing downloaded per-run run.json files')
    args=p.parse_args()
    if not args.directory.is_dir(): raise SystemExit('Results directory does not exist')
    records=[]
    for path in sorted(args.directory.rglob('run.json')):
        data=json.loads(path.read_text())
        if data.get('action') not in ['dc','pt']: continue
        if data.get('status') not in ['PASS','FAIL','RUNNING']: raise RuntimeError(f'Invalid status: {path}')
        records.append((data.get('start_unix',0),path,data))
    if not records: raise SystemExit('No DC/PrimeTime run records found')
    index=ROOT/'local_notes/imported_lab_runs.json'
    imported=set(json.loads(index.read_text())) if index.exists() else set()
    count=0
    for _,path,data in sorted(records):
        identity=hashlib.sha256(path.read_bytes()).hexdigest()
        if identity in imported: continue
        append_entry(f'匯入實驗室 {data["action"]} 執行紀錄',
                     '將實際實驗室結果附加至本機工程日誌。',
                     f'匯入排程 {data["policy"]}、佇列深度 {data["queue_depth"]}、時脈週期 {data["clock_ns"]} ns 的紀錄。',
                     '無（讀取已下載的綜合產物）',' '.join(data['command']),
                     f'工具流程狀態：{data["status"]}；產物位置：{path.parent}。PASS 僅表示流程完成，仍須檢查時序約束。',
                     '未取得或未解析的時序與面積結果不可視為通過。',
                     '每次綜合分別記錄；筆記留在本機，不傳回伺服器。',
                     '檢查映射面積、最差裕量、未約束路徑，並更新公開摘要。')
        imported.add(identity); count+=1
        index.parent.mkdir(exist_ok=True)
        index.write_text(json.dumps(sorted(imported),indent=2)+'\n')
    print(f'Appended {count} lab run entries locally')

if __name__=='__main__': main()
