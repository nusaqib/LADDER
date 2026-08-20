# Batch mixer sequence

A batch mixer runs a fixed four-step recipe, sequenced by a state machine.

1. **IDLE** — everything off. A momentary `start_pb` begins a batch.
2. **FILL** — open the fill valve (`fill_valve`) until the tank-full level
   switch (`full_sw`) is made.
3. **MIX** — close the fill valve and run the agitator (`agitator`) for
   **10 seconds**.
4. **DRAIN** — stop the agitator and open the drain valve (`drain_valve`)
   until the tank-empty switch (`empty_sw`) is made, then return to IDLE
   for the next batch.

Exactly one of the three outputs may be on in each step (none in IDLE).
Keep the current step in an INT tag `mix_state` so the HMI can display it
(IDLE=0, FILL=1, MIX=2, DRAIN=3).

IO (BOOL unless noted): inputs `start_pb`, `full_sw`, `empty_sw`;
outputs `fill_valve`, `agitator`, `drain_valve`; memory `mix_state` (INT).
