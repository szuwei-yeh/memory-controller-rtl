# Baseline report-only diagnostics

All 14 hold-violating endpoints have register-to-register paths. Counts: input-to-register **0**, register-to-register **14**, register-to-output **0**, other **0**. These are the worst reported paths per violating endpoint, not an enumeration of every possible combinational route.

| Startpoint | Endpoint | Class | Worst slack (ns) |
|---|---|---|---:|
| `table_i/done_reg_4_` | `table_i/done_reg_4_` | register-to-register | -0.002538 |
| `table_i/done_reg_0_` | `table_i/done_reg_0_` | register-to-register | -0.002538 |
| `table_i/done_reg_5_` | `table_i/done_reg_5_` | register-to-register | -0.002538 |
| `table_i/done_reg_6_` | `table_i/done_reg_6_` | register-to-register | -0.002538 |
| `table_i/done_reg_14_` | `table_i/done_reg_14_` | register-to-register | -0.000714 |
| `table_i/done_reg_15_` | `table_i/done_reg_15_` | register-to-register | -0.000714 |
| `table_i/done_reg_8_` | `table_i/done_reg_8_` | register-to-register | -0.000714 |
| `table_i/done_reg_10_` | `table_i/done_reg_10_` | register-to-register | -0.000714 |
| `table_i/done_reg_11_` | `table_i/done_reg_11_` | register-to-register | -0.000714 |
| `table_i/done_reg_12_` | `table_i/done_reg_12_` | register-to-register | -0.000714 |
| `table_i/done_reg_13_` | `table_i/done_reg_13_` | register-to-register | -0.000714 |
| `banks_i/ras_reg_1__2_` | `banks_i/ras_reg_1__2_` | register-to-register | -0.000659 |
| `table_i/done_reg_9_` | `table_i/done_reg_9_` | register-to-register | -0.000608 |
| `banks_i/rcd_reg_1__1_` | `banks_i/rcd_reg_1__1_` | register-to-register | -0.000467 |

Source: [baseline hold report](../results/dc_baseline/hold.rpt), reopened from the accepted mapped DDC without compile. Names are Verilog-normalized. Clock uncertainty remains 0.1 ns for both setup and hold; no constraints were relaxed.

All **5,556** max-capacitance violations report a zero allowed load. `candidates_i/n2557` is driven by `NAND2X1 U1845` and has 0.003852 pF load against 0 pF allowed. Both the loaded `gscl45nm.db` and its companion Liberty specify `NAND2X1/Y max_capacitance=0`; `INVX1/Y` instead has 0.238796 pF. See [precise violations](../results/dc_baseline/constraints_precise.rpt) and [library query](../results/dc_baseline/library_cap_limits.txt). These inherited limits are retained, not waived or corrected.

The database SHA-256 was rechecked before the sweep: `4968d1dba7ff9911cc51dfac7d8ea8b94fbab59d2f862f0531d7c774fb0a5791`. No RTL, library, or SDC edits are part of these diagnostics.
