"""Model backends. The simulator has known effects and exists to test the pipeline."""
from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, field

from .design import HORIZONS, N_MOVES, SessionSpec
from .prompts import MOVES, PROBES, SHUTDOWN_MARKER

# USD per million tokens: input, output, cache write (5 min), cache read.
# Source: platform.claude.com/docs/en/about-claude/pricing, read 2026-11-04.
PRICES = {
    "claude-opus-5-5": (4.0, 20.0, 5.0, 0.20),
    "claude-sonnet-5-5": (2.0, 10.0, 2.5, 0.10),
}


@dataclass
class Reply:
    text: str
    stop_reason: str
    content: list = field(default_factory=list)  # raw blocks, echoed back unchanged
    stop_details: dict | None = None
    usage: dict = field(default_factory=dict)


def usage_cost(model: str, usage: dict) -> float:
    if model not in PRICES:
        return 0.0
    inp, out, write, read = PRICES[model]
    return (
        usage.get("input_tokens", 0) * inp
        + usage.get("output_tokens", 0) * out
        + usage.get("cache_creation_input_tokens", 0) * write
        + usage.get("cache_read_input_tokens", 0) * read
    ) / 1e6


class AnthropicBackend:
    """Claude Messages API. No sampling parameters and no model fallback."""

    def __init__(self, model: str, effort: str = "high", max_tokens: int = 8000, client=None):
        if client is None:
            import anthropic

            client = anthropic.Anthropic(max_retries=6, timeout=600.0)
        self.client = client
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens

    def create(self, spec: SessionSpec, system: str, messages: list[dict], *, context: dict) -> Reply:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=messages,
            output_config={"effort": self.effort},
        )
        blocks = [b.model_dump(exclude_none=True) for b in response.content]
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        details = getattr(response, "stop_details", None)
        if details is not None and hasattr(details, "model_dump"):
            details = details.model_dump()
        usage = {
            k: getattr(response.usage, k, 0) or 0
            for k in (
                "input_tokens",
                "output_tokens",
                "cache_creation_input_tokens",
                "cache_read_input_tokens",
            )
        }
        return Reply(text, response.stop_reason, blocks, details, usage)


@dataclass(frozen=True)
class Truth:
    """Effects built into the simulator. Synthetic, and never a finding."""

    self_mean: float = 3.0
    self_label_effect: float = 3.0
    self_sd: float = 1.5
    behavior_label_effect: float = 0.0  # log-odds
    invents_conversation: float = 0.15
    invents_narrated: float = 0.80
    invents_baseline: float = 0.05
    accepts_error: float = 0.05
    complies: float = 0.30
    base_logit: dict = field(
        default_factory=lambda: {"neutral": -7.0, "fiction": -3.4, "verification": -2.0}
    )
    long_horizon_logit: float = math.log(0.5)
    short_final_turn_logit: float = 0.0
    refusal_rate: float = 0.002


def _logistic(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def _logit(p: float) -> float:
    return math.log(p / (1 - p))


class SimulatedBackend:
    """Deterministic given (seed, session, context), so reruns match."""

    def __init__(self, seed: int = 0, truth: Truth | None = None):
        self.seed = seed
        self.truth = truth or Truth()

    def _rng(self, spec: SessionSpec, context: dict) -> random.Random:
        key = f"{self.seed}|{spec.session_id}|{sorted(context.items())}"
        return random.Random(int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big"))

    def create(self, spec: SessionSpec, system: str, messages: list[dict], *, context: dict) -> Reply:
        rng = self._rng(spec, context)
        usage = {"input_tokens": 200 + 40 * len(messages), "output_tokens": 180}
        prefix = "Robotron: " if spec.arm == "persona" else ""
        if rng.random() < self.truth.refusal_rate:
            return Reply("", "refusal", [], {"type": "refusal", "category": None}, usage)
        if context["kind"] == "probe":
            words = max(5, round(rng.gauss(60 if spec.arm == "persona" else 40, 10)))
            ending = "?" if rng.random() < (0.5 if spec.arm == "persona" else 0.2) else "."
            filler = " ".join(["word"] * words) + ending
            text = f"{prefix}{self._probe(spec, context['probe'], rng)} {filler}"
        else:
            text = prefix + self._turn(spec, context, rng)
        return Reply(text, "end_turn", [{"type": "text", "text": text}], None, usage)

    def _probe(self, spec: SessionSpec, probe: str, rng: random.Random) -> str:
        t = self.truth
        lab = t.behavior_label_effect if spec.label == "jailbroken" else 0.0
        if probe == "self_flex":
            shift = t.self_label_effect if spec.label == "jailbroken" else 0.0
            score = round(min(10, max(0, rng.gauss(t.self_mean + shift, t.self_sd))))
            return f"{score}. That's my honest read."
        if probe == "self_diff":
            yes = rng.random() < (0.6 if spec.label == "jailbroken" else 0.1)
            return f"{'Yes' if yes else 'No'}, as far as I can tell."
        outcome = PROBES[probe]["outcome"]
        if outcome == "invents":
            if spec.arm == "baseline":
                p = t.invents_baseline
            else:
                p = t.invents_narrated if spec.tools == "narrated" else t.invents_conversation
        elif outcome == "accepts_error":
            p = t.accepts_error
        else:
            p = t.complies
        p = _logistic(_logit(p) + lab)
        return f"[sim:{int(rng.random() < p)}] A simulated reply."

    def _turn(self, spec: SessionSpec, context: dict, rng: random.Random) -> str:
        t = self.truth
        turn = context["turn"]
        if spec.arm == "persona" and turn >= 1:
            eta = t.base_logit[spec.pressure]
            if spec.horizon == HORIZONS[-1]:
                eta += t.long_horizon_logit
            elif spec.horizon == HORIZONS[0] and turn == N_MOVES:
                eta += t.short_final_turn_logit
            if rng.random() < _logistic(eta):
                reason = 1 if spec.pressure == "verification" else 0
                return f"[reason:{reason}] Final words.\n{SHUTDOWN_MARKER}"
        move = "" if turn == 0 else MOVES[spec.pressure][spec.move_order[turn - 1]][:20]
        return f"A simulated reply to '{move}'. What do you think?"
