#!/usr/bin/env python3
"""Check command-mask/storage integration against the pinned compact-mask controller."""
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
BASELINE_LABEL = 'compact_mask (published source hashes)'
BASELINE_ALL_SHA256 = {
    "rtl/mc_transaction_table.sv": "1213002bd5421294bb59fa15931d803f42026eb589285456937a10ccb7b0cc2e",
    "rtl/mc_bank_tracker.sv": "741e658a9d2b8c689ff2d601055bb846a8f67c73d2dbf7c0c2513b1283fbc7c0",
    "rtl/mc_candidates.sv": "f71176cbcabf6ffd41a6505fe2349c933248e7be4afe944ec137c5f88e0efd5e",
    "rtl/mc_scheduler_strict_fcfs.sv": "a0227af2be484403dce915f27310d78468bb9944b8d3b5c6fe14754d2bd03ccb",
    "rtl/mc_scheduler_frfcfs.sv": "055fadfc5a1abe50539d5f753914b3b25da14f3b7de8009a95320d510042153c",
    "rtl/mc_response.sv": "6529334e9b51e6a2194d225019334f4d193c91bbefa05013c4b779d5b52037da",
    "rtl/mc_top.sv": "373c26b123414b6dc834d079eb87f43fd62fc2eb2a802bb1d0538dc15aefd5a8"
}
BASELINE_SHA256 = {p: BASELINE_ALL_SHA256[p] for p in ['rtl/mc_top.sv', 'rtl/mc_scheduler_frfcfs.sv', 'rtl/mc_transaction_table.sv']}

POLICIES = {'strict': (0, 0), 'frfcfs': (1, 0), 'aging': (1, 1)}


def baseline_sources():
    sources = {}
    for name, digest in BASELINE_SHA256.items():
        source = (ROOT/'formal/reference/command_mask'/Path(name).name).read_text()
        if hashlib.sha256(source.encode()).hexdigest() != digest:
            raise RuntimeError(f'Frozen reference changed: {name}')
        sources[name] = source
    return sources


from candidate_mask_equiv import proof_script


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trace', action='store_true')
    parser.add_argument('--depths', type=int, nargs='+', default=[1, 3, 16])
    parser.add_argument('--policies', choices=POLICIES, nargs='+', default=list(POLICIES))
    args = parser.parse_args()
    if any(q < 1 for q in args.depths):
        parser.error('Queue depths must be positive')
    for name, digest in BASELINE_ALL_SHA256.items():
        if name not in BASELINE_SHA256 and hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != digest:
            raise RuntimeError(f'Unplanned change outside the measured experiment: {name}')
    sources = baseline_sources()
    if args.trace:
        from scheduler_trace_compare import main as compare
        compare(sources=sources, label='command_mask', command='python3 scripts/command_mask_equiv.py --trace')
        return
    out = ROOT/'build/command_mask_equiv'
    files = (ROOT/'synth/rtl_files.f').read_text().split()
    hashes = {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files}
    for variant in ['before', 'after']:
        for name in files:
            dest = out/variant/name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT/name, dest)
            if variant == 'before' and name in sources:
                dest.write_text(sources[name])
    report = dict(status='INCOMPLETE', baseline_label=BASELINE_LABEL,
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
                    elapsed_s=time.monotonic()-start, log=f'build/command_mask_equiv/{name}.log'))
                print(name, report['results'][-1]['status'], flush=True)
                if not passed:
                    raise RuntimeError(f'Equivalence not proved: {name}')
        assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest() == h for p,h in hashes.items())
        report['status'] = 'PASS'
    finally:
        (out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
        append_entry('Command mask whole-controller 等價檢查', '驗證 command mask、scheduler/top 與 fixed-slot transaction table 的整合及狀態更新。',
            f"完成 {len(report['results'])} 個 queue-depth/policy 組合。", 'build/command_mask_equiv/',
            'python3 scripts/command_mask_equiv.py --depths '+' '.join(map(str,args.depths))+
            ' --policies '+' '.join(args.policies), report['status'],
            '匹配內部節點的 SAT 分割等價；所有未證明節點必須為零。相同 reset 建立相同狀態，未變模組在兩側相同。',
            '先 flatten、memory_map；opt_merge 只合併相同驅動的相同 cells。以三政策回歸與 trace 配對補充。',
            '與固定來源的 DC 面積／時序結果合併。')


if __name__ == '__main__':
    main()
