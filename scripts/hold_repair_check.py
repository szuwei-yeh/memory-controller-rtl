#!/usr/bin/env python3
"""Prove paired mapped netlists with the lab's matching Liberty cell models."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def proof_script(before, after, liberty, top):
    commands = []
    for netlist, name in [(before, 'gold'), (after, 'gate')]:
        commands += [
            'read_liberty '+json.dumps(str(liberty)),
            'read_verilog '+json.dumps(str(netlist)),
            f'hierarchy -check -top {top}', f'prep -flatten -top {top}',
            'opt_clean', f'rename {top} {name}',
        ]
        if name == 'gold':
            commands.append('design -stash gold')
    commands += [
        'design -copy-from gold -as gold gold', 'equiv_make gold gate equiv',
        'hierarchy -check -top equiv', 'opt_merge', 'opt_clean',
        'equiv_simple -short', 'equiv_status -assert',
    ]
    return '\n'.join(commands)+'\n'


def run_check(before, after, liberty, top, out, name):
    script, log = out/f'{name}.ys', out/f'{name}.log'
    script.write_text(proof_script(before, after, liberty, top))
    start = time.monotonic()
    with log.open('w') as stream:
        result = subprocess.run(['yosys', '-Q', '-T', '-s', str(script)],
                                stdout=stream, stderr=subprocess.STDOUT, timeout=600)
    text = log.read_text()
    counts = re.search(r'Of those cells (\d+) are proven and (\d+) are unproven', text)
    passed = result.returncode == 0 and counts is not None and int(counts[2]) == 0
    return dict(status='PASS' if passed else 'FAIL', exit_code=result.returncode,
                proven_cells=int(counts[1]) if counts else None,
                unproven_cells=int(counts[2]) if counts else None,
                elapsed_s=time.monotonic()-start, log_sha256=sha(log),
                script_sha256=sha(script), before_sha256=sha(before), after_sha256=sha(after))


def mutate_buffer(before, after):
    """Invert one newly inserted hold buffer, preserving its input/output pins."""
    modules = lambda text: dict(re.findall(r'\bmodule\s+(\S+)\s*(.*?endmodule)', text, re.S))
    old = modules(before.read_text())
    source = after.read_text()
    for module, body in modules(source).items():
        for cell in re.finditer(r'\bBUFX2\s+(\S+)\s*\(', body):
            instance = cell[1]
            if re.search(r'\bBUFX2\s+'+re.escape(instance)+r'\s*\(', old.get(module, '')):
                continue
            changed = body[:cell.start()]+'INVX1'+body[cell.start()+len('BUFX2'):]
            assert source.count(body) == 1
            return source.replace(body, changed, 1), dict(module=module, instance=instance,
                original_cell='BUFX2', mutated_cell='INVX1')
    raise RuntimeError('No newly inserted BUFX2 found for the negative control')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--after', type=Path, required=True)
    parser.add_argument('--liberty', type=Path, required=True)
    parser.add_argument('--top', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--negative-control', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', args.top):
        parser.error('Expected a plain Verilog top-module name')
    before, after, liberty = [p.resolve(strict=True) for p in [args.before, args.after, args.liberty]]
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = dict(status='INCOMPLETE', tool=subprocess.check_output(['yosys', '-V'], text=True).strip(),
                  top=args.top, liberty_sha256=sha(liberty), checker_sha256=sha(Path(__file__)),
                  scope='Flattened mapped-netlist matched-node equivalence, including state and outputs; '
                        'all equivalence cells must be proven. Cell semantics come from the supplied '
                        'Liberty models. No timing or physical equivalence claim.')
    try:
        report['equivalence'] = run_check(before, after, liberty, args.top, out, 'equivalence')
        if report['equivalence']['status'] != 'PASS':
            raise RuntimeError('Mapped equivalence not proven; inspect equivalence.log')
        if args.negative_control:
            text, mutation = mutate_buffer(before, after)
            mutant = out/'mutated.v'
            mutant.write_text(text)
            control = run_check(before, mutant, liberty, args.top, out, 'negative_control')
            if control['exit_code'] == 0 or not control['unproven_cells']:
                raise RuntimeError('Negative control did not reach a genuine equivalence rejection')
            control.update(status='REJECTED', mutation=mutation)
            report['negative_control'] = control
        report['status'] = 'PASS'
    finally:
        (out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
