#!/usr/bin/env python3
"""Publish guarded incremental mapping only after timing/DRC/equivalence checks."""
import argparse
import json
from pathlib import Path
import re

from dc_sweep_report import paths
from hold_repair_report import measured, sdc_commands
from storage_timing_report import publish_reports, read, sha

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT/'build/setup_margin/preserve_zero_caps_50ps')
    parser.add_argument('--out', type=Path, default=ROOT/'results/setup_margin')
    args = parser.parse_args()
    source, out = args.source.resolve(), args.out.resolve()
    baseline = read(ROOT/'results/hold_repair/summary.json')
    provenance = read(source/'provenance.json')
    assert provenance['status'] == 'TOOL_FLOW_COMPLETE'
    assert provenance['setup_mode'] == 'preserve_zero_caps'
    assert provenance['setup_guard_ns'] == 0.05
    assert provenance['rtl_sha256'] == baseline['current_rtl_sha256']
    assert provenance['library_sha256'] == baseline['library_sha256']
    assert provenance['script_sha256'] == sha(ROOT/'synth/dc/improve_setup_margin.tcl')
    for name, digest in provenance['rtl_sha256'].items():
        assert sha(ROOT/name) == digest
    criteria = provenance['predeclared_criteria']
    assert criteria == read(ROOT/'build/setup_margin/baseline.json')['criteria']
    assert criteria['three_ns_setup_slack_at_least_ns'] == 0.020
    assert criteria['area_increase_at_most_percent'] == 5
    rows, proofs, checks = [], {}, {}
    for period in [3, 4]:
        folder = source/f'q16_{period}ns'
        point = provenance['points'][str(period)]
        old = next(r for r in baseline['runs'] if r['clock_ns'] == period)
        assert point['ddc_sha256'] == old['provenance']['report_sha256']['after.ddc']
        for key in ['config_sha256', 'sdc_sha256', 'library_sha256']:
            assert point[key] == old['provenance'][key]
        assert point['exit_code'] == 0 and (folder/'SUCCESS').exists()
        for name, digest in point['report_sha256'].items():
            assert sha(folder/name) == digest
        for path in [folder/'tool.log', *folder.glob('*.rpt')]:
            assert not re.search(r'^Error:', path.read_text(), re.M), path
        assert 'R-2020.09-SP4' in (folder/'tool.log').read_text()
        before, after = [measured(folder, prefix) for prefix in ['before', 'after']]
        assert before == old['after']
        assert before['sequential_cells'] == after['sequential_cells'] == 1974
        same_sdc = sdc_commands(folder/'before.sdc') == sdc_commands(folder/'after.sdc')
        target = (folder/'optimization_target.sdc').read_text()
        assert re.search(r'set_clock_uncertainty -setup 0\.15\s+\[get_clocks core_clk\]', target)
        assert re.search(r'set_clock_uncertainty -hold 0\.1\s+\[get_clocks core_clk\]', target)
        restricted = (folder/'restricted_cells.rpt').read_text()
        assert restricted.count('max_capacitance=0.000000') == 5
        internal = {}
        for prefix in ['before', 'after']:
            path = paths((folder/f'{prefix}_internal_setup.rpt').read_text())[0]
            assert path['classification'] == 'register-to-register'
            internal[prefix] = path
        proof_folder = source/f'final_check_{period}ns'
        proof = read(proof_folder/'summary.json')
        assert proof['status'] == proof['equivalence']['status'] == 'PASS'
        assert proof['checker_sha256'] == sha(ROOT/'scripts/setup_margin_check.py')
        assert proof['shared_checker_sha256'] == sha(ROOT/'scripts/hold_repair_check.py')
        assert len(proof['registers']) == len(set(proof['registers'])) == 1974
        assert proof['equivalence']['port_maps_identical']
        ports = proof['models']['before']['original_ports']
        assert all(direction in ['input', 'output'] and width > 0 for direction, width in ports.values())
        expected_inputs = 1974 + sum(width for direction, width in ports.values() if direction == 'input')
        expected_outputs = 2*1974 + sum(width for direction, width in ports.values() if direction == 'output')
        for label in ['before', 'after', 'mutated']:
            model = proof['models'][label]
            assert model['original_ports'] == ports
            assert model['input_bits'] == expected_inputs and model['output_bits'] == expected_outputs
            assert model['latch_count'] == 0
            assert model['port_map_sha256'] == proof['models']['before']['port_map_sha256']
            assert sha(proof_folder/f'{label}.map') == model['port_map_sha256']
            assert sha(proof_folder/f'{label}.aig') == model['aig_sha256']
        assert proof['liberty_sha256'] == baseline['mapped_equivalence'][str(period)]['liberty_sha256']
        assert proof['models']['before']['netlist_sha256'] == point['report_sha256']['before.v']
        assert proof['models']['after']['netlist_sha256'] == point['report_sha256']['after.v']
        assert proof['negative_control']['status'] == 'REJECTED'
        proofs[str(period)] = proof
        check = dict(zero_setup_and_hold=after['setup_violation_count'] == after['hold_violation_count'] == 0,
            setup_margin_target=after['setup_worst_slack_ns'] >= (0.020 if period == 3 else before['setup_worst_slack_ns']),
            area_within_budget=after['area_um2'] <= 1.05*before['area_um2'],
            capacitance_not_worse=after['max_capacitance_violation_count'] <= before['max_capacitance_violation_count'],
            transition_not_worse=after['max_transition_violation_count'] <= before['max_transition_violation_count'],
            final_sdc_unchanged=same_sdc, all_endpoints_constrained=after['unconstrained_endpoint_count'] == 0,
            mapped_equivalence=True, negative_control_rejected=True)
        assert all(check.values()), (period, check)
        checks[str(period)] = check
        rows.append(dict(clock_ns=period, queue_depth=16, policy='frfcfs_aging', before=before, after=after,
            register_to_register_setup=internal, constraints_identical_excluding_comments=same_sdc,
            area_increase_percent=100*(after['area_um2']/before['area_um2']-1),
            report_path=str((out/'reports'/folder.name).relative_to(ROOT)), provenance=point))
    # Do not create a public destination until all acceptance checks pass.
    out.mkdir(parents=True, exist_ok=False)
    for row in rows:
        period = row['clock_ns']
        folder = source/f'q16_{period}ns'
        names = [f'{prefix}_{name}.rpt' for prefix in ['before', 'after'] for name in
                 ['area', 'setup', 'hold', 'constraints', 'qor', 'references', 'check_design',
                  'check_timing', 'clocks', 'design', 'internal_setup']]
        names += ['before.sdc', 'after.sdc', 'optimization_target.sdc', 'restricted_cells.rpt', 'guarded_setup.rpt']
        publish_reports(folder, ROOT/row['report_path'], names)
        proof_folder = source/f'final_check_{period}ns'
        for label in ['equivalence', 'negative_control']:
            log = (proof_folder/f'{label}.log').read_text()
            assert sha(proof_folder/f'{label}.log') == proofs[str(period)][label]['log_sha256']
            if label == 'equivalence':
                assert re.search(r'^Networks are equivalent(?:\.| after structural hashing\.)', log, re.M)
            else:
                assert 'Networks are NOT EQUIVALENT.' in log
                lines = [line for line in log.splitlines() if line.startswith(
                    ('Networks are NOT EQUIVALENT.', 'Verification failed', 'Output ', 'Input pattern:'))]
                (proof_folder/'negative_control_status.rpt').write_text(
                    'Selected ABC status/counterexample lines; full raw log hash is retained in summary.json.\n'+
                    '\n'.join(lines)+'\n')
        publish_reports(proof_folder, out/'checks'/folder.name,
                        ['equivalence.log', 'negative_control_status.rpt', 'before.map', 'after.map', 'mutated.map'])
    report = dict(status='EXPERIMENT_COMPLETE', measured_date='2026-10-03',
        baseline_evidence='results/hold_repair/summary.json',
        current_rtl_sha256=provenance['rtl_sha256'], library_sha256=provenance['library_sha256'],
        setup_script_sha256=provenance['script_sha256'], publisher_sha256=sha(Path(__file__)),
        setup_guard_ns=0.05, setup_mode='preserve_zero_caps', predeclared_criteria=criteria,
        adoption_checks=checks, runs=rows, mapped_equivalence=proofs,
        tool='Synopsys Design Compiler R-2020.09-SP4',
        corner='GSCL45nm typical, process=1, voltage=1.1V, temperature=27C',
        flow='Preserve existing zero-cap reference instances; exclude these references during incremental '
             'high-effort mapping with additional 50 ps setup uncertainty. Restore library/cell attributes '
             'and original uncertainty; run hold-only repair; assess original constraints.',
        limits='Two Q16 FR-FCFS+aging, ideal-clock typical-corner pre-layout mappings. '
               'Inherited zero-limit capacitance violations remain; no physical or multicorner timing signoff.')
    (out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    print('Published guarded setup-margin mapping with original constraints, preserved hold and state/output equivalence.')


if __name__ == '__main__':
    main()
