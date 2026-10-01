#!/usr/bin/env python3
"""Check candidate-mask integration against the pinned shared-address controller."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time

from log_experiment import append_entry

ROOT = Path(__file__).resolve().parents[1]
BASELINE_COMMIT = '12db3996def42219deb0d0d589ec2ac0c472f0cf'
BASELINE_SHA256 = {'rtl/mc_top.sv': '314bec72415cd8e0d268da3994f00260182754247a601fe579f48dbe1218678d', 'rtl/mc_candidates.sv': '4da7b37a9742faf6bc0d36b07e38d82c3e522b98474c6984114c2023be0662c3', 'rtl/mc_scheduler_frfcfs.sv': '76ec170f40b188b432f3c12c08ea9b3e37d4f11ed6ad04369bd80d60644ba418'}
POLICIES = {'strict': (0, 0), 'frfcfs': (1, 0), 'aging': (1, 1)}


def baseline_sources():
    sources = {}
    for name, digest in BASELINE_SHA256.items():
        source = (ROOT/'formal/reference/candidate_mask'/Path(name).name).read_text()
        if hashlib.sha256(source.encode()).hexdigest() != digest:
            raise RuntimeError(f'Frozen reference changed: {name}')
        sources[name] = source
    return sources


def proof_script(before, after, files, q, policy):
    scheduler, aging = POLICIES[policy]
    def design(root, name):
        return '\n'.join([
            'read_verilog -sv -D SYNTHESIS '+' '.join(str(root/p) for p in files),
            f'chparam -set Q_DEPTH {q} -set SCHED_POLICY {scheduler} -set AGING_ENABLE {aging} mc_top',
            'prep -flatten -top mc_top', 'memory_map', 'opt_clean', f'rename mc_top {name}',
        ])
    return '\n'.join([
        design(before, 'gold'), 'design -stash gold', design(after, 'gate'),
        'design -copy-from gold -as gold gold', 'equiv_make gold gate equiv',
        'hierarchy -top equiv', 'opt_merge', 'opt_clean',
        'equiv_simple -undef -short', 'equiv_status -assert', '',
    ])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trace', action='store_true')
    parser.add_argument('--depths', type=int, nargs='+', default=[1, 3, 16])
    parser.add_argument('--policies', choices=POLICIES, nargs='+', default=list(POLICIES))
    args = parser.parse_args()
    if 'select_mask' in (ROOT/'rtl/mc_scheduler_frfcfs.sv').read_text():
        parser.error('This experiment uses the frozen compact candidate-mask snapshot; use make formal-command-mask / compare-command-mask for current RTL.')
    if any(q < 1 for q in args.depths):
        parser.error('Queue depths must be positive')
    sources = baseline_sources()
    if args.trace:
        from scheduler_trace_compare import main as compare
        compare(sources=sources, label='candidate_mask', command='python3 scripts/candidate_mask_equiv.py --trace')
        return
    out = ROOT/'build/candidate_mask_equiv'
    files = (ROOT/'synth/rtl_files.f').read_text().split()
    hashes = {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files}
    for variant in ['before', 'after']:
        for name in files:
            dest = out/variant/name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT/name, dest)
            if variant == 'before' and name in sources:
                dest.write_text(sources[name])
    report = dict(status='INCOMPLETE', baseline_commit=BASELINE_COMMIT,
        baseline_sha256={**hashes, **BASELINE_SHA256}, source_sha256=hashes,
        tool=subprocess.check_output(['yosys', '-V'], text=True).strip(), results=[])
    try:
        for q in args.depths:
            for policy in args.policies:
                name = f'q{q}_{policy}'
                script = out/f'{name}.ys'
                script.write_text(proof_script(out/'before', out/'after', files, q, policy))
                start = time.monotonic()
                with (out/f'{name}.log').open('w') as log:
                    proc = subprocess.run(['yosys', '-Q', '-T', '-s', str(script)], cwd=ROOT,
                        stdout=log, stderr=subprocess.STDOUT, timeout=1200)
                log = (out/f'{name}.log').read_text()
                counts = re.search(r'Of those cells (\d+) are proven and (\d+) are unproven', log)
                passed = proc.returncode == 0 and counts is not None and int(counts[2]) == 0
                report['results'].append(dict(queue_depth=q, policy=policy,
                    status='PASS' if passed else 'FAIL', proven_cells=int(counts[1]) if counts else None,
                    elapsed_s=time.monotonic()-start, log=f'build/candidate_mask_equiv/{name}.log'))
                print(name, report['results'][-1]['status'], flush=True)
                if not passed:
                    raise RuntimeError(f'Equivalence not proved: {name}')
        assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest() == h for p,h in hashes.items())
        report['status'] = 'PASS'
    finally:
        (out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
        append_entry('Candidate mask whole-controller 等價檢查', '驗證 candidate mask、scheduler、top 的實際整合接線及狀態更新。',
            f"完成 {len(report['results'])} 個 queue-depth/policy 組合。", 'build/candidate_mask_equiv/',
            'python3 scripts/candidate_mask_equiv.py --depths '+' '.join(map(str,args.depths))+
            ' --policies '+' '.join(args.policies), report['status'],
            '匹配內部節點的 SAT 分割等價；所有未證明節點必須為零。相同 reset 建立相同狀態，未變模組在兩側相同。',
            '先 flatten、memory_map；opt_merge 只合併相同驅動的相同 cells。以三政策回歸與 trace 配對補充。',
            '與固定來源的 DC 面積／時序結果合併。')


if __name__ == '__main__':
    main()
