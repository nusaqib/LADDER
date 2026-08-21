# Papers

Conference papers about LADDER, in JACoW format (the common template
for accelerator conferences: IPAC, ICALEPCS, PCaPAC, ...).

| paper | about |
|---|---|
| [jacow/LADDER-paper.tex](jacow/LADDER-paper.tex) | the toolkit: IR, deterministic lowering, five backends, auto-generated safety theorems, the human-gated LLM authoring loop |

A companion paper on the PPS reconstruction case study lives in the
private SR-PPS repository (`papers/jacow/`).

## Building

`jacow.cls` v3.01 (2026-03-11, the current official class from
[JACoW-org/JACoW_Templates](https://github.com/JACoW-org/JACoW_Templates))
is vendored beside the source. Compile with any TeX distribution:

```bash
cd jacow && pdflatex LADDER-paper.tex && pdflatex LADDER-paper.tex
```

or upload the two files to Overleaf. Switch the class option
`letterpaper`/`a4paper` to match the host conference.

## Before submitting

- [ ] Fix the author line (full name/initials per JACoW style) and add
      co-authors.
- [ ] Confirm the funding footnote wording per LBNL publication guidance.
- [ ] LBNL/DOE publication release approval.
- [ ] Register the abstract with the conference SPMS and use the
      assigned program code as the filename.
