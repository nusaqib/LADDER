# Security Policy

## Reporting

Report suspected vulnerabilities privately via GitHub security advisories
on this repository (or to the repository owner) rather than a public
issue. You should receive an acknowledgment within a week.

## Scope and threat model

LADDER is an **engineering-time** tool: it generates and verifies PLC
project artifacts on an engineering workstation. It does not talk to
controllers, does not deploy to plants, and must never be wired to do so
unattended. Relevant classes of issues:

- Artifact injection: crafted IR/YAML, IO maps, scenario files, or
  adopted vendor exports causing the toolchain to emit content the
  design did not specify, or to execute code (YAML is loaded with
  `yaml.safe_load` everywhere — deviations from that are bugs).
- Path traversal in generated outputs or spec adoption.
- Backend plugins: third-party entry-point backends execute at import;
  install plugins you trust, as with any Python package.

## Non-goals

Generated programs are reviewed engineering artifacts, not a security
boundary; plant-side security (controller hardening, network
segmentation, safety access protection) belongs to the facility. Never
commit vendor binaries or facility-specific safety programs to this
repository — see CONTRIBUTING.md.
