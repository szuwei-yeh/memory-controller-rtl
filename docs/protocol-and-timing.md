# Protocol and timing contract

Single clock; active-high synchronous reset. Host request: valid/ready, write,
word address, full-word write data, tag. Response: valid/ready, write indication,
original tag, read data (zero on write acknowledgment). Payloads remain stable
while stalled. One handshake per rising edge; tags must be unique until response
consumption. Illegal parameters fail simulation elaboration. No address error
response exists because the address exactly spans the memory.

Memory outputs: `cmd_valid`, `cmd_op`, `cmd_bank`, `cmd_row`, `cmd_col`,
`cmd_wdata`. Command encoding is ACT=0, READ=1, WRITE=2, PRE=3. Row/column always
identify the selected request, including PRE. Write data is meaningful only for
WRITE. Outputs when cmd_valid=0 carry no command. There is no cmd_ready.
Memory returns `rd_valid`, `rd_data`; READ returns are in command order at fixed
READ_LATENCY. The controller's slot pipeline matches them without a memory tag.

## Edge convention

Commands sample on edge C. Required separation T permits the next command at
C+T. Example: ACT C10, tRCD=3; READ is forbidden at C11/C12 and legal at C13.

| Rule | Scope | Source -> destination |
|---|---|---|
| tRCD | Bank | ACT -> READ or WRITE |
| tRP | Bank | PRE -> ACT |
| tRAS | Bank | ACT -> PRE |
| tCCD | Channel | READ/WRITE -> any next READ/WRITE |
| tWR | Bank | WRITE -> PRE |

If ACT is C0 and WRITE is C3 with tRAS=6 and tWR=3, PRE is legal at C6.
With tRP=3, the next ACT is C9. With tRCD=3, its column command is C12.
With tCCD=2, READ to bank 0 at C13 permits a bank 1 WRITE at C15, not C14.

Timing values must be positive. Counter width supports T-1, including T=1.
Counter loads take precedence over decrements. A row's state changes at the
actual command edge, not selection in an earlier cycle.

## Data and ordering examples

WRITE commits with its command; acknowledgment can precede tWR expiry. READ
snapshots its value on its command edge and returns it at C+READ_LATENCY. A later
WRITE or PRE cannot change the pending return. There is no tRTP, tWTR, tRTW,
tRRD, tFAW, burst bus, or extra tRC constraint in this protocol.

Accepted W(A,7), R(A), W(A,9), R(B):

- A's commands must issue W(A,7), R(A), W(A,9).
- The read returns 7 even if W(A,9) commits before its data returns.
- A's responses must be consumed acknowledgment, read 7, acknowledgment.
- R(B) can issue/complete/respond anywhere allowed by its bank and shared timing.

Accepted R(A), W(A): the younger write can be DONE before the older read. Its
acknowledgment remains blocked until the read response is **consumed**, not just
ready or first presented. An independent completed B can bypass both if eligible.

Response selection chooses the oldest eligible DONE slot. Eligibility requires
no older occupied same-address slot, including a held response. A held response
does not change until handshake. On that handshake edge, the register may refill
from the oldest **other** pre-edge response-eligible slot, allowing consecutive
responses for independent addresses. The held slot is excluded from both the
replacement candidates and their oldest-first comparison, avoiding reselection
of the just-consumed transaction. Empty registers use the same arbitration.

Same-address eligibility is not computed using a speculative retirement: the held
predecessor remains occupied for this edge's eligibility check. Its successor may
be selected starting on the following edge. Thus an isolated same-address chain
retains its conservative bubble; an already-eligible independent response can fill
that interval. No transaction-table allocation bypass or global retirement buffer
is introduced. Slots and acceptance-order relationships survive through handshake.

## Reset

While reset is asserted, req_ready, rsp_valid, and cmd_valid are low. Reset cancels
all outstanding transactions and clears bank state, owners, counters, held response,
and pending read-return metadata. Model protocol state resets simultaneously;
memory contents are preserved. Tests initialize memory separately at startup.
No response is required for a canceled request. Reset is not a memory rollback:
already committed writes remain. A scoreboard must discard canceled expectations
and preserve/reconstruct only committed state for post-reset checking.
