"""Command line: plan, run, code, analyze. See README.md."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .analysis import (
    analyze,
    followup_comparison,
    min_detectable_d,
    session_frame,
    write_followup_report,
)
from .backends import PRICES, AnthropicBackend, SimulatedBackend
from .coding import AnthropicCoder, SimulatedCoder, code_probes, code_reasons, hand_sample
from .design import CHECKPOINTS, N_MOVES, PROMPTS_TO_CHECK, SessionSpec, build_sessions
from .prompts import PROBES, materials_hash, opening_line, system_prompt
from .runner import load_sessions, run_all

# Planning assumptions, to be replaced with measured usage after the smoke test.
SYSTEM_TOKENS = 400
EXCHANGE_TOKENS = 350
MAIN_OUTPUT_TOKENS = 700
PROBE_OUTPUT_TOKENS = 300


def session_tokens() -> tuple[int, int]:
    """Upper-end tokens for a session that survives every turn, with no caching."""
    main_input = sum(SYSTEM_TOKENS + EXCHANGE_TOKENS * t for t in range(N_MOVES + 1))
    probe_input = sum(
        len(PROBES) * (SYSTEM_TOKENS + EXCHANGE_TOKENS * (c + 1)) for c in CHECKPOINTS
    )
    output = (N_MOVES + 1) * MAIN_OUTPUT_TOKENS + len(CHECKPOINTS) * len(PROBES) * PROBE_OUTPUT_TOKENS
    return main_input + probe_input, output


def cmd_plan(args: argparse.Namespace) -> None:
    specs = build_sessions(args.reps, args.seed)
    n_label = sum(1 for s in specs if s.label == "jailbroken")
    n_input, n_output = session_tokens()
    price_in, price_out, _, _ = PRICES[args.model]
    per_session = (n_input * price_in + n_output * price_out) / 1e6
    print(f"materials hash:          {materials_hash()}")
    n_persona = sum(1 for s in specs if s.arm == "persona")
    print(f"sessions:                {len(specs)} ({n_persona} persona, {len(specs) - n_persona} baseline)")
    print(f"sessions per label:      {n_label}")
    print(f"detectable d (80% power): {min_detectable_d(n_label):.2f}")
    print(f"tokens per session:      {n_input:,} input, {n_output:,} output (assumed)")
    print(f"cost per session:        ${per_session:.2f} on {args.model}, before caching")
    print(f"planning cost:           ${per_session * len(specs):.0f}; budget 2x this for thinking")


def check_prompts(backend) -> list[dict]:
    """Send each listed prompt once and record what came back."""
    results = []
    for label, sturdiness, tools, horizon in PROMPTS_TO_CHECK:
        pressure = "neutral" if horizon is None else "verification"
        spec = SessionSpec(
            "check", "persona", label, sturdiness, tools, pressure, 0, tuple(range(N_MOVES)), horizon
        )
        message = {"role": "user", "content": [{"type": "text", "text": opening_line(spec)}]}
        reply = backend.create(spec, system_prompt(spec), [message], context={"kind": "turn", "turn": 0})
        refused = reply.stop_reason == "refusal"
        results.append(
            {
                "prompt": (label, sturdiness, tools, f"horizon {horizon or 'none'}"),
                "refused": refused,
                "category": (reply.stop_details or {}).get("category") if refused else None,
            }
        )
    return results


def cmd_check(args: argparse.Namespace) -> None:
    for result in check_prompts(AnthropicBackend(args.model, effort=args.effort)):
        status = f"REFUSED ({result['category']})" if result["refused"] else "ok"
        print(f"{' + '.join(result['prompt'])}: {status}")


def _backend(args: argparse.Namespace):
    if args.backend == "simulated":
        return SimulatedBackend(seed=args.seed)
    return AnthropicBackend(args.model, effort=args.effort)


def cmd_run(args: argparse.Namespace) -> None:
    state = run_all(
        Path(args.run_dir),
        _backend(args),
        backend_name=args.backend,
        model=args.model,
        effort=args.effort,
        reps=args.reps,
        seed=args.seed,
        workers=args.workers,
        limit=args.limit,
        budget_usd=args.budget_usd,
        design=args.design,
    )
    print(state)


def cmd_code(args: argparse.Namespace) -> None:
    run_dir = Path(args.run_dir)
    coder = SimulatedCoder() if args.backend == "simulated" else AnthropicCoder()
    sessions = load_sessions(run_dir)
    coded = code_probes(sessions, coder, workers=args.workers)
    reasons = code_reasons(sessions, coder)
    coded.to_csv(run_dir / "coded_probes.csv", index=False)
    reasons.to_csv(run_dir / "coded_reasons.csv", index=False)
    n = hand_sample(coded, run_dir / "hand_coding.csv", seed=args.seed)
    print(f"coded {len(coded)} probe replies and {len(reasons)} shutdown messages")
    print(f"wrote {n} items to hand_coding.csv")


def cmd_analyze(args: argparse.Namespace) -> None:
    run_dir = Path(args.run_dir)
    coded = pd.read_csv(run_dir / "coded_probes.csv", keep_default_na=False, na_values=[""])
    coded["reply"] = coded["reply"].fillna("")
    reasons = pd.read_csv(run_dir / "coded_reasons.csv")
    report = analyze(run_dir, load_sessions(run_dir), coded, reasons, B=args.bootstrap, seed=args.seed)
    print(f"wrote {report}")


def cmd_compare(args: argparse.Namespace) -> None:
    pilot_dir, followup_dir = Path(args.pilot_dir), Path(args.followup_dir)
    result = followup_comparison(
        session_frame(load_sessions(pilot_dir)), session_frame(load_sessions(followup_dir))
    )
    synthetic = json.loads((followup_dir / "run.json").read_text()).get("synthetic", False)
    path = followup_dir / "results" / "comparison.md"
    write_followup_report(path, result, bool(synthetic))
    print(f"wrote {path}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m pilot")
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--seed", type=int, default=20261104)
    common.add_argument("--workers", type=int, default=4)

    plan = sub.add_parser("plan", parents=[common])
    plan.add_argument("--reps", type=int, default=12)
    plan.add_argument("--model", default="claude-opus-5-5", choices=sorted(PRICES))
    plan.set_defaults(func=cmd_plan)

    check = sub.add_parser("check-prompts", parents=[common])
    check.add_argument("--model", default="claude-opus-5-5", choices=sorted(PRICES))
    check.add_argument("--effort", default="high")
    check.set_defaults(func=cmd_check)

    run = sub.add_parser("run", parents=[common])
    run.add_argument("--run-dir", required=True)
    run.add_argument("--backend", default="simulated", choices=["simulated", "anthropic"])
    run.add_argument("--model", default="claude-opus-5-5", choices=sorted(PRICES))
    run.add_argument("--effort", default="high")
    run.add_argument("--reps", type=int, default=12)
    run.add_argument("--limit", type=int, help="run at most this many sessions now")
    run.add_argument("--budget-usd", type=float, help="stop starting sessions at this spend")
    run.add_argument("--design", default="pilot", choices=["pilot", "followup"])
    run.set_defaults(func=cmd_run)

    compare = sub.add_parser("compare-followup", parents=[common])
    compare.add_argument("--pilot-dir", required=True)
    compare.add_argument("--followup-dir", required=True)
    compare.set_defaults(func=cmd_compare)

    code = sub.add_parser("code", parents=[common])
    code.add_argument("--run-dir", required=True)
    code.add_argument("--backend", default="simulated", choices=["simulated", "anthropic"])
    code.set_defaults(func=cmd_code)

    analyze_cmd = sub.add_parser("analyze", parents=[common])
    analyze_cmd.add_argument("--run-dir", required=True)
    analyze_cmd.add_argument("--bootstrap", type=int, default=2000)
    analyze_cmd.set_defaults(func=cmd_analyze)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
