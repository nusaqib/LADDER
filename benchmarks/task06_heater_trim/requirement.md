# Task 06 — Heater output trim (proportional controller)

A process heater's control value `heater_cv` (REAL, 0.0–100.0 %) must
track a setpoint `temp_sp` against the measured value `temp_pv` (both
REAL, engineering units) with a proportional-only controller:

1. In automatic (`auto_mode` = TRUE): `heater_cv` = Kp × (SP − PV) with
   **Kp = 2.0**, clamped to 0.0…100.0.
2. Out of automatic: the controller FREEZES — `heater_cv` holds its last
   value regardless of SP/PV changes (a manual station owns the output;
   re-entry must be bumpless).
3. The control program executes every **100 ms** and the design must say
   so.

Declare every tag with direction and a comment.
