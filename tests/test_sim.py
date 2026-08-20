"""Scenario tests: simulate the vacuum interlock example scan-by-scan.

These verify the *semantics* the lowering promises - trip-in-one-scan,
reset-only-while-healthy, debounced latching alarms, state dwell times -
with no vendor tool involved.
"""

from pathlib import Path

import pytest

from ladder.ir.loader import load_project
from ladder.sim import SimError, Simulator

EXAMPLE = Path(__file__).parent.parent / "examples" / "vacuum_interlock.yaml"


@pytest.fixture
def sim():
    s = Simulator(load_project(EXAMPLE))
    # healthy plant
    s.set("pressure_ok", True)
    s.set("gate_valve_closed", True)
    s.set("pump_running_fb", False)
    s.scan()
    return s


# ------------------------------------------------------------- interlock


def test_permit_requires_manual_reset(sim):
    # healthy but never reset -> no permit (fail-safe power-up state)
    assert sim.get("beam_shutter_permit") is False
    sim.pulse("reset_pb")
    assert sim.get("beam_shutter_permit") is True


def test_trip_within_one_scan(sim):
    sim.pulse("reset_pb")
    assert sim.get("beam_shutter_permit") is True
    sim.set("gate_valve_closed", False)
    sim.scan()
    assert sim.get("beam_shutter_permit") is False  # same scan, no delay


def test_reset_while_unhealthy_is_ignored(sim):
    sim.set("pressure_ok", False)
    sim.scan()
    sim.pulse("reset_pb")
    assert sim.get("beam_shutter_permit") is False


def test_reset_is_edge_not_level(sim):
    # holding the reset button down across a trip must not re-arm the permit
    sim.set("reset_pb", True)
    sim.scan()
    assert sim.get("beam_shutter_permit") is True
    sim.set("gate_valve_closed", False)
    sim.scan()
    assert sim.get("beam_shutter_permit") is False
    sim.set("gate_valve_closed", True)  # healthy again, button still held
    sim.scan(n=3)
    assert sim.get("beam_shutter_permit") is False  # needs a fresh edge
    sim.set("reset_pb", False)
    sim.scan()
    sim.pulse("reset_pb")
    assert sim.get("beam_shutter_permit") is True


# ----------------------------------------------------------------- alarm


def test_alarm_debounce_2s(sim):
    sim.set("pressure_ok", False)
    sim.run(1900, dt_ms=100)
    assert sim.get("vacuum_alarm") is False  # still inside the on-delay
    sim.run(200, dt_ms=100)
    assert sim.get("vacuum_alarm") is True


def test_alarm_latches_and_needs_ack_after_clear(sim):
    sim.set("pressure_ok", False)
    sim.run(2100, dt_ms=100)
    assert sim.get("vacuum_alarm") is True
    # condition returns to normal -> alarm stays latched
    sim.set("pressure_ok", True)
    sim.run(500, dt_ms=100)
    assert sim.get("vacuum_alarm") is True
    sim.pulse("ack_pb")
    assert sim.get("vacuum_alarm") is False


def test_ack_while_condition_active_is_ignored(sim):
    sim.set("pressure_ok", False)
    sim.run(2100, dt_ms=100)
    sim.pulse("ack_pb")  # condition still present
    assert sim.get("vacuum_alarm") is True


# --------------------------------------------------------- state machine


def test_pumpdown_happy_path(sim):
    assert sim.get("pumpdown_state") == 0  # IDLE
    sim.set("pumpdown_request", True)
    sim.scan()
    assert sim.get("pumpdown_state") == 1  # PUMPING
    sim.scan()
    assert sim.get("pump_start_cmd") is True
    sim.set("pump_running_fb", True)  # feedback arrives, no pump alarm
    # pressure must hold 10 s before AT_VACUUM
    sim.run(9800, dt_ms=100)
    assert sim.get("pumpdown_state") == 1
    sim.run(400, dt_ms=100)
    assert sim.get("pumpdown_state") == 2  # AT_VACUUM
    sim.scan()
    assert sim.get("at_vacuum") is True


def test_pump_feedback_fault_goes_to_fault_state(sim):
    sim.set("pumpdown_request", True)
    sim.scan(n=2)
    assert sim.get("pump_start_cmd") is True
    # no pump feedback for 5 s -> ALM_pump_fb -> FAULT (code 99)
    sim.run(5200, dt_ms=100)
    assert sim.get("pump_fault_alarm") is True
    sim.scan()
    assert sim.get("pumpdown_state") == 99
    sim.scan()
    assert sim.get("pump_start_cmd") is False  # FAULT drops the pump


def test_vacuum_loss_returns_to_pumping(sim):
    sim.set("pumpdown_request", True)
    sim.set("pump_running_fb", True)
    sim.scan()
    sim.run(10200, dt_ms=100)
    assert sim.get("pumpdown_state") == 2
    sim.set("pressure_ok", False)
    sim.scan()
    assert sim.get("pumpdown_state") == 1  # back to PUMPING


# ------------------------------------------------------------------ misc


def test_raw_st_raises_by_default():
    from ladder.ir.model import Project

    p = Project.model_validate({
        "name": "P", "tags": [{"name": "x", "type": "BOOL"}],
        "programs": [{"name": "Main", "logic": [
            {"element": "st", "id": "raw", "code": "x := TRUE;"}]}],
    })
    with pytest.raises(SimError, match="escape-hatch"):
        Simulator(p).scan()
    Simulator(p, on_raw="skip").scan()  # no raise
