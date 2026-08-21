# Acceptance scenarios

Scenarios are declarative behavior tests executed by the LADDER simulator
(`ladder.sim`) — pure Python, no vendor tool. They are the acceptance gate
for `ladder generate`, the scoring mechanism for `benchmarks/`, and a good
way to pin the behavior of hand-written IR.

```yaml
scenarios:
  - name: jam_after_3s_no_motion        # required, unique
    description: optional prose
    steps:
      - set: {stop_ok: true, motion_ok: true}   # write global tags
      - scan: {}                                # one scan (10 ms default)
      - scan: {n: 5, dt_ms: 100}                # five 100 ms scans
      - pulse: start_pb                         # one scan TRUE, one FALSE
      - run: {ms: 3000, dt_ms: 100}             # advance simulated time
      - expect: {jam_alarm: true, conveyor_run: false}
```

Run with:

```bash
ladder test my_program.yaml scenarios.yaml
ladder generate spec.md --cmd "your-llm-cli" --accept scenarios.yaml
```

## Step reference

| Step | Argument | Meaning |
|---|---|---|
| `set` | `{tag: value, ...}` | write global tags (inputs, typically) |
| `pulse` | `tag` | momentary button: one scan TRUE, one scan FALSE |
| `scan` | `{n:, dt_ms:}` (both optional) | execute n scans of dt_ms each |
| `run` | `{ms:, dt_ms:}` | advance simulated time, scanning every dt_ms |
| `expect` | `{tag: value, ...}` | assert current values; failure reports step, value, and sim time |
| `model` | `{input:, output:, gain:, tau_ms:, ambient:}` | attach a first-order plant: each scan, `output` relaxes toward `ambient + gain * input` with time constant `tau_ms` — closes the loop for PID/analog tests |
| `expect_near` | `{tag: {value:, tol:}}` | assert an analog value within tolerance (default tol: 5% of value) |

Timing note: timers accumulate real simulated milliseconds, so a `T#3s`
on-delay needs `run: {ms: 3000+}` (plus a scan or two of margin for the
element ordering) before its effect is observable.

Programs containing raw `st` elements cannot be simulated; `ladder test
--skip-raw` ignores them (the rest of the logic still runs), otherwise
they are an error.
