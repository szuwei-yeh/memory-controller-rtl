#!/usr/bin/env python3
"""Diagnose retained zero-cap limits and account for every violating net load."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re

from dc_sweep_report import constraint_rows
from hold_repair_report import measured, sdc_commands
from storage_timing_report import publish_reports, read, sha

ROOT = Path(__file__).resolve().parents[1]
NET_TOL = 5e-8       # Native connection-report precision, in pF.
CONSTRAINT_TOL = 5.1e-7  # Six decimal places in constraint/attribute reports.


def groups(text, keyword):
    """Extract named Liberty groups, respecting quoted strings and comments."""
    text = re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)
    for match in re.finditer(r'\b'+keyword+r'\s*\(\s*([^()]*)\s*\)\s*\{', text):
        depth, index, start, quoted = 1, match.end(), match.end(), False
        while depth:
            char = text[index]
            if char == '\\' and quoted:
                index += 2
                continue
            if char == '"':
                quoted = not quoted
            elif not quoted:
                depth += (char == '{') - (char == '}')
            index += 1
        yield match[1].strip(), text[start:index-1]


def library_metadata(path):
    text = path.read_text()
    assert len(list(groups(text, 'library'))) == 1
    assert next(groups(text, 'library'))[0] == 'gscl45nm'
    assert re.search(r'capacitive_load_unit\s*\(\s*1\s*,\s*pf\s*\)', text)
    assert re.search(r'time_unit\s*:\s*"1ns"', text)
    templates = {name: body for name, body in groups(text, 'lu_table_template')}
    inputs, outputs, cells = {}, {}, []
    for cell, body in groups(text, 'cell'):
        cells.append(cell)
        for pin, definition in groups(body, 'pin'):
            direction = re.search(r'\bdirection\s*:\s*(\w+)', definition)[1]
            values = {key: float(value) for key, value in re.findall(
                r'\b(capacitance|rise_capacitance|fall_capacitance|max_capacitance)\s*:\s*([\d.eE+-]+)', definition)}
            key = cell+'/'+pin
            if direction == 'input':
                assert set(values) >= {'capacitance', 'rise_capacitance', 'fall_capacitance'}
                inputs[key] = values
            elif direction in ['output', 'inout']:
                assert 'max_capacitance' in values
                bounds = set()
                for kind in ['cell_rise', 'cell_fall']:
                    for template, table in groups(definition, kind):
                        axes = dict(re.findall(r'variable_(\d)\s*:\s*(\w+)', templates[template]))
                        axis = next((k for k, v in axes.items() if v == 'total_output_net_capacitance'), None)
                        if axis is None:
                            continue
                        indices = re.search(r'index_'+axis+r'\s*\(\s*"([^"]+)"', table)[1]
                        numbers = [float(v.strip()) for v in indices.split(',')]
                        bounds.add((min(numbers), max(numbers)))
                outputs[key] = dict(max_capacitance_pf=values['max_capacitance'],
                    explicitly_defined=True, dynamic_max_cap_group=bool(list(groups(definition, 'max_cap'))),
                    delay_load_axis_bounds_pf=[list(pair) for pair in sorted(bounds)])
    assert len(cells) == len(set(cells))
    return dict(liberty_sha256=sha(path), library='gscl45nm', capacitance_unit_pf=1.0,
                capacitance_unit_fF=1000.0, time_unit_ns=1.0, cells=sorted(cells),
                inputs=inputs, outputs=outputs)


def connection_blocks(path):
    parts = re.split(r"\nnet '([^']+)':\n", path.read_text())
    result = dict(zip(parts[1::2], parts[2::2]))
    assert len(result) == len(parts[1::2]), 'Duplicated reported net'
    return result


def account_loads(folder, library):
    drivers = list(csv.DictReader((folder/'zero_drivers.tsv').open(), delimiter='\t'))
    mapped = {row['net']: row for row in drivers}
    blocks = connection_blocks(folder/'zero_nets.rpt')
    constraints = {row['endpoint']: row for row in constraint_rows(
        (folder/'audit_constraints.rpt').read_text())['max_capacitance']}
    assert len(mapped) == len(drivers) and set(mapped) == set(blocks) == set(constraints)
    rows = []
    for net in sorted(mapped):
        driver, body, violation = mapped[net], blocks[net], constraints[net]
        pins = re.findall(r'^\s+(\S+)\s+(Input|Output) Pin \((\w+)\)\s+([\d.eE+-]+)\s*$', body, re.M)
        outputs = [row for row in pins if row[1] == 'Output']
        inputs = [row for row in pins if row[1] == 'Input']
        assert len(outputs) == 1 and outputs[0][0] == driver['driver_pin']
        assert outputs[0][2] == driver['reference']
        assert int(re.search(r'number of drivers:\s+(\d+)', body)[1]) == 1
        assert int(re.search(r'number of loads:\s+(\d+)', body)[1]) == len(inputs) > 0
        assert not re.search(r'\b(?:Input|Output|Inout) Port\b', body)
        sink_pins = []
        for pin, _, ref, cap in inputs:
            key = ref+'/'+pin.rsplit('/', 1)[1]
            assert abs(float(cap)-library['inputs'][key]['capacitance']) <= NET_TOL
            sink_pins.append(key)
        sums = {key: sum(library['inputs'][p][key] for p in sink_pins)
                for key in ['capacitance', 'rise_capacitance', 'fall_capacitance']}
        stats = {}
        for label in ['pin', 'wire', 'total']:
            match = re.search(label+r' capacitance:\s+min:([\d.eE+-]+)\s+max:([\d.eE+-]+)', body)
            stats[label] = [float(match[1]), float(match[2])]
        assert stats['wire'] == [0.0, 0.0]
        expected = sorted([sums['rise_capacitance'], sums['fall_capacitance']])
        assert all(abs(a-b) <= NET_TOL for a, b in zip(stats['pin'], expected))
        assert stats['total'] == stats['pin']
        assert abs(violation['actual']-sums['capacitance']) <= CONSTRAINT_TOL
        assert violation['actual'] == float(driver['actual_capacitance_library_units'])
        output_key = driver['reference']+'/'+driver['driver_pin'].rsplit('/', 1)[1]
        assert library['outputs'][output_key]['max_capacitance_pf'] == violation['required'] == 0
        assert float(driver['max_capacitance_library_units']) == 0
        rows.append(dict(net=net, driver_pin=driver['driver_pin'], reference=driver['reference'],
            sink_library_pins=';'.join(sorted(sink_pins)), sink_count=len(inputs),
            nominal_pin_sum_pf=sums['capacitance'], rise_pin_sum_pf=sums['rise_capacitance'],
            fall_pin_sum_pf=sums['fall_capacitance'], report_net_pin_min_pf=stats['pin'][0],
            report_net_pin_max_pf=stats['pin'][1], wire_capacitance_pf=0.0,
            report_net_total_max_pf=stats['total'][1], constraint_required_pf=0.0,
            constraint_actual_pf=violation['actual']))
    return rows, blocks


def load_statistics(rows):
    values = [float(row['nominal_pin_sum_pf']) for row in rows]
    return dict(violating_nets=len(rows), driver_reference_counts=dict(sorted(Counter(
        row['reference'] for row in rows).items())), sink_count_histogram=dict(sorted(Counter(
        str(row['sink_count']) for row in rows).items())),
        nominal_load_min_pf=min(values), nominal_load_max_pf=max(values),
        wire_capacitance_nonzero_count=sum(float(row['wire_capacitance_pf']) != 0 for row in rows),
        below_delay_load_grid_count=len(rows))


def check_published(folder, previous):
    """Audit committed derivatives and native reports without private libraries."""
    summary, library = read(folder/'summary.json'), read(folder/'library_metadata.json')
    assert summary['status'] == 'DIAGNOSIS_COMPLETE_NO_REPAIR'
    assert summary['baseline_evidence'] == 'results/setup_margin/summary.json'
    assert summary['current_rtl_sha256'] == previous['current_rtl_sha256']
    assert summary['library_sha256'] == previous['library_sha256']
    assert summary['script_sha256'] == sha(ROOT/'synth/dc/diagnose_capacitance.tcl')
    assert summary['publisher_sha256'] == sha(Path(__file__))
    assert sha(folder/'library_metadata.json') == summary['library_metadata_sha256']
    assert library['capacitance_unit_fF'] == 1000 and library['capacitance_unit_pf'] == 1
    zeros = sorted(k for k, v in library['outputs'].items() if v['max_capacitance_pf'] == 0)
    assert summary['zero_limit_library_outputs'] == zeros
    assert [row['clock_ns'] for row in summary['runs']] == [3, 4]
    for manifest in folder.glob('**/hashes.json'):
        for name, digest in read(manifest)['public'].items():
            assert sha(manifest.parent/name) == digest
    for row in summary['runs']:
        period = row['clock_ns']
        old = next(r for r in previous['runs'] if r['clock_ns'] == period)
        reports = ROOT/row['report_path']
        assert measured(reports, 'audit') == row['observed'] == old['after']
        assert sdc_commands(reports/'query.sdc') == sdc_commands(ROOT/old['report_path']/'after.sdc')
        assert row['original_sdc_unchanged']
        point = row['provenance']
        assert point['exit_code'] == 0
        assert point['ddc_sha256'] == old['provenance']['report_sha256']['after.ddc']
        assert point['config_sha256'] == old['provenance']['config_sha256']
        assert point['library_sha256'] == previous['library_sha256']
        assert point['liberty_sha256'] == library['liberty_sha256'] == previous['mapped_equivalence'][str(period)]['liberty_sha256']
        environment = dict(line.split('=', 1) for line in (reports/'environment.rpt').read_text().splitlines())
        assert float(environment['capacitive_load_units_fF']) == float(environment['config_capacitance_unit_fF']) == 1000
        assert environment['time_unit_name'] == 'ns' and float(environment['config_time_unit_ns']) == 1
        limits = list(csv.DictReader((reports/'db_limits.tsv').open(), delimiter='\t'))
        assert {v['library_pin'].removeprefix('gscl45nm/') for v in limits} == set(library['outputs'])
        for limit in limits:
            key = limit['library_pin'].removeprefix('gscl45nm/')
            assert abs(float(limit['max_capacitance_library_units'])-library['outputs'][key]['max_capacitance_pf']) <= CONSTRAINT_TOL
        for name, digest in row['derived_sha256'].items():
            assert sha(reports/name) == digest
        loads = list(csv.DictReader((reports/'load_accounting.csv').open()))
        constraints = {v['endpoint']: v for v in constraint_rows((reports/'audit_constraints.rpt').read_text())['max_capacitance']}
        assert len(loads) == len({v['net'] for v in loads}) == len(constraints)
        assert {v['net'] for v in loads} == set(constraints)
        for load in loads:
            sinks = load['sink_library_pins'].split(';')
            assert len(sinks) == int(load['sink_count']) > 0
            for field, source in [('nominal_pin_sum_pf', 'capacitance'), ('rise_pin_sum_pf', 'rise_capacitance'), ('fall_pin_sum_pf', 'fall_capacitance')]:
                assert abs(float(load[field])-sum(library['inputs'][p][source] for p in sinks)) <= NET_TOL
            expected = sorted([float(load['rise_pin_sum_pf']), float(load['fall_pin_sum_pf'])])
            assert abs(float(load['report_net_pin_min_pf'])-expected[0]) <= NET_TOL
            assert abs(float(load['report_net_pin_max_pf'])-expected[1]) <= NET_TOL
            assert float(load['wire_capacitance_pf']) == 0
            assert float(load['report_net_total_max_pf']) == float(load['report_net_pin_max_pf'])
            violation = constraints[load['net']]
            assert float(load['constraint_actual_pf']) == violation['actual']
            assert abs(violation['actual']-float(load['nominal_pin_sum_pf'])) <= CONSTRAINT_TOL
            key = load['reference']+'/'+load['driver_pin'].rsplit('/', 1)[1]
            output = library['outputs'][key]
            assert output['explicitly_defined'] and not output['dynamic_max_cap_group']
            assert output['max_capacitance_pf'] == float(load['constraint_required_pf']) == violation['required'] == 0
            assert float(load['nominal_pin_sum_pf']) > 0
            assert output['delay_load_axis_bounds_pf']
            assert all(float(load['nominal_pin_sum_pf']) < low for low, high in output['delay_load_axis_bounds_pf'])
        assert load_statistics(loads) == row['load_statistics']
        assert row['load_statistics']['violating_nets'] == row['observed']['max_capacitance_violation_count']
        assert read(reports/'hashes.json')['raw'].items() <= point['report_sha256'].items()
        print(f"Capacitance diagnosis Q16/{period} ns: {len(loads)} zero-limit driver nets, all positive pin loads, zero modeled wire capacitance; no repair claimed.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT/'build/capacitance_diagnosis/canonical')
    parser.add_argument('--liberty', type=Path, default=ROOT/'build/hold_repair/gscl45nm.lib')
    parser.add_argument('--out', type=Path, default=ROOT/'results/capacitance_diagnosis')
    args = parser.parse_args()
    source, out = args.source.resolve(), args.out.resolve()
    previous, provenance = read(ROOT/'results/setup_margin/summary.json'), read(source/'provenance.json')
    assert provenance['status'] == 'TOOL_FLOW_COMPLETE'
    assert provenance['script_sha256'] == sha(ROOT/'synth/dc/diagnose_capacitance.tcl')
    assert provenance['current_rtl_sha256'] == previous['current_rtl_sha256']
    for name, digest in provenance['current_rtl_sha256'].items():
        assert sha(ROOT/name) == digest
    library, prepared = library_metadata(args.liberty), []
    for period in [3, 4]:
        folder, point = source/f'q16_{period}ns', provenance['points'][str(period)]
        old = next(r for r in previous['runs'] if r['clock_ns'] == period)
        assert point['exit_code'] == 0 and (folder/'SUCCESS').exists()
        assert point['ddc_sha256'] == old['provenance']['report_sha256']['after.ddc']
        assert point['config_sha256'] == old['provenance']['config_sha256']
        assert point['library_sha256'] == previous['library_sha256']
        assert point['liberty_sha256'] == library['liberty_sha256'] == previous['mapped_equivalence'][str(period)]['liberty_sha256']
        for name, digest in point['report_sha256'].items():
            assert sha(folder/name) == digest
        for path in [folder/'tool.log', *folder.glob('*.rpt')]:
            assert not re.search(r'^ERROR:|^Error:', path.read_text(), re.M), path
        assert measured(folder, 'audit') == old['after']
        assert sdc_commands(folder/'query.sdc') == sdc_commands(ROOT/old['report_path']/'after.sdc')
        rows, blocks = account_loads(folder, library)
        prepared.append((period, folder, point, rows, blocks))
    out.mkdir(parents=True, exist_ok=False)
    (out/'library_metadata.json').write_text(json.dumps(library, indent=2)+'\n')
    runs = []
    for period, folder, point, rows, blocks in prepared:
        dest = out/'reports'/folder.name
        names = [f'audit_{name}.rpt' for name in ['area', 'setup', 'hold', 'constraints', 'qor', 'references', 'check_timing', 'check_design', 'design']]
        names += ['environment.rpt', 'db_limits.tsv', 'query.sdc']
        publish_reports(folder, dest, names)
        with (dest/'load_accounting.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
        chosen = [min(rows, key=lambda r: r['nominal_pin_sum_pf'])['net'],
                  max(rows, key=lambda r: r['nominal_pin_sum_pf'])['net'],
                  max(rows, key=lambda r: r['nominal_pin_sum_pf']-r['report_net_pin_max_pf'])['net']]
        examples = 'Selected native connection-report blocks; full raw report digest is retained in summary.json.\n'
        for net in dict.fromkeys(chosen):
            examples += "\nnet '"+net+"':\n"+blocks[net]
        (dest/'examples.rpt').write_text('\n'.join(v.rstrip() for v in examples.splitlines())+'\n')
        runs.append(dict(clock_ns=period, queue_depth=16, policy='frfcfs_aging',
            observed=measured(folder, 'audit'), original_sdc_unchanged=True,
            load_statistics=load_statistics(rows), report_path=str(dest.relative_to(ROOT)),
            derived_sha256={name: sha(dest/name) for name in ['load_accounting.csv', 'examples.rpt']}, provenance=point))
    summary = dict(status='DIAGNOSIS_COMPLETE_NO_REPAIR', measured_date='2026-10-03',
        baseline_evidence='results/setup_margin/summary.json', current_rtl_sha256=previous['current_rtl_sha256'],
        library_sha256=previous['library_sha256'], library_metadata_sha256=sha(out/'library_metadata.json'),
        script_sha256=provenance['script_sha256'], publisher_sha256=sha(Path(__file__)),
        zero_limit_library_outputs=sorted(k for k, v in library['outputs'].items() if v['max_capacitance_pf'] == 0),
        runs=runs, load_accounting_tolerance_pf=NET_TOL, constraint_rounding_tolerance_pf=CONSTRAINT_TOL,
        finding='Explicit source-library zero output limits match the loaded DB and constraint reports; '
                'every violation has positive cell-input capacitance and zero modeled wire capacitance. '
                'All affected loads are below the supplied cell-delay load-table grid.',
        limits='Read-only diagnosis of two retained Q16 typical ideal-clock pre-layout mappings. '
               'No library correction, remapping, waiver, parasitic extraction, physical or multicorner signoff.')
    (out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    check_published(out, previous)
    print('Published capacitance diagnosis; retained setup/hold/area reproduced without edits.')


if __name__ == '__main__':
    main()
