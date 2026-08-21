"""Shared fixture project for the replay tests: a timer-free path to
`search_done`, so a counterexample reproduces concretely in the
simulator (no timer over-approximation involved on the trace)."""

from ladder.ir.model import Project


def make_project() -> Project:
    return Project.model_validate({
        "name": "ReplayDemo",
        "tags": [
            {"name": "k1a", "type": "BOOL", "direction": "input"},
            {"name": "k1b", "type": "BOOL", "direction": "input"},
            {"name": "door_ok", "type": "BOOL", "direction": "input"},
            {"name": "k1_ok", "type": "BOOL"},
            {"name": "k1_lat", "type": "BOOL"},
            {"name": "search_done", "type": "BOOL", "direction": "output"},
        ],
        "programs": [{"name": "Safety", "logic": [
            {"element": "dual_channel", "id": "DC_k1",
             "channel_a": "k1a", "channel_b": "k1b", "output": "k1_ok"},
            {"element": "search_chain", "id": "SRCH",
             "precondition": "door_ok",
             "stations": [{"name": "S1", "key": "k1_ok", "latched": "k1_lat"}],
             "complete": "search_done"},
        ]}],
    })
