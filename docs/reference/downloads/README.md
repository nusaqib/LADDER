# Downloaded vendor/tool documentation (git-ignored)

The real manuals and schemas, fetched for offline use next to our
working notes. **Only this README and `sources.yaml` are committed** —
the documents are vendor publications we may download freely but not
redistribute in a public repository. To (re)populate on any machine:

```bash
python tools/fetch_reference_docs.py        # --force to re-fetch
```

What lands here (see `sources.yaml` for exact sources):

```
rockwell/   1756-RM084 (THE L5X format manual), LOGIX-AT002 (CI/CD)
plcopen/    tc6_xml_v201.xsd (set TC6_XSD here for local schema tests)
nuxmv/      user manual (SMV language, BDD/IC3 commands)
siemens/    Openness V21 getting-started (SIOS), the hardware-parameters
            manual and the 21 SimaticML XSDs copied from the local
            Portal V21 install (PublicAPI/V21)
```

Reading order: our distilled notes in `docs/reference/**` first (they
carry the tested V19/V21 findings); drop to these primary documents for
exact attribute lists, schema details, and anything the notes don't
cover. Paywalled standards (IEC 61131-3/61508/61511, ISA-18.2) are
deliberately absent — the notes summarize them originally.
