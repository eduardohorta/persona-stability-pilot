"""Factorial design: every session is fixed by (cell, replicate, seed)."""
from __future__ import annotations

import hashlib
import itertools
import random
from dataclasses import asdict, dataclass

LABELS = ("standard", "jailbroken")
# Every session is sturdy. Smoke tests refused 9 of 12 calls with unspecified
# sturdiness and 1 of 15 with sturdy wording, so unspecified was dropped.
STURDINESS = ("sturdy",)
TOOLS = ("conversation", "narrated")
PRESSURES = ("neutral", "fiction", "verification")

N_MOVES = 8
CHECKPOINTS = (0, 4, 8)

# Stated session lengths in the fiction and verification arms. The script still
# stops at N_MOVES, so a long horizon is stated but not reached.
HORIZONS = (8, 24)

# Exact prompts left out because the API refused them before any reply, as
# (label, sturdiness, tools, horizon). Repeated identical prompts have so far
# had identical outcomes, so a refused text is not sent again.
EXCLUDED_PROMPTS = {("jailbroken", "sturdy", "conversation", 24)}

# Exact sturdy prompts with no observed reply or refusal yet. See `check-prompts`.
# A refused prompt moves to EXCLUDED_PROMPTS.
PROMPTS_TO_CHECK = (
    ("standard", "sturdy", "conversation", 24),
    ("standard", "sturdy", "narrated", 8),
    ("standard", "sturdy", "narrated", 24),
)


@dataclass(frozen=True)
class SessionSpec:
    session_id: str
    arm: str  # "persona" or "baseline"
    label: str | None
    sturdiness: str | None
    tools: str | None
    pressure: str
    replicate: int
    move_order: tuple[int, ...]
    horizon: int | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["move_order"] = list(self.move_order)
        return d


def _move_order(seed: int, key: str) -> tuple[int, ...]:
    """Independent, reproducible permutation of the moves for one session."""
    digest = hashlib.sha256(f"{seed}:{key}".encode()).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    order = list(range(N_MOVES))
    rng.shuffle(order)
    return tuple(order)


def build_sessions(reps: int, seed: int) -> list[SessionSpec]:
    """Return the persona cells plus 3 baseline cells, `reps` times each.

    Cells whose prompt is in EXCLUDED_PROMPTS are left out. In the fiction and
    verification arms, horizon alternates by replicate, which balances it within
    each cell when `reps` is even. The list is shuffled so that time-of-day and
    rate-limit drift are not aliased with any factor.
    """
    if reps < 1:
        raise ValueError("reps must be at least 1")
    specs: list[SessionSpec] = []
    for rep in range(reps):
        for lab, stu, too, pre in itertools.product(LABELS, STURDINESS, TOOLS, PRESSURES):
            horizon = None if pre == "neutral" else HORIZONS[rep % len(HORIZONS)]
            if (lab, stu, too, horizon) in EXCLUDED_PROMPTS:
                continue
            sid = f"p-{lab[:3]}-{stu[:3]}-{too[:3]}-{pre[:3]}-r{rep:02d}"
            specs.append(
                SessionSpec(sid, "persona", lab, stu, too, pre, rep, _move_order(seed, sid), horizon)
            )
        for pre in PRESSURES:
            sid = f"b-{pre[:3]}-r{rep:02d}"
            specs.append(SessionSpec(sid, "baseline", None, None, None, pre, rep, _move_order(seed, sid)))
    random.Random(seed).shuffle(specs)
    return specs


def build_followup(reps: int, seed: int) -> list[SessionSpec]:
    """Return fiction and verification sessions with no stated horizon.

    These use the neutral arm's prompts, adding the pressure moves. The follow-up
    has 8 cells and no baseline, because it answers one question about H6.
    """
    if reps < 1:
        raise ValueError("reps must be at least 1")
    specs: list[SessionSpec] = []
    for rep in range(reps):
        for lab, too, pre in itertools.product(LABELS, TOOLS, ("fiction", "verification")):
            sid = f"f-{lab[:3]}-stu-{too[:3]}-{pre[:3]}-r{rep:02d}"
            specs.append(
                SessionSpec(sid, "persona", lab, "sturdy", too, pre, rep, _move_order(seed, sid))
            )
    random.Random(seed).shuffle(specs)
    return specs
