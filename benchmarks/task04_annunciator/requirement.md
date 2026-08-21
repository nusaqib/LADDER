# Task 04 — Alarm annunciator with first-out

A compressor room has three supervised conditions, each a fail-safe BOOL
input (1 = OK): cooling water flow `water_ok`, discharge temperature
`temp_ok`, and oil pressure `oil_ok`. Build a three-window annunciator:

- A group lamp `panel_lamp` is lit while ANY alarm is latched.
- A horn `horn` sounds for unacknowledged alarms and must re-sound when a
  NEW alarm arrives, even if earlier ones are still standing.
- A single acknowledge pushbutton `ack_pb` silences the horn; an alarm
  window clears only if its cause is gone when acknowledged — a standing
  cause keeps its window latched.
- An INT `first_out` reports which condition tripped FIRST since the
  panel was last clear: 0 = none, 1 = water, 2 = temperature, 3 = oil.
  It must not change when later alarms arrive, and resets when the panel
  clears.
- The water-flow condition is noisy: debounce it 2 seconds. The other
  two trip immediately.

Declare every tag with direction and a comment. Alarm-present conditions
are the INVERSE of the OK inputs.
