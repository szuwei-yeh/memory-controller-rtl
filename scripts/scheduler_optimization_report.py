#!/usr/bin/env python3
"""Collect the paired scheduler experiment without replacing frozen v1.1 results."""
import csv
import hashlib
import json
from pathlib import Path
import re

from dc_sweep_report import parse_run
from scheduler_equiv import baseline_source

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / 'build/scheduler_opt'
OUT = ROOT / 'results/scheduler_optimization'
POINTS = [(16, 5), (16, 4), (16, 3), (32, 5)]


def read_json(path):
    return json.loads(path.read_text())


def main():
    current = {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
               for p in (ROOT/'synth/rtl_files.f').read_text().split()}
    baseline = dict(current)
    baseline['rtl/mc_scheduler_frfcfs.sv'] = hashlib.sha256(baseline_source().encode()).hexdigest()
    rows = []
    for variant, expected in [('baseline', baseline), ('decode_trial', current)]:
        for q, period in POINTS:
            directory = LOCAL / 'dc' / variant / f'q{q}_{period}ns'
            row = parse_run(directory)
            assert row['metadata']['rtl_sha256'] == expected, 'DC source mismatch'
            assert row['queue_depth'] == q and row['clock_ns'] == period
            assert row['policy'] == 'frfcfs_aging'
            environment = (directory/'environment.rpt').read_text()
            for expected_setting in ['nom_process: 1.000000','nom_voltage: 1.100000',
                                     'nom_temperature: 27.000000',
                                     'Time unit ns: 1.0; capacitance unit fF: 1000.0',
                                     f'Clock target ns: {period}; Q: {q}; policy: 1; aging: 1']:
                assert expected_setting in environment, 'DC environment mismatch'
            row['variant'] = variant
            area = (directory/'area.rpt').read_text()
            row['scheduler_area_um2'] = float(re.search(r'^frfcfs\.scheduler_i\s+([\d.]+)', area, re.M)[1])
            row['sequential_cells'] = int(re.search(r'Number of sequential cells:\s+(\d+)', area)[1])
            public = OUT / 'reports' / variant / directory.name
            public.mkdir(parents=True, exist_ok=True)
            raw_hashes, public_hashes = {}, {}
            for name in ['area.rpt','timing.rpt','hold.rpt','qor.rpt','check_timing.rpt','check_design.rpt']:
                raw = (directory/name).read_text()
                # Keep licensed library content and private site paths out of the artifact.
                sanitized = re.sub(r'/[^\s()]*?/gscl45nm\.db', '${TECH_LIBRARY_DIR}/gscl45nm.db', raw)
                assert not any(token in sanitized for token in ['/fs/','/Users/','/tmp/'])
                (public/name).write_text(sanitized)
                raw_hashes[name] = hashlib.sha256(raw.encode()).hexdigest()
                public_hashes[name] = hashlib.sha256(sanitized.encode()).hexdigest()
            (public/'hashes.json').write_text(json.dumps(dict(raw=raw_hashes,public=public_hashes),indent=2)+'\n')
            row['report_path'] = str(public.relative_to(ROOT))
            rows.append(row)
    assert len({r['metadata']['lab_config_sha256'] for r in rows}) == 1
    assert len({json.dumps(r['metadata']['flow_sha256'],sort_keys=True) for r in rows}) == 1
    expected_flow = rows[0]['metadata']['flow_sha256']
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in expected_flow.items())
    historical = read_json(ROOT/'results/dc_sweep/summary.json')['runs']
    for row in rows:
        if row['variant'] != 'baseline':
            continue
        old = next(r for r in historical if (r['policy'],r['queue_depth'],r['clock_ns']) ==
                   (row['policy'],row['queue_depth'],row['clock_ns']))
        for key in ['area_um2','setup_worst_slack_ns','worst_hold_slack_ns']:
            assert row[key] == old[key], f'Fresh baseline differs: {key}'
    equivalence = read_json(ROOT/'build/scheduler_equiv/summary.json')
    trace = read_json(ROOT/'build/scheduler_trace_compare/summary.json')
    regression = read_json(ROOT/'build/regress_summary.json')
    directed = read_json(ROOT/'build/test_summary.json')
    controller_formal = read_json(ROOT/'build/formal/summary.json')
    assert equivalence['status'] == trace['status'] == 'PASS'
    assert equivalence['source_sha256']['rtl/mc_scheduler_frfcfs.sv'] == current['rtl/mc_scheduler_frfcfs.sv']
    assert all(r['status']=='PASS' for r in controller_formal)
    # Every retained regression/directed run must belong to this RTL revision.
    for suite in [regression,directed]:
        for run in suite['results']:
            build = read_json(ROOT/run['path']/'run.json')['build']['source_sha256']
            assert all(build[p]==h for p,h in current.items())
    reset_proofs = []
    for q in [1,3,16]:
        for aging in ['plain','aging']:
            name=f'q{q}_{aging}'
            folder=LOCAL/f'equiv_final_{name}'
            assert (folder/'status').read_text().split()[0]=='PASS'
            assert (folder/'src/mc_scheduler_frfcfs.sv').read_bytes()==(ROOT/'rtl/mc_scheduler_frfcfs.sv').read_bytes()
            reset_proofs.append(dict(task=name,mode='prove',status='PASS',
                engine='smtbmc z3' if q<16 else 'abc pdr'))
    for key,build in trace['builds'].items():
        expected=current if key.startswith('after/') else baseline
        assert all(build['source_sha256'][p]==h for p,h in expected.items())
    proof_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in [ROOT/'formal/formal_scheduler_equiv.sv',ROOT/'formal/scheduler_equiv.sby',
                            ROOT/'scripts/scheduler_equiv.py',ROOT/'scripts/scheduler_trace_compare.py']}
    report=dict(status='COMPLETE',policy='frfcfs_aging',runs=rows,
        library_sha256=read_json(LOCAL/'lab_session.json')['library_sha256'],
        baseline_commit=read_json(LOCAL/'baseline.json')['baseline_commit'],
        baseline_rtl_sha256=baseline,current_rtl_sha256=current,verification_source_sha256=proof_hashes,
        fresh_baseline_reproduces_frozen_results=True,
        equivalence=equivalence,reset_equivalence=reset_proofs,
        trace_pairs=trace['pairs'],trace_simulations=2*trace['pairs'],
        trace_accepted_total=2*sum(r['accepted_per_revision'] for r in trace['results']),
        trace_source_sha256=hashlib.sha256((ROOT/'build/scheduler_trace_compare/summary.json').read_bytes()).hexdigest(),
        regression_runs=len(regression['results']),
        regression_accepted=sum(r['accepted'] for r in regression['results']),
        directed_corner_runs=len(directed['results']),controller_formal=controller_formal,
        negative_control=read_json(LOCAL/'mutation.json'),
        limits='Typical-corner pre-layout mapping only. Hold and zero-limit max-capacitance violations remain. No power, post-layout, signoff, or exact Fmax claim.')
    (OUT/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    fields=['variant','queue_depth','clock_ns','area_um2','scheduler_area_um2','sequential_cells',
            'setup_worst_slack_ns','setup_tns_ns','setup_violation_count','worst_hold_slack_ns',
            'hold_violation_count','max_capacitance_violation_count','unconstrained_endpoint_count']
    with (OUT/'summary.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore')
        writer.writeheader();writer.writerows(rows)
    table = ['| Q | Clock target (ns) | Area before (µm²) | Area after (µm²) | Area change | Worst setup slack before → after (ns) |',
             '|---:|---:|---:|---:|---:|---:|']
    for q,period in POINTS:
        before=next(r for r in rows if (r['variant'],r['queue_depth'],r['clock_ns'])==('baseline',q,period))
        after=next(r for r in rows if (r['variant'],r['queue_depth'],r['clock_ns'])==('decode_trial',q,period))
        delta=100*(after['area_um2']/before['area_um2']-1)
        table.append(f"| {q} | {period} | {before['area_um2']:,.2f} | {after['area_um2']:,.2f} | {delta:+.2f}% | {before['setup_worst_slack_ns']:+.6f} → {after['setup_worst_slack_ns']:+.6f} |")
    document=ROOT/'docs/experiments/scheduler-optimization.md'
    start,end='<!-- paired-table -->','<!-- /paired-table -->'
    text=document.read_text()
    assert text.count(start)==text.count(end)==1
    prefix,body=text.split(start)
    _,suffix=body.split(end)
    document.write_text(prefix+start+'\n\n'+'\n'.join(table)+'\n\n'+end+suffix)
    print('Verified and collected 8 matched DC runs, source provenance, equivalence, and regression evidence.')


if __name__ == '__main__':
    main()
