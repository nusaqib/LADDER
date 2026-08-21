"""`ladder sim` - poke the logic interactively, scan by scan.

A commissioning panel in a terminal: set inputs, press buttons, advance
time, watch outputs - against the same scan-accurate simulator the
scenarios use. For the one weird timing you want to *explore* rather
than script.

    > help
    > set estop_ok true          > pulse start_pb
    > watch motor_run run_permit > run 1500 50
    > state                      > quit
"""

from __future__ import annotations

from ladder.ir.model import Project
from ladder.sim import FirstOrderProcess, SimError, Simulator

_HELP = """\
commands:
  set <tag> <value>       write a tag (true/false/int/float; dotted paths ok)
  pulse <tag>             one scan true, one scan false (button press)
  scan [n] [dt_ms]        advance n scans (default 1, dt 10ms)
  run <ms> [dt_ms]        advance simulated time
  get <tag>               print one tag
  watch <tag> [...]       print these tags after every command (no args: clear)
  state                   every non-default tag (the interesting ones)
  model <in> <out> <gain> <tau_ms> [ambient]   attach first-order plant
  reset                   fresh simulator (same project)
  help                    this text
  quit / exit / ctrl-d    leave"""


def _parse(value: str):
    low = value.lower()
    if low in ("true", "1", "on"):
        return True
    if low in ("false", "0", "off"):
        return False
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def _state_lines(sim: Simulator) -> list[str]:
    out = []
    for tag in sorted(sim.globals):
        v = sim.get(tag)
        if isinstance(v, dict):  # UDT instance: show non-default members
            for m, mv in sorted(v.items()):
                if mv:
                    out.append(f"  {tag}.{m} = {mv}")
        elif v:
            out.append(f"  {tag} = {v}")
    return out or ["  (everything at defaults/0)"]


def run_repl(project: Project, input_fn=input, print_fn=print) -> int:
    sim = Simulator(project, on_raw="skip")
    watches: list[str] = []
    print_fn(f"simulating {project.name} - {len(project.tags)} tags, "
             f"{len(project.programs)} program(s). type 'help'.")

    while True:
        try:
            line = input_fn("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print_fn("")
            return 0
        if not line:
            continue
        cmd, *args = line.split()
        try:
            if cmd in ("quit", "exit", "q"):
                return 0
            elif cmd == "help":
                print_fn(_HELP)
            elif cmd == "set" and len(args) >= 2:
                sim.set(args[0], _parse(args[1]))
                sim.scan()
            elif cmd == "pulse" and args:
                sim.pulse(args[0])
            elif cmd == "scan":
                n = int(args[0]) if args else 1
                dt = int(args[1]) if len(args) > 1 else 10
                sim.scan(dt_ms=dt, n=n)
            elif cmd == "run" and args:
                dt = int(args[1]) if len(args) > 1 else 10
                sim.run(int(args[0]), dt_ms=dt)
            elif cmd == "get" and args:
                print_fn(f"  {args[0]} = {sim.get(args[0])}")
                continue
            elif cmd == "watch":
                watches = list(args)
                if not watches:
                    print_fn("  watches cleared")
                continue
            elif cmd == "state":
                for line_ in _state_lines(sim):
                    print_fn(line_)
                continue
            elif cmd == "model" and len(args) >= 4:
                sim.attach_model(FirstOrderProcess(
                    input=args[0], output=args[1], gain=float(args[2]),
                    tau_ms=float(args[3]),
                    ambient=float(args[4]) if len(args) > 4 else 0.0))
                print_fn(f"  plant attached: {args[1]} <- {args[0]}")
                continue
            elif cmd == "reset":
                sim = Simulator(project, on_raw="skip")
                print_fn("  fresh simulator")
                continue
            else:
                print_fn(f"  ? unknown/incomplete command {line!r} - 'help'")
                continue
        except (SimError, ValueError, KeyError) as e:
            print_fn(f"  error: {e}")
            continue
        stamp = f"  [t={sim.time_ms}ms scan={sim.scan_count}]"
        if watches:
            vals = " ".join(f"{w}={sim.get(w)}" for w in watches)
            print_fn(f"{stamp} {vals}")
        else:
            print_fn(stamp)
