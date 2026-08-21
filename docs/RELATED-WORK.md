# Related work — where LADDER sits, honestly

Survey date: 2026-08. This is the evidence behind the roadmap's
positioning claim and the papers' related-work sections. Corrections
welcome; every claim of novelty below should be read as "as far as this
survey found".

## The landscape

| system | year | what it does | how LADDER differs |
|---|---|---|---|
| **PLCverif** (CERN) | 2015– | Formal verification of existing PLC programs: parses Siemens SCL/FBD, builds scan-accurate models, checks via nuXmv/CBMC/Theta; production use incl. the SPS Personnel Safety System | verifies code after the fact; LADDER generates the code *and* its theorems from one IR |
| **PLCspecif** (CERN, Darvas et al.) | 2015–17 | Formal spec language generating Siemens ST *and* supporting verification — **the closest prior art in spirit** | Siemens-only, research prototype, no vendor-neutral IR, no simulator/scenarios/CI project model, properties not auto-derived per element |
| **UNICOS-CPC** (CERN) | 2011– | Object taxonomy + generator: device specs → Siemens/Schneider ST + SCADA | continuous process control via object instantiation; no general logic IR, no formal verification |
| **PLC Factory / PLC Integrator** (ESS) | 2017/2025 | device DB + DSL → Siemens SCL + EPICS records | interface/glue generation, not semantic logic; no verification |
| **PyPLC / EPS tools** (ALBA) | 2015 | equipment DB + templates → protection PLC code | template instantiation, no formal semantics |
| **LLM4PLC / Agents4PLC / AutoPLC** | 2024–26 | LLM pipelines generating ST with compiler/model-checker feedback | they generate free-form vendor code autonomously; LADDER's LLM drives a *human-overseen* loop and only ever writes schema-validated YAML, judged by deterministic gates and human sign-off |
| **Arcade.PLC**, **ESBMC-PLC(+)** | 2012, 2026 | model checking / BMC of existing PLC code (ESBMC-PLC+ takes properties as YAML) | verification-only; the YAML-property idea independently corroborates LADDER's declarative properties file |
| **G4LTL-ST** | 2014 | reactive synthesis: LTL → ST | expert-hostile input, scalability limits; LADDER has humans author structured logic and derives the theorems |
| **FRET → PLCverif** (NASA/CERN) | 2023 | controlled-English requirements → temporal logic → PLCverif | requirements front-end for verification; a model for rendering LADDER's theorems back into reviewable English |
| **matiec/Beremiz, OpenPLC, IronPLC** | 2007– | open IEC compilers/IDEs/runtimes | infrastructure LADDER *uses* (matiec is a CI gate), not competitors |
| **TcUnit** | 2018– | xUnit testing for TwinCAT ST | tests hand-written code on the runtime; complements the IR-level scenario simulator |
| **SIMATIC AX**, **Rockwell Logix CI/CD (AT002, SDK, Echo)**, **Zeugwerk**, **Copia** | 2020– | vendor "PLC-as-code": git, CI, headless builds, emulators, graphical diffs | single-vendor workflow plumbing for hand-written projects; proves the workflow LADDER assumes is now industry-endorsed |
| **Eclipse 4diac** | 2007– | IEC 61499 distributed-control MDE | different standard and execution model (event-driven 61499) |
| **pytmc / blark** (SLAC) | 2019– | TwinCAT code → EPICS interface generation; ST parsing | opposite direction (from PLC code out); signals demand for IR→EPICS artifacts |

## Gap analysis (what to claim, what not to)

**Already standard practice — never claim novelty for:** config/DB →
PLC-code generation at labs (UNICOS, ESS, ALBA — 15+ years of ICALEPCS
papers); nuXmv-based scan-accurate PLC verification (PLCverif, in
production on a personnel safety system); git+CI PLC workflows (vendor-
endorsed); LLM→verified-ST loops (LLM4PLC and successors).

**The combination that appears unoccupied:**

1. a **vendor-neutral, schema-validated semantic IR** for
   interlock/alarm/sequence logic with **deterministic lowering to five
   backends** including two real vendor toolchains driven headlessly;
2. **auto-generated safety theorems per element type** — interlock,
   dual_channel, search_chain, alarm_group each ship proof obligations
   by construction (every prior system requires hand-written properties);
3. one artifact driving **lint + scan-accurate simulation with
   declarative acceptance scenarios + formal proof + codegen + generated
   documentation package** in a self-contained git/CI project;
4. **the human-oversight inversion of LLM-first codegen**: the LLM
   drives the authoring loop but emits only constrained YAML, every
   draft judged by the same deterministic gates as a human edit and
   landed only on human sign-off — while the pipeline itself stays
   fully operable with no model at all.

**Convergence risk to watch:** ESBMC-PLC+ from the verification side,
SIMATIC AX / Rockwell DevOps from the workflow side. The defensible core
is the IR-with-domain-semantics and theorem auto-generation.

## Best practices adopted / to adopt

| practice | source | status |
|---|---|---|
| xUnit/JUnit XML from scenario runs so CI renders pass/fail natively | TcUnit | **adopted** (`ladder check --junit`) |
| requirement patterns: fill-in-the-blank English → fixed temporal templates | PLCverif | roadmap (extend the properties file with pattern kinds) |
| model reductions (cone of influence) for big SMV models | PLCverif | roadmap (IC3 covers current scale) |
| counterexample → replayable failing scenario in our own simulator | PLCverif (improved) | roadmap |
| render each auto-theorem as controlled English in the doc package | FRET | roadmap (verification report) |
| semantic `ladder diff` ("interlock X gained input Y") for reviews | Copia's lesson | roadmap |
| mutation testing of the IR to score scenario/theorem strength | STMutants | roadmap (paper evaluation) |
| emulator-in-the-loop stage after artifact build (PLCSIM Adv. / Logix Echo) | Rockwell AT002 | roadmap |
| emit EPICS/OPC UA interface artifacts from the same IR | pytmc/ESS | roadmap (labs will ask immediately) |
| structured models over string templates (ESS rebuilt to learn this) | PLC Integrator | already LADDER's core design |

## Citable references

See the papers' `.bib`/reference lists (papers/ in this repo); the
primary set: Darvas et al. ICALEPCS'15 (PLCverif), Fernández Adiego et
al. ICALEPCS'19/'21, Darvas et al. INDIN'16 (PLCspecif), Blanco Viñuela
et al. ICALEPCS'11 (UNICOS-CPC), Ulm et al. ICALEPCS'17 (PLC Factory),
Rubio-Manrique et al. ICALEPCS'15 (PyPLC), Fakih et al. ICSE-SEIP'24
(LLM4PLC), Liu et al. 2024 (Agents4PLC), Biallas et al. ASE'12
(Arcade.PLC), Cheng et al. CAV'14 (G4LTL-ST), Katis et al. NFM'23
(FRET+PLCverif), plus tool references (matiec/Beremiz, OpenPLC, TcUnit,
Rockwell AT002, ESBMC-PLC+).
