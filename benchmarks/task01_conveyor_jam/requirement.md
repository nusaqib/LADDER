# Conveyor with jam detection

A belt conveyor is driven by one motor.

- The operator starts the conveyor with a momentary **start pushbutton**
  (`start_pb`). The motor seals in: it keeps running after the button is
  released.
- A **stop chain** input (`stop_ok`) is healthy when TRUE. If it goes
  unhealthy the motor must stop immediately.
- A **motion sensor** (`motion_ok`) is TRUE while the belt is actually
  moving. If the motor is commanded to run but no motion is seen for
  **3 seconds**, that is a jam: raise a latched **jam alarm** (`jam_alarm`)
  and stop the motor.
- The jam alarm is acknowledged with `ack_pb`, but only clears once the jam
  condition is gone. After acknowledging, the operator can restart with the
  start pushbutton.

IO (all BOOL): inputs `start_pb`, `stop_ok`, `motion_ok`, `ack_pb`;
outputs `conveyor_run`, `jam_alarm`.
