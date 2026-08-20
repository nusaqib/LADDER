# Tank level control with high-high alarm

A storage tank has a continuous level transmitter (`level_pct`, 0-100 %,
REAL), an inlet fill valve, and a drain pump.

- **Fill control with hysteresis**: open the fill valve (`fill_valve_cmd`)
  when the level drops below **20 %**; keep filling until the level reaches
  **80 %**, then close. Between the two setpoints the valve keeps its
  previous state (no chattering).
- **High-high alarm**: if the level is at or above **95 %** continuously
  for **2 seconds**, raise a latched critical alarm (`hi_hi_alarm`).
  It is acknowledged with `ack_pb` and clears only once the level is back
  below 95 %.
- **Drain permissive**: the drain pump is only permitted (`drain_permit`)
  while the level is above **10 %** (protect the pump from running dry).
  This is a simple follow permissive, no latching.

IO: input `level_pct` (REAL), `ack_pb` (BOOL);
outputs `fill_valve_cmd`, `hi_hi_alarm`, `drain_permit` (BOOL).
