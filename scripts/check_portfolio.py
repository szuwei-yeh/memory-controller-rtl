#!/usr/bin/env python3
"""Check current RTL against published PPA/verification evidence, without EDA tools."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

from dc_sweep_report import constraint_rows, paths

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def main():
    folder = ROOT/'results/parallel_arbitration'
    summary = read(folder/'summary.json')
    assert summary['status'] == 'EXPERIMENT_COMPLETE'
    assert summary['selected_variant'] == 'parallel_classes'
    assert summary['trial_qualifies'] and all(summary['adoption_checks'].values())
    sources = summary['current_rtl_sha256']
    assert sources == summary['trial_rtl_sha256']
    assert set(sources) == set((ROOT/'synth/rtl_files.f').read_text().split())
    for name, digest in sources.items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == digest, name
    assert (ROOT/'rtl/mc_scheduler_frfcfs.sv').read_bytes() == (
        folder/'variant/rtl/mc_scheduler_frfcfs.sv').read_bytes()
    reference = ROOT/'formal/reference/parallel_arbitration/mc_scheduler_frfcfs.sv'
    assert hashlib.sha256(reference.read_bytes()).hexdigest() == summary['baseline_rtl_sha256']['rtl/mc_scheduler_frfcfs.sv']
    assert summary['lint']['status'] == 'PASS' and summary['lint']['source_sha256'] == sources
    assert summary['negative_control']['status'] == 'REJECTED'
    assert summary['negative_control']['unproven_cells'] > 0
    validation = read(folder/'validation_summary.json')
    assert validation == summary['validation']
    assert validation['status'] == 'PASS' and validation['source_sha256'] == sources
    for eq in [summary['equivalence'], validation['current_equivalence']]:
        assert eq['status'] == 'PASS' and eq['source_sha256'] == sources
        assert len(eq['results']) == 9
        assert {(r['queue_depth'], r['policy']) for r in eq['results']} == {
            (q, p) for q in [1, 3, 16] for p in ['strict', 'frfcfs', 'aging']}
        assert all(r['status'] == 'PASS' and r['unproven_cells'] == 0 for r in eq['results'])
    assert validation['counts']['test']['runs'] == 42
    assert validation['counts']['regress']['runs'] == 300
    assert validation['counts']['regress']['accepted'] == 3003000
    assert len(validation['controller_formal']) == 5
    assert all(r['status'] == 'PASS' for r in validation['controller_formal'])
    trace_file = folder/'trace_summary.json'
    assert hashlib.sha256(trace_file.read_bytes()).hexdigest() == summary['trace_summary_sha256']
    trace = read(trace_file)
    assert trace['status'] == 'PASS' and trace['pairs'] == len(trace['results']) == 120
    for label, build in trace['builds'].items():
        expected = summary['baseline_rtl_sha256'] if label.startswith('before/') else sources
        assert all(build['source_sha256'][p] == h for p, h in expected.items())
    for manifest in sorted(folder.glob('**/hashes.json')):
        for name, digest in read(manifest)['public'].items():
            assert hashlib.sha256((manifest.parent/name).read_bytes()).hexdigest() == digest, name
    for row in summary['runs']:
        if row['variant'] != 'parallel_classes':
            continue
        reports = ROOT/row['report_path']
        assert row['metadata']['rtl_sha256'] == sources
        area = float(re.search(r'Total cell area:\s+([\d.]+)', (reports/'area.rpt').read_text())[1])
        assert area == row['area_um2']
        assert min(p['slack_ns'] for p in paths((reports/'timing.rpt').read_text())) == row['setup_worst_slack_ns']
        assert min(p['slack_ns'] for p in paths((reports/'hold.rpt').read_text())) == row['worst_hold_slack_ns']
        constraints = constraint_rows((reports/'constraints.rpt').read_text())
        for section, key in [('max_delay/setup', 'setup_violation_count'),
                             ('min_delay/hold', 'hold_violation_count'),
                             ('max_capacitance', 'max_capacitance_violation_count')]:
            assert len(constraints.get(section, [])) == row[key]
        assert row['setup_pass'] and row['hold_violation_count'] > 0
        print(f"Q16/{row['clock_ns']} ns: area={area:.6f} um^2, setup={row['setup_worst_slack_ns']:+.6f} ns, "
              f"hold={row['worst_hold_slack_ns']:+.6f} ns / {row['hold_violation_count']} endpoints")
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    assert not any(p.startswith('local_notes/') for p in tracked)
    assert not any(p.endswith(('.db', '.ddc', '.lib')) for p in tracked if p)
    print('PASS: current source, published report hashes, timing/area numbers and verification summaries agree.')
    print('Evidence audit only: this does not rerun simulation, formal proofs or licensed synthesis.')


if __name__ == '__main__':
    main()
