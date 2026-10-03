# Controller design review: a five-minute walkthrough

**Outcome:** a verified simplified DRAM controller with three scheduling policies
and a measured RTL optimization that removes 50 Q16/3 ns setup violations.
Follow-up mapped optimization eliminates hold failures and increases setup
margin to **50.054 ps at 3 ns / 55.773 ps at 4 ns**, with unchanged capacitance
violation counts. Its area cost is 0.77348% / 0.03285% versus hold-repaired
baselines. This remains a typical-corner
pre-layout study. Start with [reproduction](reproduce.md) to inspect or run it.

## 1. Architecture and the design decisions

```mermaid
flowchart LR
    H[Host request] --> T[Transaction table<br/>allocate through response consumption]
    T --> C[Dependency checks<br/>one candidate per bank]
    B[Four bank states<br/>timers and preparation owners] --> C
    C --> S[Selectable scheduler<br/>Strict-FCFS / FR-FCFS / aging]
    S --> I[Command issue<br/>ACT / READ / WRITE / PRE]
    I --> B
    I --> T
    I -.-> M[Behavioral DRAM<br/>simulation only]
    M -.-> D[Read return capture]
    D --> T
    T --> R[Response eligibility<br/>registered ready/valid output]
    R --> O[Host response]
    R -->|retire slot| T
```

The controller has one channel and four banks. A request holds its transaction
slot until the host consumes its response. Same-address operations and responses
preserve acceptance order; independent addresses can bypass. The older-than
matrix makes ordering explicit and avoids sequence-number wraparound, at the
cost of quadratic storage/logic as queue depth grows.

Strict-FCFS is an explicit head-of-line baseline: a blocked oldest request stalls
command issue. FR-FCFS prefers ready columns and then the oldest eligible request.
Aging protects an old request's command service, including draining a bank's
existing preparation owner. Host response consumption still requires readiness.
Bank timing legality and scheduling policy are separate concerns.

## 2. Diagnose a path, then change the dependency

The previous selected implementation (`9d40e16`) still failed 3 ns by 68.773 ps.
Its worst address-register-to-command path arrived at 1.968773 ns against a
1.900000 ns budget: 3 ns minus 1 ns output delay and 0.1 ns clock uncertainty.
Read-only DDC queries showed that candidates and arbitration consumed 70.72%
of that arrival time. Another nearly equal path used a different command mask,
so fixing one high-fanout mask alone would leave the other path failing.

```mermaid
flowchart TB
    subgraph Before[Before: class selection precedes arbitration]
        E[Eligible commands] --> C[Column-presence class selection]
        C --> W[Oldest-winner arbitration]
        W --> M[Winner mask and command payload]
    end
    subgraph After[After: arbitrate classes in parallel]
        EC[Eligible column commands] --> WC[Oldest column winners]
        EP[Eligible PRE / ACT commands] --> WP[Oldest preparation winners]
        WC --> CS[Select class using column presence]
        WP --> CS
        CS --> MO[Winner mask and command payload]
    end
```

This diagram describes the RTL dependency, not a measured gate-for-gate mapping.
The change adds no pipeline, state or cycle latency. It preserves highest-slot
tie priority, aging overrides and slot-zero payload when no command is valid.
Class selection must use **column presence**, not column-winner existence:
an arbitrary cyclic ordering matrix can have columns but no oldest winner.
A deliberately incorrect selector is rejected by equivalence.

## 3. Measure against the same baseline and constraints

| Q16 FR-FCFS+aging | Previous selected RTL | Parallel arbitration |
|---|---:|---:|
| 3 ns area (µm²) | 71,720.770984 | **70,362.616764 (−1.89%)** |
| 3 ns worst setup slack (ns) | −0.068773 | **+0.000038** |
| 3 ns setup endpoints / TNS (ns) | 50 / −3.396384 | **0 / 0** |
| 3 ns internal setup margin (ns) | +0.002394 | +0.000186 |
| 3 ns worst hold slack (ns) / endpoints | −0.000661 / 8 | −0.000659 / 8 |
| 4 ns area (µm²) | 65,996.718912 | **65,709.507315 (−0.44%)** |
| 4 ns worst setup slack (ns) | +0.000109 | **+0.001984** |
| 4 ns worst hold slack (ns) / endpoints | −0.000659 / 2 | −0.000659 / 2 |

Both targets use Synopsys DC R-2020.09-SP4, GSCL45nm typical at 1.1 V/27°C,
the same SDC and medium mapping effort, and 1,974 sequential cells. Two fresh
trial mappings are compared with two reused baseline mappings; each clock
target has its own netlist. Source/library/flow hashes and full violation lists
are retained. The smaller internal setup margin is a real tradeoff, even though
it satisfies the predeclared requirement of zero internal setup failures.

The subsequent [mapped hold repair](experiments/hold-repair-experiment.md)
inserts eight/two buffers at 3/4 ns, eliminating all eight/two hold failures.
Worst hold slack becomes +0.008031 ns at both points, while setup slack stays
unchanged. Area rises by 0.02668%/0.00714%. The paired mapped netlists pass
equivalence, and deliberately inverted hold buffers are rejected. The table
above retains the original RTL experiment's measurements before that repair.

The latest [setup-margin experiment](experiments/setup-margin-experiment.md)
then optimizes each hold-repaired mapping with a temporary 50 ps setup guard.
Existing zero-cap library cell instances are preserved and excluded from new
selection during incremental mapping; all temporary attributes and uncertainty
are restored before final measurement. Setup margin becomes 50.054 / 55.773 ps,
hold remains +8.031 ps, and the inherited 5,504 / 5,334 capacitance violations do
not increase. The area increases are 0.77348% / 0.03285% against those repaired
baselines. These area costs and earlier savings use separate paired baselines.

I also kept rejected experiments. The earlier direct-mask-only trial improved
worst setup but worsened TNS and hold count; a folded-default-mask trial worsened
hold. Fixed-slot storage alone failed its earlier screen, while a separately
measured combination later qualified. These are different baselines and trials;
their percentage improvements cannot be added together.

## 4. Establish what is correct, and what is still unproven

- **Implementation equivalence:** Q=1/3/16 across all three policies, nine
  whole-controller matched-node SAT checks, zero unproven cells; a wrong-class
  negative control is rejected. This is the documented partitioned proof scope.
- **Simulation:** 120 complete baseline/current event-trace pairs; 42 integrated
  workload/reset/parameter-corner cases and model/scheduler/response unit checks;
  300 regression runs with 3,003,000 accepted transactions.
- **Properties:** three depth-12 controller BMC tasks with symbolic data, plus
  reduced unbounded bank/progress control proofs. The reduced progress proof
  is not a general unbounded data-correctness or all-parameter proof.
- **Mapped repair:** before/after equivalence has zero unproven cells at both
  clock points, using associated GSCL45nm Liberty models; buffer-inversion
  negative controls are rejected. Exported timing constraints match.
- **Mapped setup margin:** all 1,974 register next-state/clock functions and
  94 original output bits pass ABC CEC at both points under common symbolic
  state/input; deliberately replacing an inverter with a buffer is rejected.
  Final exported constraints match the baselines.
- **Boundary:** latest 3 ns setup margin is 50.054 ps; zero-limit library
  capacitance violations remain. A [read-only diagnosis](experiments/capacitance-diagnosis.md)
  matches every violation to explicit source/DB zero limits and positive pin
  loads, and finds affected loads below the associated source's delay-table grid.
  These are supplied-library timing results. No placement/routing, power, PHY, refresh,
  JEDEC compliance, or production-frequency claim is made.

The next engineering phase would obtain validated library limits and low-load
characterization, then evaluate timing with a suitable physical flow across
corners and after placement/routing.

## Evidence to open during a review

- [Interface, timing and ordering contract](protocol-and-timing.md)
- [Pre-change critical-path diagnosis](experiments/command-path-3ns.md)
- [Final experiment, adoption criteria and limitations](experiments/parallel-arbitration-experiment.md)
- [Current machine-readable evidence](../results/parallel_arbitration/summary.json)
- [Mapped hold repair and proofs](experiments/hold-repair-experiment.md)
- [Latest setup-margin mapping and proofs](experiments/setup-margin-experiment.md)
- [Capacitance source, load accounting and characterization diagnosis](experiments/capacitance-diagnosis.md)
- [Verification scope](verification-plan.md) and [reproduction commands](reproduce.md)
- [Rejected direct-mask alternatives](experiments/command-mask-optimization.md) and
  [storage study](experiments/storage-timing-experiment.md)

An accurate resume description is: “Designed and verified a four-bank DRAM
command scheduler with FR-FCFS and aging; parallelized arbitration and optimized
mapped timing to achieve 50 ps setup margin with zero setup/hold violations at
a 3 ns typical-corner pre-layout target, supported by equivalence checks and
3.0M simulated transactions.”
Keep the simplified-protocol, typical-corner and pre-layout qualifications in
the project description and be ready to explain them.
