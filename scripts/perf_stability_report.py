#!/usr/bin/env python3
"""Validate and publish the fixed multi-seed study, without reading private notes."""
import csv
import hashlib
import json
from pathlib import Path
from log_experiment import append_entry

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/perf_stability'


def main():
    study = json.loads((OUT/'summary.json').read_text())
    frozen = json.loads((OUT/'frozen_sources.json').read_text())
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest() == h for p,h in frozen.items())
    rows = study['per_seed']
    assert len(rows) == 600 and len({(r['revision'],r['policy'],r['workload'],r['ready_percent'],r['seed']) for r in rows}) == 600
    assert all(r['accepted'] == 2210 and r['measured'] == 2000 for r in rows)
    previous = {
        'v1.0': json.loads((ROOT/'results/response_refill_before.json').read_text())['performance']['results'],
        'v1.1': json.loads((ROOT/'results/local_summary.json').read_text())['performance']}
    for r in rows:
        if r['seed'] == 42 and r['workload'] == 'random' and r['ready_percent'] == 50:
            old = next(x for x in previous[r['revision']] if x['policy_name'] == r['policy'] and
                       x['workload'] == 'random' and x['ready_percent'] == 50)
            m = old['metrics']; lat = m['latency']['end_to_end']
            assert r['responses_per_cycle'] == m['responses_per_cycle']
            assert all(r[k] == lat[v] for k,v in [('mean_latency','mean'),('p95','p95'),('p99','p99'),('maximum_latency','max')])
    # Acceptance order/address/operation sequence is identical for every paired trial.
    for old in [r for r in rows if r['revision'] == 'v1.0']:
        new = next(r for r in rows if r['revision'] == 'v1.1' and
                   all(r[k] == old[k] for k in ['policy','workload','ready_percent','seed']))
        def stimulus(r):
            with (ROOT/r['path']/'events.csv').open() as f:
                return [tuple(row[2:]) for row in csv.reader(f) if row[0] == 'A']
        assert stimulus(old) == stimulus(new)
    groups = study['distributions']
    assert all(g['metrics'][m]['stdev'] == 0 for g in groups if g['workload'] != 'random' for m in g['metrics'])
    verification = dict(status='PASS', frozen_sources_unchanged=True, final_runs=540, historical_runs=60,
        accepted=study['accepted_total'], measured=1200000, paired_address_operation_sequences_identical=60,
        prior_seed42_metric_sets_reproduced=6, deterministic_hot_cold_hol_confirmed=True)
    (OUT/'verification.json').write_text(json.dumps(verification, indent=2)+'\n')
    with (OUT/'distributions.csv').open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['policy','workload','ready_percent','metric','mean','stdev','median','minimum','maximum'])
        for g in groups:
            for metric, d in g['metrics'].items():
                writer.writerow([g['policy'],g['workload'],g['ready_percent'],metric,*[d[k] for k in ['mean','stdev','median','minimum','maximum']]])
    lines = ['# Frozen v1.1 performance stability study', '',
        'The controller RTL and testbench are unchanged. All **540 final-design runs** and',
        '**60 historical paired runs** passed their existing self-checks and drained completely:',
        '1,326,000 accepted transactions, including 1,200,000 measured transactions.', '',
        '## Experiment design', '',
        '- Seeds: **1–19 and 42**, fixed before running; 20 seeds per condition.',
        '- Final design: random, hot_cold, hol × ready 100%, 50%, 20% × strict_fcfs, frfcfs, frfcfs_aging.',
        '- Historical comparison: random/50% for every policy and the same 20 seeds.',
        '- Per run: fixed ten-request directed prelude, 200 workload warm-up requests, 2,000 measured requests, complete drain.',
        '- Four banks, simulation ROWS=8 and COLS=8, 32-bit data, Q=16, read latency 3, tRCD/tRP/tRAS/tCCD/tWR=3/3/6/2/3, aging threshold 128.',
        '- Offered interval one cycle, offered load 100%, 25% writes. Ready is asserted when cycle modulo 100 is below the requested percentage; final drain forces ready high.',
        '- Latency is acceptance to response consumption, in cycles. Throughput is measured responses divided by the inclusive interval from first measured acceptance to last measured response.',
        '- Per-run p95/p99 use sorted samples at floor(q × (n−1)), matching prior results. Cross-seed summaries treat each run equally; percentiles are not pooled.', '',
        'The historical controller is reconstructed under ignored `build/` using the reverse',
        'of `results/response_refill.patch`; all seven historical RTL hashes are checked.',
        'All 60 paired acceptance address/operation sequences match, and seed 42 reproduces',
        'all five earlier metrics exactly for both revisions and all three policies.', '',
        '## Random traffic at 50% ready: paired old → v1.1', '',
        'Values below are averages of the 20 per-seed metrics. Δ is v1.1 minus old.', '',
        '| Policy | Responses/cycle | Mean latency | p95 | p99 | Maximum |',
        '|---|---:|---:|---:|---:|---:|']
    for p in study['paired_random_ready50']:
        cells = [p['policy']]
        for m in ['responses_per_cycle','mean_latency','p95','p99','maximum_latency']:
            fmt = '.4f' if m == 'responses_per_cycle' else '.2f'
            cells.append(f"{p['before'][m]['mean']:{fmt}} → {p['after'][m]['mean']:{fmt}}")
        lines.append('| '+' | '.join(cells)+' |')
    lines += ['', '| Policy | Mean p99 Δ | Median Δ | Δ range | Higher / equal / lower | 95% bootstrap interval for mean Δ | Sign-test p |',
              '|---|---:|---:|---:|---:|---:|---:|']
    for p in study['paired_random_ready50']:
        d = p['delta']['p99']; lo,hi = d['bootstrap_mean_95_ci']
        lines.append(f"| {p['policy']} | {d['mean']:.2f} | {d['median']:.2f} | {d['minimum']:.0f}–{d['maximum']:.0f} | {d['positive']} / {d['zero']} / {d['negative']} | [{lo:.2f}, {hi:.2f}] | {d['two_sided_sign_test_p']:.6g} |")
    lines += ['', 'Intervals use 10,000 paired-seed bootstrap resamples with fixed analysis RNG seed',
              '20260922. The two-sided sign test excludes ties. These are descriptive intervals',
              'for this seed set and generator, without adjustment for multiple comparisons.', '',
              '## Final v1.1 distributions', '',
              'Each cell is **cross-seed mean [minimum, maximum]**. Full sample standard',
              'deviation and median for every metric are in the linked distribution CSV.', '',
              '| Workload | Ready | Policy | Responses/cycle | Mean latency | p95 | p99 | Maximum |',
              '|---|---:|---|---:|---:|---:|---:|---:|']
    for g in sorted(groups, key=lambda g: (g['workload'], -g['ready_percent'], g['policy'])):
        cells = [g['workload'],str(g['ready_percent'])+'%',g['policy']]
        for m in ['responses_per_cycle','mean_latency','p95','p99','maximum_latency']:
            d = g['metrics'][m]; fmt = '.4f' if m == 'responses_per_cycle' else '.2f'
            cells.append(f"{d['mean']:{fmt}} [{d['minimum']:{fmt}}, {d['maximum']:{fmt}}]")
        lines.append('| '+' | '.join(cells)+' |')
    lines += ['', '## Interpretation and limits', '',
        '<!-- INTERPRETATION -->', '',
        '**Hot/cold and HOL are deterministic timing experiments.** Their seeds change',
        'write data, but not addresses or read/write operations. All five metrics have',
        'zero cross-seed variation in every such condition. Twenty passing payload seeds',
        'do not establish robustness across twenty different locality or arrival patterns.', '',
        'Random traffic does vary addresses. Paired seed comparisons isolate the response',
        'implementation under the same offered transaction sequence. Different response',
        'timing changes slot availability and the requests visible to the scheduler;',
        'higher throughput and lower mean latency do not imply a lower p99.', '',
        'These runs characterize saturated small-memory simulation with periodic stalls,',
        'not arbitrary traffic or Bernoulli readiness. Each p99 has only about 20 samples',
        'above it; longer runs could further characterize tails. Forced-ready final drain',
        'is retained for exact comparability and means throughput is a finite-cohort metric.',
        'The study supports conclusions within this configuration, not a universal latency guarantee.', '',
        'No RTL, testbench, architecture, scheduler, constraints, or synthesis settings were',
        'changed. This task ran performance self-checks, not a new regression, formal,',
        'or synthesis campaign; earlier correctness evidence remains associated with the same RTL.', '',
        '## Reproduce and inspect', '', '```sh', 'python3 scripts/perf_stability.py',
        'python3 scripts/perf_stability_report.py', '```', '',
        '- [All 600 per-seed records](../results/perf_stability/per_seed.csv)',
        '- [All cross-seed distributions](../results/perf_stability/distributions.csv)',
        '- [Summary, paired deltas, configuration and build hashes](../results/perf_stability/summary.json)',
        '- [Frozen source hashes](../results/perf_stability/frozen_sources.json)',
        '- [Verification accounting](../results/perf_stability/verification.json)', '',
        'Raw simulation commands, logs and timestamp traces stay under ignored',
        '`build/runs/stability_*`; build commands are in `build/perf_stability/commands.json`.',
        'The private notebook is append-only and excluded from Git and export artifacts.', '']
    # Preserve the reviewed interpretation on regeneration.
    report_path = ROOT/'docs/performance-stability.md'
    interpretation_path = OUT/'interpretation.txt'
    if interpretation_path.exists():
        lines = [interpretation_path.read_text().strip() if line == '<!-- INTERPRETATION -->' else line for line in lines]
    report_path.write_text('\n'.join(lines))
    append_entry('v1.1 穩定性研究：交叉檢查與公開資料整理',
        '確認配對公平性、舊結果重現及凍結完整性。',
        '60 組配對地址與操作序列相同；6 組種子 42 新舊結果五項指標完全重現；600 次量測皆完整。',
        'scripts/perf_stability_report.py；docs/performance-stability.md；results/perf_stability/distributions.csv、verification.json。',
        'python3 scripts/perf_stability_report.py；git check-ignore local_notes/實驗日誌.md；git ls-files local_notes。',
        '全部檢查通過；RTL 與測試平台雜湊不變；私人筆記已忽略且未被追蹤。',
        'hot_cold 與 hol 的所有跨種子標準差為零，反映固定刺激而非普遍穩定性保證。',
        '公開報告讀取明確列出的實驗產物，絕不讀取或匯出私人筆記。',
        '補充最終解讀並回報，維持 RTL 凍結。')
    print(json.dumps(verification, indent=2))


if __name__ == '__main__':
    main()
