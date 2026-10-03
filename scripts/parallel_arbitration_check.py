#!/usr/bin/env python3
"""Check an isolated command-class arbitration trial against checkpoint 9d40e16."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time

from candidate_mask_equiv import proof_script, POLICIES

ROOT = Path(__file__).resolve().parents[1]
BASELINE = '9d40e165e8b071bbe20c01e16d8a12e20b6a8bbc'


def baseline_sources():
    hashes = json.loads((ROOT/'results/command_mask/summary.json').read_text())['current_rtl_sha256']
    sources = {}
    for p, digest in hashes.items():
        path = (ROOT/'formal/reference/parallel_arbitration/mc_scheduler_frfcfs.sv'
                if p == 'rtl/mc_scheduler_frfcfs.sv' else ROOT/p)
        sources[p] = path.read_bytes()
        assert hashlib.sha256(sources[p]).hexdigest() == digest, f'Baseline changed: {p}'
    return sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trial', type=Path, default=ROOT/'build/parallel_arbitration/trial')
    parser.add_argument('--out', type=Path, default=ROOT/'build/parallel_arbitration')
    parser.add_argument('--trace', action='store_true')
    parser.add_argument('--depths', type=int, nargs='+', default=[1, 3, 16])
    parser.add_argument('--prepare', action='store_true',
                        help='Reconstruct a new trial directory from the published variant and frozen reference')
    args = parser.parse_args()
    if any(q < 1 for q in args.depths):
        parser.error('Queue depths must be positive')
    trial, out = args.trial.resolve(), args.out.resolve()
    reference = baseline_sources()
    if args.prepare:
        if trial.exists():
            parser.error('--prepare requires a new trial directory')
        variant = ROOT/'results/parallel_arbitration/variant/rtl/mc_scheduler_frfcfs.sv'
        if not variant.is_file():
            parser.error('Published experiment variant is missing')
        files = (ROOT/'synth/rtl_files.f').read_text().split()
        for p in files + ['synth/rtl_files.f']:
            data = reference[p] if p in reference else (ROOT/p).read_bytes()
            dest = trial/p
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        shutil.copyfile(variant, trial/'rtl/mc_scheduler_frfcfs.sv')
    out.mkdir(parents=True, exist_ok=True)
    files = (ROOT/'synth/rtl_files.f').read_text().split()
    baseline = json.loads((ROOT/'results/command_mask/summary.json').read_text())['current_rtl_sha256']
    hashes = {p: hashlib.sha256((trial/p).read_bytes()).hexdigest() for p in files}
    sources = {}
    for p in files:
        data = reference[p]
        assert hashlib.sha256(data).hexdigest() == baseline[p]
        dest = out/'baseline'/p
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        if p == 'rtl/mc_scheduler_frfcfs.sv':
            sources[p] = data.decode()
        else:
            assert hashes[p] == baseline[p], f'Unexpected change: {p}'
    if args.trace:
        import scheduler_trace_compare as compare
        for p in ['synth/rtl_files.f', 'tb/dram_model.sv', 'tb/tb_top.sv']:
            dest = trial/p
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.resolve() != (ROOT/p).resolve():
                shutil.copyfile(ROOT/p, dest)
        compare.ROOT = trial
        compare.run.ROOT = trial
        compare.main(sources=sources, label='parallel_arbitration',
                     command='python3 scripts/parallel_arbitration_check.py --trace')
        shutil.copyfile(trial/'build/parallel_arbitration_trace_compare/summary.json', out/'trace_summary.json')
        return
    report = dict(status='INCOMPLETE', baseline_commit=BASELINE,
                  baseline_sha256=baseline, source_sha256=hashes,
                  tool=subprocess.check_output(['yosys', '-V'], text=True).strip(), results=[])
    try:
        for q in args.depths:
            for policy in POLICIES:
                name = f'q{q}_{policy}'
                script = out/(name+'.ys')
                script.write_text(proof_script(out/'baseline', trial, files, q, policy))
                started = time.monotonic()
                with (out/(name+'.log')).open('w') as log:
                    proc = subprocess.run(['yosys', '-Q', '-T', '-s', str(script)], cwd=ROOT,
                                          stdout=log, stderr=subprocess.STDOUT, timeout=1200)
                text = (out/(name+'.log')).read_text()
                counts = re.search(r'Of those cells (\d+) are proven and (\d+) are unproven', text)
                passed = proc.returncode == 0 and counts is not None and int(counts[2]) == 0
                report['results'].append(dict(queue_depth=q, policy=policy,
                    status='PASS' if passed else 'FAIL', proven_cells=int(counts[1]) if counts else None,
                    unproven_cells=int(counts[2]) if counts else None, elapsed_s=time.monotonic()-started))
                print(name, report['results'][-1]['status'], flush=True)
                if not passed:
                    raise RuntimeError('Equivalence failed: '+name+'\n'+text[-6000:])
        assert hashes == {p: hashlib.sha256((trial/p).read_bytes()).hexdigest() for p in files}
        report['status'] = 'PASS'
    finally:
        (out/'equiv_summary.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
