# v1.1 publication privacy audit

The initial publication includes controller RTL, verification sources, reproducible
workloads, synthesis scripts/SDC, documentation, and intentionally curated result
reports and plots. It excludes the private engineering notebook, build trees,
raw temporary logs, waveforms, tool installations, local lab configuration,
credentials, and licensed technology databases. No technology library is distributed.

## Redaction scope

Private account names, SSH destinations, machine names, temporary workspace
identifiers, installation/library directory paths, and the license-server address
were removed from public documentation and report provenance. Library basenames,
corner, tool versions, source hashes, numeric measurements, and limitations remain.
`${TECH_LIBRARY_DIR}` and similar values in report text are redaction placeholders,
not literal usable installation paths. The Tcl setup example shows environment
expansion; authorized users must supply their own site configuration privately.

The remote sweep helper now reads `LAB_SSH_TARGET`, `LAB_BASELINE_DIR`, and optional
`LAB_SSH_CONTROL_PATH` instead of embedding an account or infrastructure details.
It exits before connecting if required values are absent. No synthesis settings,
constraints, controller behavior, or measurements changed.

[Redaction provenance](publication-redactions.json) records original and public
SHA-256 hashes for sanitized report files. Earlier `verification.json` and
`report_sha256` values intentionally describe the original measured artifacts;
they are historical provenance, not assertions about redacted byte streams.
The M8 byte-for-byte reproduction occurred before these publication redactions.
Raw report regeneration can reintroduce site metadata: repeat the publication
privacy audit before publishing regenerated reports or creating a release bundle.
The old local M8/lab bundles predate redaction and must not be uploaded.

## Audit checks

- Controller RTL, testbench, formal harnesses, architecture/protocol, and SDC
  remain byte-identical to the accepted freeze.
- Numeric JSON values and report measurements remain unchanged; result edits are
  limited to private provenance strings.
- The public inventory is scanned for private identifiers, credential/token/key
  signatures, machine-specific paths, forbidden artifacts, and oversized files.
  Generic interpreter paths, placeholder paths, RTL hierarchical pin names,
  and public tool documentation URLs are intentional.
- PNG/PDF figures are intentional public artifacts; no binaries, technology
  databases, waveforms, temporary logs, or build caches are included.
- `local_notes/` is ignored and untracked. Mentions of its exclusion in project
  instructions are intentional; notebook contents are never published.
- Relative README/documentation links resolve within the intended public tree.
- The release author uses the configured GitHub noreply address. Commit identity
  is intentional public attribution, not a lab login or private credential.

No GitHub upload is permitted before authentication and the final staged-tree
checks pass. Remote visibility, branch/tag identity, and the published tree are
verified after a successful push; local checks alone do not establish publication.
