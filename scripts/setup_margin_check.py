#!/usr/bin/env python3
"""Prove all mapped next-state/clock/output functions with ABC CEC."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time

from hold_repair_check import sha


def register_paths(path, top):
    modules = {}
    for module, body in re.findall(r'\bmodule\s+(\S+)\s*(.*?endmodule)', path.read_text(), re.S):
        modules[module] = re.findall(r'\b(\w+)\s+([\w$]+)\s*\(.*?\);', body, re.S)
    result = []
    def visit(module, prefix):
        for ref, instance in modules[module]:
            name = prefix+instance
            if ref == 'DFFPOSX1':
                result.append(name)
            elif ref in modules:
                visit(ref, name+'.')
            elif ref.startswith(('DFF', 'LATCH')):
                raise RuntimeError('Unsupported sequential cell reference: '+ref)
    visit(top, '')
    if not result or len(set(result)) != len(result):
        raise RuntimeError('Missing or duplicated register identities')
    return sorted(result)


def run_yosys(commands, out, name):
    script, log = out/f'{name}.ys', out/f'{name}.log'
    script.write_text('\n'.join(commands)+'\n')
    with log.open('w') as stream:
        subprocess.run(['yosys', '-Q', '-T', '-s', str(script.resolve())], cwd=out,
                       stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=120)


def combinational_model(netlist, liberty, top, registers, out, label):
    flat = out/f'{label}_flat.json'
    run_yosys(['read_liberty '+json.dumps(str(liberty)),
               'read_verilog '+json.dumps(str(netlist)), f'hierarchy -check -top {top}',
               'proc', 'flatten', 'opt_expr', 'opt_clean', 'write_json '+json.dumps(str(flat))],
              out, label+'_prepare')
    data = json.loads(flat.read_text())
    module = data['modules'][top]
    names = module['netnames']
    ports = {name: (port['direction'], len(port['bits'])) for name, port in module['ports'].items()}
    qbits = [names[name+'.Q']['bits'][0] for name in registers]
    assert len(set(qbits)) == len(registers) and all(isinstance(bit, int) for bit in qbits)
    flops = {name: cell for name, cell in module['cells'].items() if cell['type'] == '$_DFF_P_'}
    assert len(flops) == len(registers), 'Every physical register must have one modeled flip-flop'
    by_q = {cell['connections']['Q'][0]: cell for cell in flops.values()}
    assert set(by_q) == set(qbits)
    for register, qbit in zip(registers, qbits):
        assert by_q[qbit]['connections']['D'] == names[register+'.D']['bits']
        assert by_q[qbit]['connections']['C'] == names[register+'.CLK']['bits']
    for name in flops:
        del module['cells'][name]
    for index, register in enumerate(registers):
        for pin, direction, role in [('Q', 'input', 'state_q'), ('D', 'output', 'state_d'),
                                     ('CLK', 'output', 'state_clk')]:
            name = f'{role}_{index:04d}'
            assert name not in module['ports']
            module['ports'][name] = dict(direction=direction, bits=names[register+'.'+pin]['bits'])
    data['modules'] = {top: module}
    comb = out/f'{label}_comb.json'
    comb.write_text(json.dumps(data))
    # Relative AIG filenames avoid backend-specific quoting of option arguments.
    run_yosys(['read_json '+json.dumps(str(comb)), f'hierarchy -check -top {top}',
               'techmap', 'opt_expr', 'opt_clean', 'aigmap',
               f'write_aiger -symbols -map {label}.map {label}.aig'], out, label+'_export')
    header = (out/f'{label}.aig').read_bytes().split(b'\n', 1)[0].decode().split()
    assert header[0] == 'aig' and int(header[3]) == 0, 'CEC models must have no latches'
    return dict(original_ports=ports, input_bits=int(header[2]), output_bits=int(header[4]),
                latch_count=0, netlist_sha256=sha(netlist), aig_sha256=sha(out/f'{label}.aig'),
                port_map_sha256=sha(out/f'{label}.map'))


def cec(out, after, name, abc):
    assert (out/'before.map').read_bytes() == (out/f'{after}.map').read_bytes(), 'Port order/name mismatch'
    log = out/f'{name}.log'
    command = [abc, '-c', f'cec -T 300 -C 1000000 before.aig {after}.aig']
    start = time.monotonic()
    with log.open('w') as stream:
        result = subprocess.run(command, cwd=out, stdout=stream, stderr=subprocess.STDOUT, timeout=330)
    text = log.read_text()
    passed = result.returncode == 0 and re.search(
        r'^Networks are equivalent(?:\.| after structural hashing\.)', text, re.M) is not None
    rejected = result.returncode == 0 and 'Networks are NOT EQUIVALENT.' in text
    return dict(status='PASS' if passed else 'REJECTED' if rejected else 'INCOMPLETE',
                exit_code=result.returncode, elapsed_s=time.monotonic()-start, log_sha256=sha(log),
                command=command, port_maps_identical=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['before', 'after', 'liberty', 'out']:
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--top', required=True)
    parser.add_argument('--abc', default='yosys-abc')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', args.top):
        parser.error('Expected a plain Verilog top-module name')
    before, after, liberty = [path.resolve(strict=True) for path in [args.before, args.after, args.liberty]]
    registers = register_paths(before, args.top)
    if register_paths(after, args.top) != registers:
        raise RuntimeError('Before/after physical register identities differ')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = dict(status='INCOMPLETE', backend='ABC combinational equivalence (FRAIG + SAT)',
        yosys=subprocess.check_output(['yosys', '-V'], text=True).strip(),
        abc=subprocess.check_output([args.abc, '-c', 'version'], text=True).strip(),
        top=args.top, liberty_sha256=sha(liberty), checker_sha256=sha(Path(__file__)),
        shared_checker_sha256=sha(Path(__file__).with_name('hold_repair_check.py')), registers=registers,
        scope=f'All {len(registers)} physical DFFPOSX1 identities are matched. Each FF Q becomes a common '
              'symbolic state input; every FF D and CLK and every original output is compared. '
              'No combinational implementation names are assumed equal. Matching initial/reset '
              'state and identical positive-edge FF semantics establish corresponding state transitions. '
              'No retiming, added state, timing or physical equivalence claim.')
    try:
        report['models'] = {label: combinational_model(netlist, liberty, args.top, registers, out, label)
                            for label, netlist in [('before', before), ('after', after)]}
        assert report['models']['before']['original_ports'] == report['models']['after']['original_ports']
        report['equivalence'] = cec(out, 'after', 'equivalence', args.abc)
        if report['equivalence']['status'] != 'PASS':
            raise RuntimeError('Complete state/clock/output equivalence not proven')
        source = after.read_text()
        cell = re.search(r'\b(INVX\d+)\s+(\S+)\s*\(', source)
        if cell is None:
            raise RuntimeError('No inverter instance available for the negative control')
        mutant = out/'mutated.v'
        mutant.write_text(source[:cell.start()]+'BUFX2'+source[cell.start()+len(cell[1]):])
        assert register_paths(mutant, args.top) == registers
        report['models']['mutated'] = combinational_model(mutant, liberty, args.top, registers, out, 'mutated')
        control = cec(out, 'mutated', 'negative_control', args.abc)
        if control['status'] != 'REJECTED':
            raise RuntimeError('Negative control did not produce a genuine CEC counterexample')
        control['mutation'] = dict(instance=cell[2], original_cell=cell[1], mutated_cell='BUFX2')
        report['negative_control'] = control
        report['status'] = 'PASS'
    finally:
        (out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({key: value for key, value in report.items() if key not in ['registers', 'models']}, indent=2))


if __name__ == '__main__':
    main()
