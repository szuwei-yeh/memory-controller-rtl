#!/usr/bin/env python3
"""Collect shared-address PPA evidence against the recorded round-one baseline."""
import csv
import hashlib
import json
from pathlib import Path
import re

from address_equiv import BASELINE_COMMIT, baseline_sources
from dc_sweep_report import parse_run

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT/'build/address_opt'
OUT = ROOT/'results/address_sharing'
POINTS = [(16, 5), (16, 4), (16, 3), (32, 5)]
REPORTS = ['area.rpt', 'timing.rpt', 'hold.rpt', 'qor.rpt', 'check_timing.rpt', 'check_design.rpt']


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    current = {p: sha(ROOT/p) for p in (ROOT/'synth/rtl_files.f').read_text().split()}
    baseline = {**current, **{p: hashlib.sha256(s.encode()).hexdigest()
                             for p,s in baseline_sources().items()}}
    previous = read(ROOT/'results/scheduler_optimization/summary.json')
    assert previous['current_rtl_sha256'] == baseline, 'Baseline drifted from round one'
    assert read(LOCAL/'baseline.json')['baseline_commit'] == BASELINE_COMMIT
    library = read(LOCAL/'lab_session.json')['library_sha256']
    assert library == previous['library_sha256'], 'Technology library changed'
    rows = []
    for variant, expected in [('baseline', baseline), ('shared_address', current)]:
        for q, period in POINTS:
            key = f'q{q}_{period}ns'
            directory = (ROOT/'build/scheduler_opt/dc/decode_trial'/key if variant == 'baseline'
                         else LOCAL/'dc'/key)
            row = parse_run(directory)
            assert row['metadata']['rtl_sha256'] == expected, 'DC source mismatch'
            assert (row['policy'], row['queue_depth'], row['clock_ns']) == ('frfcfs_aging', q, period)
            environment = (directory/'environment.rpt').read_text()
            for setting in ['nom_process: 1.000000', 'nom_voltage: 1.100000',
                            'nom_temperature: 27.000000',
                            'Time unit ns: 1.0; capacitance unit fF: 1000.0',
                            f'Clock target ns: {period}; Q: {q}; policy: 1; aging: 1']:
                assert setting in environment, 'DC environment mismatch'
            assert 'R-2020.09-SP4' in (directory/'tool.log').read_text()
            row['variant'] = variant
            row['baseline_reused'] = variant == 'baseline'
            row['metadata'].pop('hostname', None)
            area = (directory/'area.rpt').read_text()
            row['sequential_cells'] = int(re.search(r'Number of sequential cells:\s+(\d+)', area)[1])
            row['block_area_um2'] = {name: float(re.search(r'^'+re.escape(name)+r'\s+([\d.]+)', area, re.M)[1])
                                    for name in ['candidates_i', 'response_i', 'table_i', 'frfcfs.scheduler_i', 'banks_i']}
            if variant == 'baseline':
                old = next(r for r in previous['runs'] if (r['variant'], r['queue_depth'], r['clock_ns']) ==
                           ('decode_trial', q, period))
                for metric in ['area_um2', 'setup_worst_slack_ns', 'worst_hold_slack_ns']:
                    assert row[metric] == old[metric], 'Reused baseline report differs'
                row['report_path'] = old['report_path']
                recorded = read(ROOT/old['report_path']/'hashes.json')
                assert all(sha(directory/name) == recorded['raw'][name] for name in REPORTS)
                assert all(sha(ROOT/old['report_path']/name) == recorded['public'][name] for name in REPORTS)
            else:
                public = OUT/'reports'/key
                public.mkdir(parents=True, exist_ok=True)
                raw_hashes, public_hashes = {}, {}
                for name in REPORTS:
                    raw = (directory/name).read_text()
                    sanitized = re.sub(r'/[^\s()]*?/gscl45nm\.db', '${TECH_LIBRARY_DIR}/gscl45nm.db', raw)
                    sanitized = '\n'.join(line.rstrip() for line in sanitized.splitlines())+'\n'
                    assert not any(token in sanitized for token in ['/fs/', '/Users/', '/tmp/'])
                    (public/name).write_text(sanitized)
                    raw_hashes[name], public_hashes[name] = sha(directory/name), sha(public/name)
                (public/'hashes.json').write_text(json.dumps(dict(raw=raw_hashes, public=public_hashes), indent=2)+'\n')
                row['report_path'] = str(public.relative_to(ROOT))
            rows.append(row)
    assert len({r['metadata']['lab_config_sha256'] for r in rows}) == 1
    # The earlier isolated driver did not record the Python launcher hash. The
    # actual source manifest, DC Tcl and constraints must match on both sides.
    for name in ['synth/rtl_files.f', 'synth/dc/run.tcl', 'synth/constraints/controller.sdc']:
        assert all(r['metadata']['flow_sha256'][name] == sha(ROOT/name) for r in rows)
    for row in rows:
        if row['variant'] == 'shared_address':
            assert row['metadata']['flow_sha256']['scripts/synth.py'] == sha(ROOT/'scripts/synth.py')
    for q, period in POINTS:
        pair = [r for r in rows if (r['queue_depth'], r['clock_ns']) == (q, period)]
        assert len({r['sequential_cells'] for r in pair}) == 1, 'Unexpected storage count change'
    equivalence = read(ROOT/'build/address_equiv/summary.json')
    trace = read(ROOT/'build/address_trace_compare/summary.json')
    assert equivalence['status'] == trace['status'] == 'PASS'
    assert equivalence['source_sha256'] == current and equivalence['baseline_sha256'] == baseline
    assert {(r['queue_depth'], r['policy']) for r in equivalence['results'] if r['status'] == 'PASS'} == {
        (q, p) for q in [1, 3, 16, 32] for p in ['strict', 'frfcfs', 'aging']}
    assert trace['pairs'] == 120
    for key, build in trace['builds'].items():
        expected = current if key.startswith('after/') else baseline
        assert all(build['source_sha256'][p] == h for p,h in expected.items())
    regression = read(ROOT/'build/regress_summary.json')
    directed = read(ROOT/'build/test_summary.json')
    for suite in [regression, directed]:
        for run in suite['results']:
            build = read(ROOT/run['path']/'run.json')['build']['source_sha256']
            assert all(build[p] == h for p,h in current.items())
    controller_formal = read(ROOT/'build/formal/summary.json')
    assert all(r['status'] == 'PASS' for r in controller_formal)
    for result in controller_formal:
        for path in (ROOT/'build/formal'/result['task']/'src').glob('mc_*.sv'):
            assert sha(path) == current['rtl/'+path.name], 'Formal source mismatch'
    mutation = read(LOCAL/'mutation.json')
    assert mutation['status'] == 'REJECTED'
    proof_paths = ['scripts/address_equiv.py', 'scripts/scheduler_trace_compare.py', 'tb/tb_response.sv']
    report = dict(status='COMPLETE', policy='frfcfs_aging', runs=rows,
        tool='Synopsys Design Compiler R-2020.09-SP4', compile_effort='medium',
        library_sha256=library, baseline_commit=BASELINE_COMMIT,
        baseline_reused_from='results/scheduler_optimization/summary.json: decode_trial',
        fresh_baseline_rerun=False, baseline_rtl_sha256=baseline, current_rtl_sha256=current,
        verification_source_sha256={p: sha(ROOT/p) for p in proof_paths},
        equivalence=equivalence, negative_control=mutation,
        trace_pairs=trace['pairs'], trace_simulations=2*trace['pairs'],
        trace_accepted_total=2*sum(r['accepted_per_revision'] for r in trace['results']),
        trace_source_sha256=sha(ROOT/'build/address_trace_compare/summary.json'),
        regression_runs=len(regression['results']), regression_accepted=sum(r['accepted'] for r in regression['results']),
        directed_corner_runs=len(directed['results']), controller_formal=controller_formal,
        limits='Typical-corner pre-layout mapping only. Hold and zero-limit max-capacitance violations remain. No power, post-layout, signoff, or exact Fmax claim.')
    (OUT/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    fields = ['variant', 'baseline_reused', 'queue_depth', 'clock_ns', 'area_um2', 'sequential_cells',
              'setup_worst_slack_ns', 'setup_tns_ns', 'setup_violation_count', 'worst_hold_slack_ns',
              'hold_violation_count', 'max_capacitance_violation_count', 'unconstrained_endpoint_count']
    with (OUT/'summary.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore', lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)
    table = ['| Q | Clock target (ns) | Area before (µm²) | Area after (µm²) | Area change | Worst setup slack before → after (ns) |',
             '|---:|---:|---:|---:|---:|---:|']
    for q,period in POINTS:
        before, after = [r for r in rows if (r['queue_depth'],r['clock_ns']) == (q,period)]
        delta = 100*(after['area_um2']/before['area_um2']-1)
        table.append(f"| {q} | {period} | {before['area_um2']:,.2f} | {after['area_um2']:,.2f} | {delta:+.2f}% | {before['setup_worst_slack_ns']:+.6f} → {after['setup_worst_slack_ns']:+.6f} |")
    document = ROOT/'docs/address-sharing-optimization.md'
    start, end = '<!-- paired-table -->', '<!-- /paired-table -->'
    text = document.read_text()
    assert text.count(start) == text.count(end) == 1
    prefix, body = text.split(start); _, suffix = body.split(end)
    document.write_text(prefix+start+'\n\n'+'\n'.join(table)+'\n\n'+end+suffix)
    print('Collected four new mapped points, four reused baselines, and matching verification evidence.')


if __name__ == '__main__':
    main()
