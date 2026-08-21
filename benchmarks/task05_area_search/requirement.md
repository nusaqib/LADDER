# Task 05 — Interlocked area search

A shielded enclosure must be searched before its permit can complete.
Fail-safe BOOL inputs (1 = OK/closed): the door `door_closed` and an
emergency-stop chain `estop_ok`. Three search keyswitches `key_a`,
`key_b`, `key_c` (1 = turned) are mounted along the required walk path,
in that order. Outputs: `inputs_ok` (all protective inputs healthy) and
`search_done`.

Rules, exactly:

1. `inputs_ok` = door closed AND e-stop chain healthy.
2. The search arms only while `inputs_ok` holds. Stations must latch in
   walk order A → B → C; a later station must NOT latch before its
   predecessor.
3. A station latches on the TURN of its key (rising edge) — a key
   already held while its predecessor latches must not count until it is
   released and turned again.
4. `search_done` is TRUE when station C is latched.
5. Opening the door or losing the e-stop chain clears ALL stations and
   `search_done` within one scan. Restoring the inputs must NOT restore
   the search — a full re-walk is required.
6. No acknowledge or reset signal exists that can restore a search.

Declare every tag with direction and a comment.
