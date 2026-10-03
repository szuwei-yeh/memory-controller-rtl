#!/usr/bin/env python3
"""Publish measured storage experiments, including rejected alternatives."""
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil

from dc_sweep_report import parse_run, paths

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'results/storage_timing'
EXPERIMENTS = {'fixed_slot': 'storage_opt', 'free_valid': 'free_valid_opt'}
REPORTS = ['area.rpt', 'timing.rpt', 'hold.rpt', 'qor.rpt',
           'check_design.rpt', 'check_timing.rpt']


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def publish_reports(source, dest, names):
    dest.mkdir(parents=True, exist_ok=True)
    hashes = {'raw': {}, 'public': {}}
    for name in names:
        text = (source/name).read_text()
        text = re.sub(r'/[^\s()]*?/gscl45nm\.db', '${TECH_LIBRARY_DIR}/gscl45nm.db', text)
        text = '\n'.join(line.rstrip() for line in text.splitlines())+'\n'
        assert not re.search(r'/Users/|/fs/|/tmp/|szu-wei', text)
        (dest/name).write_text(text)
        hashes['raw'][name], hashes['public'][name] = sha(source/name), sha(dest/name)
    (dest/'hashes.json').write_text(json.dumps(hashes, indent=2)+'\n')
    return hashes


def internal_setup_count(row):
    return sum('/' in item['endpoint'] for item in row['setup_violations'])


def main():
    previous = read(ROOT/'results/candidate_mask/summary.json')
    baseline = previous['current_rtl_sha256']
    files = (ROOT/'synth/rtl_files.f').read_text().split()
    current = {p: sha(ROOT/p) for p in files}
    rows, verification, variants = [], {}, {}
    for period in [3, 4]:
        row = dict(next(r for r in previous['runs']
                        if (r['variant'], r['clock_ns']) == ('compact_mask', period)))
        row.update(variant='compact_baseline', baseline_reused=True)
        rows.append(row)
    for variant, name in EXPERIMENTS.items():
        folder = ROOT/'build'/name
        hashes = read(folder/'trial_hashes.json')
        assert read(folder/'baseline.json')['source_sha256'] == baseline
        assert read(folder/'lab_session.json')['library_sha256'] == previous['library_sha256']
        for p in files:
            assert sha(folder/'trial'/p) == hashes[p]
            if p != 'rtl/mc_transaction_table.sv':
                assert hashes[p] == baseline[p], 'Only the transaction table may change'
        eq = read(folder/'equiv_summary.json')
        assert eq['status'] == 'PASS' and eq['source_sha256'] == hashes
        assert {(r['queue_depth'], r['policy']) for r in eq['results']} == {
            (1, 'aging'), (3, 'strict'), (3, 'frfcfs'), (3, 'aging'), (16, 'aging')}
        assert all(r['status'] == 'PASS' for r in eq['results'])
        verification[variant], variants[variant] = eq, hashes
        dest = OUT/'variants'/variant/'mc_transaction_table.sv'
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(folder/'trial/rtl/mc_transaction_table.sv', dest)
        for period in [3, 4]:
            directory = folder/'dc'/f'q16_{period}ns'
            row = parse_run(directory)
            assert row['metadata']['rtl_sha256'] == hashes
            assert (row['queue_depth'], row['clock_ns'], row['policy']) == (16, period, 'frfcfs_aging')
            for key in ['lab_config_sha256', 'flow_sha256']:
                assert row['metadata'][key] == rows[0]['metadata'][key]
            environment = (directory/'environment.rpt').read_text()
            assert all(s in environment for s in ['nom_process: 1.000000', 'nom_voltage: 1.100000',
                       'nom_temperature: 27.000000', 'Time unit ns: 1.0; capacitance unit fF: 1000.0'])
            assert 'R-2020.09-SP4' in (directory/'tool.log').read_text()
            row['metadata'].pop('hostname', None)
            row.update(variant=variant, baseline_reused=False)
            row['sequential_cells'] = int(re.search(r'Number of sequential cells:\s+(\d+)',
                                                    (directory/'area.rpt').read_text())[1])
            assert row['sequential_cells'] == 1974
            target = OUT/'reports'/variant/directory.name
            publish_reports(directory, target, REPORTS)
            row['report_path'] = str(target.relative_to(ROOT))
            rows.append(row)
    for row in rows:
        row['internal_setup_violation_count'] = internal_setup_count(row)
    def point(variant, period):
        return next(r for r in rows if (r['variant'], r['clock_ns']) == (variant, period))
    screens = {}
    for variant in EXPERIMENTS:
        r3, r4 = point(variant, 3), point(variant, 4)
        b3, b4 = point('compact_baseline', 3), point('compact_baseline', 4)
        screens[variant] = {
            'three_ns_worst_setup_not_worse': r3['setup_worst_slack_ns'] >= b3['setup_worst_slack_ns'],
            'three_ns_internal_setup_count_reduced': internal_setup_count(r3) < internal_setup_count(b3),
            'four_ns_setup_pass': r4['setup_pass'],
            'four_ns_area_at_most_five_percent_more': r4['area_um2'] <= 1.05*b4['area_um2'],
            'hold_worst_slack_not_worse_at_both_points': all(point(variant, p)['worst_hold_slack_ns'] >=
                point('compact_baseline', p)['worst_hold_slack_ns'] for p in [3, 4]),
            'hold_count_not_worse_at_both_points': all(point(variant, p)['hold_violation_count'] <=
                point('compact_baseline', p)['hold_violation_count'] for p in [3, 4]),
        }
    qualified = [v for v in EXPERIMENTS if all(screens[v].values())]
    selected = next((v for v, h in variants.items() if h == current), None)
    if selected:
        assert selected in qualified
    else:
        assert current == baseline

    analysis = ROOT/'build/storage_opt'
    provenance = read(analysis/'analysis_provenance.json')
    assert provenance['source_sha256'] == baseline
    assert provenance['library_sha256'] == previous['library_sha256']
    assert provenance['script_sha256'] == sha(ROOT/'synth/dc/analyze_storage_paths.tcl')
    queries = {}
    for period in [3, 4]:
        folder = analysis/f'analysis_{period}ns'
        assert (folder/'SUCCESS').is_file()
        row = point('compact_baseline', period)
        assert float(re.search(r'Total cell area:\s+([\d.]+)', (folder/'area.rpt').read_text())[1]) == row['area_um2']
        assert provenance['points'][str(period)]['config_sha256'] == row['metadata']['lab_config_sha256']
        assert provenance['points'][str(period)]['sdc_sha256'] == sha(ROOT/'synth/constraints/controller.sdc')
        names = ['area.rpt', 'check_timing.rpt', 'clocks.rpt', 'read_data_setup.rpt',
                 'done_setup.rpt', 'register_to_register.rpt', 'hold.rpt']
        publish_reports(folder, OUT/'analysis'/f'q16_{period}ns', names)
        queries[str(period)] = {name: paths((folder/name).read_text()) for name in names if name not in names[:3]}
        assert min(p['slack_ns'] for p in queries[str(period)]['hold.rpt']) == row['worst_hold_slack_ns']

    summary = dict(status='EXPERIMENT_COMPLETE', baseline_label='compact_mask',
        baseline_evidence='results/candidate_mask/summary.json', baseline_rtl_sha256=baseline,
        library_sha256=previous['library_sha256'], fresh_baseline_rerun=False,
        variants=variants, source_sha256=current, selected_variant=selected,
        qualifying_variants=qualified, adoption_checks=screens, runs=rows,
        experimental_equivalence=verification, analysis_provenance=provenance,
        baseline_path_queries=queries,
        limits='Typical-corner Q16 pre-layout DC only. Hold and zero-limit capacitance violations remain. No waiver or signoff claim.')
    (OUT/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    keys = ['variant', 'clock_ns', 'area_um2', 'setup_worst_slack_ns', 'setup_tns_ns',
            'setup_violation_count', 'internal_setup_violation_count', 'worst_hold_slack_ns', 'hold_violation_count']
    with (OUT/'summary.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=keys, extrasaction='ignore', lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)
    table = [
        '| Variant | Target (ns) | Area (µm²) | Setup slack (ns) | Setup endpoints | Internal setup endpoints | Hold slack (ns) | Hold endpoints |',
        '|---|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for r in rows:
        table.append(f"| {r['variant']} | {r['clock_ns']} | {r['area_um2']:,.2f} | "
                     f"{r['setup_worst_slack_ns']:+.6f} | {r['setup_violation_count']} | "
                     f"{r['internal_setup_violation_count']} | {r['worst_hold_slack_ns']:+.6f} | {r['hold_violation_count']} |")
    doc = ROOT/'docs/experiments/storage-timing-experiment.md'
    text = doc.read_text()
    start, end = '<!-- measured-table -->', '<!-- /measured-table -->'
    assert text.count(start) == text.count(end) == 1
    prefix, rest = text.split(start); _, suffix = rest.split(end)
    doc.write_text(prefix+start+'\n\n'+'\n'.join(table)+'\n\n'+end+suffix)
    print(json.dumps(dict(qualified=qualified, selected=selected, checks=screens), indent=2))


if __name__ == '__main__':
    main()
