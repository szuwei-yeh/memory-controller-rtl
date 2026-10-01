#!/usr/bin/env python3
"""Check scheduler equivalence against the immutable v1.1 reference."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

from log_experiment import append_entry

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = 'formal/reference/mc_scheduler_frfcfs_v1.sv'
CURRENT = 'rtl/mc_scheduler_frfcfs.sv'
BASELINE_SHA256 = '7106fa600ff25041af4770918d8f304e5f109e5e7920efa421dd55b7e933704f'


def baseline_source():
    source = (ROOT / REFERENCE).read_text()
    source = source[source.index('module mc_scheduler_frfcfs_v1'):]
    source = source.replace('module mc_scheduler_frfcfs_v1', 'module mc_scheduler_frfcfs', 1)
    if hashlib.sha256(source.encode()).hexdigest() != BASELINE_SHA256:
        raise RuntimeError('Frozen reference differs from the measured v1.1 source')
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--depths', type=int, nargs='+', default=[1, 3, 16, 32])
    args = parser.parse_args()
    if 'candidate_mask' in (ROOT/'rtl/mc_scheduler_frfcfs.sv').read_text():
        parser.error('This encoded-interface checkpoint is archived at 27f522c; use make formal-command-mask for current RTL.')
    if any(q < 1 for q in args.depths):
        parser.error('Queue depths must be positive')
    baseline_source()
    out = ROOT / 'build/scheduler_equiv'
    out.mkdir(parents=True, exist_ok=True)
    version = subprocess.check_output(['yosys', '-V'], text=True).strip()
    report = dict(tool=version, baseline_sha256=BASELINE_SHA256,
                  source_sha256={p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
                                 for p in [REFERENCE, CURRENT]}, results=[])
    status = '未完成'
    try:
        for q in args.depths:
            for aging in [0, 1]:
                name = f'q{q}_aging{aging}'
                script = f'''read_verilog -sv {REFERENCE}
chparam -set Q_DEPTH {q} -set AGING_ENABLE {aging} mc_scheduler_frfcfs_v1
rename mc_scheduler_frfcfs_v1 gold
read_verilog -sv {CURRENT}
chparam -set Q_DEPTH {q} -set AGING_ENABLE {aging} mc_scheduler_frfcfs
rename mc_scheduler_frfcfs gate
proc
memory
equiv_make gold gate equiv
hierarchy -top equiv
equiv_simple -undef -short
equiv_status -assert
'''
                script_path = out / f'{name}.ys'
                script_path.write_text(script)
                command = ['yosys', '-Q', '-T', '-s', str(script_path)]
                start = time.time()
                with (out / f'{name}.log').open('w') as log:
                    result = subprocess.run(command, cwd=ROOT, stdout=log,
                                            stderr=subprocess.STDOUT, timeout=180)
                text = (out / f'{name}.log').read_text()
                counts = re.search(r'Of those cells (\d+) are proven and (\d+) are unproven', text)
                passed = result.returncode == 0 and counts is not None and int(counts[2]) == 0
                report['results'].append(dict(queue_depth=q, aging=aging,
                    status='PASS' if passed else 'FAIL', elapsed_s=time.time()-start,
                    proven_cells=int(counts[1]) if counts else None,
                    script=str(script_path.relative_to(ROOT)), log=f'build/scheduler_equiv/{name}.log'))
                print(name, report['results'][-1]['status'], flush=True)
                if not passed:
                    raise RuntimeError(f'Equivalence failed: {out/name}.log')
        status = 'PASS'
    finally:
        report['status'] = status
        (out / 'summary.json').write_text(json.dumps(report, indent=2)+'\n')
        append_entry('Scheduler SAT 等價檢查', '以固定 v1.1 reference 驗證 candidate decode 改寫。',
            f"完成 {len(report['results'])} 個 queue-depth/aging 組合。", 'build/scheduler_equiv/',
            'python3 scripts/scheduler_equiv.py --depths '+' '.join(map(str,args.depths)), status,
            '以對應內部訊號分割 SAT；未證明節點必須為零。無效 array index 不屬介面契約。',
            '檢查全部匹配節點，包含未變的狀態更新；共同 reset 建立相同初態。',
            '搭配 reset-based SymbiYosys harness 與整合回歸。')


if __name__ == '__main__':
    main()
