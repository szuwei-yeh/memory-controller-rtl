#!/usr/bin/env python3
"""Publish paired hold-only measurements after checking provenance and equivalence."""
import argparse
import json
from pathlib import Path
import re

from dc_sweep_report import constraint_rows, paths
from storage_timing_report import publish_reports, read, sha

ROOT = Path(__file__).resolve().parents[1]


def sdc_commands(path):
    return '\n'.join(line.strip() for line in path.read_text().splitlines()
                     if line.strip() and not line.lstrip().startswith('#'))+'\n'


def measured(folder, prefix):
    text = lambda name: (folder/f'{prefix}_{name}.rpt').read_text()
    sections = constraint_rows(text('constraints'))
    qor = text('qor')
    count = lambda label: int(float(re.search(re.escape(label)+r':\s+([\d.]+)', qor)[1]))
    fields = {'max_delay/setup': ('setup_violation_count', 'No. of Violating Paths'),
              'min_delay/hold': ('hold_violation_count', 'No. of Hold Violations'),
              'max_capacitance': ('max_capacitance_violation_count', 'Max Cap Violations'),
              'max_transition': ('max_transition_violation_count', 'Max Trans Violations')}
    row = {}
    for section, (key, label) in fields.items():
        row[key] = len(sections.get(section, []))
        assert row[key] == count(label), (prefix, section)
    checks = text('check_timing')
    assert 'Checking unconstrained_endpoints...' in checks
    diagnostic = checks.split('Checking unconstrained_endpoints...', 1)[1].split('Information:', 1)[0].strip()
    assert diagnostic in ['', '1'], diagnostic
    for name in ['check_timing', 'check_design', 'constraints']:
        assert not re.search(r'^Error:', text(name), re.M)
    row.update(area_um2=float(re.search(r'Total cell area:\s+([\d.]+)', text('area'))[1]),
        setup_worst_slack_ns=min(p['slack_ns'] for p in paths(text('setup'))),
        worst_hold_slack_ns=min(p['slack_ns'] for p in paths(text('hold'))),
        sequential_cells=count('Sequential Cell Count'), leaf_cells=count('Leaf Cell Count'),
        buffer_cells=count('Buf Cell Count'), unconstrained_endpoint_count=0,
        zero_allowed_load_violation_count=sum(p['required'] == 0 for p in sections.get('max_capacitance', [])))
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT/'build/hold_repair/final')
    parser.add_argument('--out', type=Path, default=ROOT/'results/hold_repair')
    args = parser.parse_args()
    source, out = args.source.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    previous = read(ROOT/'results/parallel_arbitration/summary.json')
    provenance = read(source/'provenance.json')
    assert provenance['status'] == 'TOOL_FLOW_COMPLETE'
    assert provenance['rtl_sha256'] == previous['current_rtl_sha256']
    assert provenance['library_sha256'] == previous['library_sha256']
    assert provenance['script_sha256'] == sha(ROOT/'synth/dc/repair_hold.tcl')
    for name, digest in provenance['rtl_sha256'].items():
        assert sha(ROOT/name) == digest
    runs, proofs = [], {}
    for period in [3, 4]:
        folder = source/f'q16_{period}ns'
        point = provenance['points'][str(period)]
        assert point['exit_code'] == 0 and (folder/'SUCCESS').exists()
        assert not re.search(r'^Error:', (folder/'tool.log').read_text(), re.M)
        assert 'R-2020.09-SP4' in (folder/'tool.log').read_text()
        for name, digest in point['report_sha256'].items():
            assert sha(folder/name) == digest, name
        proof = read(source/f'check_{period}ns/summary.json')
        assert proof['status'] == proof['equivalence']['status'] == 'PASS'
        assert proof['checker_sha256'] == sha(ROOT/'scripts/hold_repair_check.py')
        assert proof['equivalence']['unproven_cells'] == 0
        assert proof['equivalence']['before_sha256'] == sha(folder/'before.v')
        assert proof['equivalence']['after_sha256'] == sha(folder/'after.v')
        assert proof['negative_control']['status'] == 'REJECTED'
        assert proof['negative_control']['unproven_cells'] > 0
        proofs[str(period)] = proof
        before, after = [measured(folder, prefix) for prefix in ['before', 'after']]
        baseline = next(r for r in previous['runs'] if r['variant'] == 'parallel_classes' and r['clock_ns'] == period)
        for key, digest in previous['analysis_provenance']['points'][str(period)].items():
            assert point[key] == digest, (period, key)
        for key in ['area_um2', 'setup_worst_slack_ns', 'worst_hold_slack_ns',
                    'setup_violation_count', 'hold_violation_count', 'max_capacitance_violation_count']:
            assert before[key] == baseline[key], (period, key)
        assert before['sequential_cells'] == after['sequential_cells'] == 1974
        assert sdc_commands(folder/'before.sdc') == sdc_commands(folder/'after.sdc')
        assert 'BUFX2 output function: A' in (folder/'buffer_model.rpt').read_text()
        assert 'BUFX2 area: 2.346500' in (folder/'buffer_model.rpt').read_text()
        assert after['setup_violation_count'] == after['hold_violation_count'] == 0
        assert after['setup_worst_slack_ns'] >= before['setup_worst_slack_ns']
        assert after['worst_hold_slack_ns'] >= 0
        for key in ['max_capacitance_violation_count', 'max_transition_violation_count',
                    'zero_allowed_load_violation_count']:
            assert after[key] == before[key]
        dest = out/'reports'/folder.name
        names = [f'{prefix}_{name}.rpt' for prefix in ['before', 'after'] for name in
                 ['area', 'setup', 'hold', 'constraints', 'qor', 'references', 'check_design',
                  'check_timing', 'clocks', 'design']]
        names += ['before.sdc', 'after.sdc', 'buffer_model.rpt']
        publish_reports(folder, dest, names)
        proof_folder = source/f'check_{period}ns'
        for label in ['equivalence', 'negative_control']:
            log = (proof_folder/f'{label}.log').read_text()
            assert sha(proof_folder/f'{label}.log') == proof[label]['log_sha256']
            status = log.rsplit('Executing EQUIV_STATUS pass.', 1)[1]
            (proof_folder/f'{label}_status.rpt').write_text('Yosys EQUIV_STATUS excerpt\n'+status)
        publish_reports(proof_folder, out/'checks'/folder.name,
                        ['equivalence_status.rpt', 'negative_control_status.rpt'])
        runs.append(dict(clock_ns=period, queue_depth=16, policy='frfcfs_aging', before=before, after=after,
            inserted_buffers=after['buffer_cells']-before['buffer_cells'],
            area_increase_percent=100*(after['area_um2']/before['area_um2']-1),
            constraints_identical_excluding_comments=True, report_path=str(dest.relative_to(ROOT)),
            provenance=point))
    report = dict(status='EXPERIMENT_COMPLETE', measured_date='2026-10-03',
        current_rtl_sha256=provenance['rtl_sha256'], library_sha256=provenance['library_sha256'],
        repair_script_sha256=provenance['script_sha256'], publisher_sha256=sha(Path(__file__)),
        tool='Synopsys Design Compiler R-2020.09-SP4',
        corner='GSCL45nm typical, process=1, voltage=1.1V, temperature=27C',
        flow='Read retained parallel-arbitration DDC; set_fix_hold core_clk; compile -only_hold_time.',
        runs=runs, mapped_equivalence=proofs,
        limits='Q16 FR-FCFS+aging, ideal-clock typical-corner pre-layout DC setup/hold only. '
               '3 ns setup margin remains 0.038 ps. Zero-limit capacitance violations remain. '
               'No physical timing signoff, multicorner closure or power claim.')
    (out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    print('Published paired Q16/3 ns and 4 ns hold repair, with unchanged setup and mapped equivalence.')


if __name__ == '__main__':
    main()
