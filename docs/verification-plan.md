# Verification strategy

The controller and testbench are independently implemented. The DRAM model uses
event timestamps; controller legality uses saturating countdowns. The scoreboard
uses acceptance sequence numbers and host-visible requests, not the DUT's timing
or candidate masks. It uses the DUT-selected slot only to identify the command's
request tag, then checks that tag, address, operation, and write data against its
independently reconstructed choice.

The acceptance-order memory model computes expected reads by tag. This is valid
because same-address memory operations preserve order and different addresses are
independent. A separate oldest-outstanding-per-address check enforces response order.

## Tests

`make test` runs all policies over ten workload classes plus reset, then parameter
corners: Q=1/minimal dimensions/timings, Q=3/long READ latency/tCCD=1, and long
bank timing with short aging thresholds. Each run includes directed same-address
RAW/WAR/WAW/RAR, row conflicts, independent banks, and a 150-cycle response stall.
The driver can offer one request per cycle and holds payloads while admission stalls.

`tb_response` preloads eight independent completed entries and requires eight
consecutive-cycle handshakes. It also stalls a held response while an older
independent entry completes, checks oldest eligible replacement and same-address
ordering after release, verifies the preserved bubble for an isolated same-address
successor, checks no duplicate final retirement, and resets a held response. The
consecutive-handshake check fails against the original response RTL.

`scripts/response_capacity.py --label after` measures row-hit traffic with tCCD=1
and tCCD=2, 64 columns, 200 warm-up and 5,000 measured requests. It reports both
cohort throughput (including drain) and first-to-last response rate, plus the
longest run of consecutive handshakes. The default tCCD=2 experiment must not be
mistaken for a measurement of the response arbiter's maximum capacity.

`tb_model` checks two legal traces covering exact boundaries and eight separately failing illegal
traces: tRCD, tRP, tRAS, tCCD, tWR, wrong row, ACT to an open bank, PRE to a closed
bank. The runner requires the intended error message and a failing exit code;
an unrelated crash is not a passing negative test.

`tb_scheduler` directly constructs an aged target behind a younger existing owner,
then checks owner drain, suppression of unrelated columns, other-bank ACT permission,
protected PRE/ACT/WRITE priority and protection release. This is a defensive-state
test: v1's oldest-bank preparation rule normally prevents a younger bank owner
from existing ahead of an older pending request in that bank. Its absence from
random top-level coverage is therefore not silently counted as covered.

`make regress` runs 100 seeds per policy, 10,000 workload requests per seed, plus
the directed prelude. Workload selection rotates over ten classes. Response-ready
patterns exercise 100%, 80%, and 30% duty cycles. The per-request RNG depends only
on sequence index, not execution timing, preserving identical workloads across policies.

Every accepted request is accounted for, and measured traffic drains completely.
Assertions check slot capacity, stable stalled responses, memory/response order,
fixed return latency, exact scheduler choice, write payload, data values, preparation
ownership via candidate legality, and finite command service with aging.

Coverage counters include same-address response blocking, independent-address bypass,
read-return/write-completion overlap, full table, bank preparation overlap, protection
activation, and max queue wait. Aggregate these over the suite; do not demand every
event in Strict-FCFS or Q=1, where some events are structurally impossible.

## Formal

`make formal-scheduler` additionally compares the current scheduler with the frozen
v1.1 reference using Yosys SAT and matched internal signals at Q=1/3/16/32, aging
off/on, and default address/age parameters. Every equivalence cell must be proved.
Both implementations have the same synchronous reset and state-update structure.
The immutable reference is hash-checked and excluded from synthesis manifests.

`formal/scheduler_equiv.sby` separately proves post-reset output equivalence at
Q=1/3/16 with aging off/on, four-bit addresses and age limit three. Slot indices
are constrained to be in range. Ordering matrices, candidate uniqueness, bank
matching, and legal/pending relationships are otherwise unconstrained. Selection
outputs and protection-valid match; protection-slot is compared when protection
is active. Non-power-of-two configurations use SMT/Z3 to retain undefined-access
semantics; Q=16 uses ABC PDR. These checks concern scheduler equivalence, not a
new proof of full-controller data correctness.

`make compare-scheduler` compares complete event CSVs from the old and new
controllers: three policies, ten workloads, seeds 1/42 and ready 100%/30%, with
500 workload requests plus the directed prelude per run. Any cycle-level event
difference fails. It does not regenerate the historical performance results.

SymbiYosys configuration and harnesses are in formal/. The integrated harness uses
two slots, four banks, two rows/two columns, 8-bit words and a small timing profile.
Host requests, data, addresses, tags, and response readiness are nondeterministic.
Assumptions require valid/payload stability under request backpressure and unique
outstanding tags. Reset is initial only. A fixed-latency memory model and an
acceptance-order reference memory check returned values and response ordering.

Record proof mode, depth, task, solver/engine, assumptions, and outcome. A BMC PASS
is bounded evidence, not an unbounded proof. Timeouts and unavailable tools remain
explicit limitations. Full-depth simulation validates service budgets for larger
configurations independently of formal outcome.

The integrated tasks use ABC BMC at depth 12. Two additional ABC PDR tasks prove
bank timing permissions against elapsed-cycle reference counters, and the 63-cycle
pending-service budget for a reduced two-slot mixed read/write controller. The
progress harness uses zero-valued data and one-cycle reads, retaining symbolic
addresses, operations, tags, and arbitrary response backpressure. Those are focused
unbounded control proofs, not a proof of the full-width memory data path or every
parameter configuration.

## Testbench limitations

Testbench tag allocation uses Q_DEPTH+1 distinct tags to reduce reference-model
search cost while allowing full occupancy and repeated tag reuse. The controller
still supports the configured TAG_W interface. Performance uses 32-bit words;
additional RTL widths can be linted/synthesized independently. Reset cancellation
tests synchronize the reference memory to the model's committed state after reset;
normal data tests do not inspect the model's storage.
