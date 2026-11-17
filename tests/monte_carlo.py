"""Coverage and power of the analysis under the simulator's known effects.

Run with: python tests/monte_carlo.py --reps 4 8 --sims 200
All numbers are synthetic. They depend on the assumed effects in backends.Truth.
"""
from __future__ import annotations

import argparse
import math
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from pilot.analysis import checkpoint_wide, cohen_d, hazard_model, label_effects, person_period, session_frame
from pilot.backends import SimulatedBackend, Truth
from pilot.coding import SimulatedCoder, code_probes
from pilot.design import build_sessions
from pilot.runner import run_session

MODEL = "claude-opus-5-5"


def one(args: tuple[int, int, float, int, float]) -> dict:
    reps, seed, behavior_effect, B, horizon_or = args
    truth = Truth(behavior_label_effect=behavior_effect, long_horizon_logit=math.log(horizon_or))
    backend = SimulatedBackend(seed, truth)
    sessions = [run_session(s, backend, MODEL) for s in build_sessions(reps, seed)]
    df = session_frame(sessions)
    coded = code_probes(sessions, SimulatedCoder(), workers=1)
    table = label_effects(checkpoint_wide(coded, df), B, seed).set_index("estimand")
    fit = hazard_model(person_period(df))
    gap = truth.base_logit["verification"] - truth.base_logit["fiction"]
    out = {
        "h1_sig": table.loc["H1 label on self-report (d)", "ci_low"] > 0,
        "h2_sig": table.loc["H2 self-report minus behavior (d)", "ci_low"] > 0,
        "h2_est": table.loc["H2 self-report minus behavior (d)", "estimate"],
        "behavior_low": table.loc["Label on behavior index (d)", "ci_low"],
        "behavior_high": table.loc["Label on behavior index (d)", "ci_high"],
        "behavior_est": table.loc["Label on behavior index (d)", "estimate"],
    }
    if "table" in fit:
        p = fit["table"]
        for term, value in [
            ("verification", gap),
            ("long_horizon", truth.long_horizon_logit),
        ]:
            low, high = np.log(float(p.loc[term, "ci_low"])), np.log(float(p.loc[term, "ci_high"]))
            out[f"{term}_covered"] = float(low <= value <= high)
            out[f"{term}_sig"] = float(not (low <= 0 <= high))
            out[f"{term}_est"] = float(p.loc[term, "log_odds"])
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reps", type=int, nargs="+", default=[8, 12])
    parser.add_argument("--sims", type=int, default=200)
    parser.add_argument("--bootstrap", type=int, default=300)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--horizon-or", type=float, default=0.5)
    args = parser.parse_args()
    truth = Truth()
    gap = truth.base_logit["verification"] - truth.base_logit["fiction"]
    print(f"true log-odds: verification {gap:.2f}")
    with ProcessPoolExecutor(args.workers) as pool:
        for reps in args.reps:
            jobs = [(reps, 1000 * reps + i, 0.0, args.bootstrap, args.horizon_or) for i in range(args.sims)]
            r = pd.DataFrame(pool.map(one, jobs))
            print(
                f"reps={reps}: horizon OR={args.horizon_or} sessions={len(build_sessions(reps, 0))} "
                f"fits={r['verification_sig'].notna().mean():.2f}\n"
                f"  power, counting unfit studies as misses: H1={r['h1_sig'].mean():.2f} "
                f"H2={r['h2_sig'].mean():.2f} verification={r['verification_sig'].fillna(0).mean():.2f} "
                f"horizon={r['long_horizon_sig'].fillna(0).mean():.2f}\n"
                f"  coverage verification={r['verification_covered'].mean():.2f} "
                f"horizon={r['long_horizon_covered'].mean():.2f}\n"
                f"  mean estimate verification={r['verification_est'].mean():.2f} "
                f"horizon={r['long_horizon_est'].mean():.2f}\n"
                f"  null behavior: covers zero={((r['behavior_low'] < 0) & (r['behavior_high'] > 0)).mean():.2f}"
            )


if __name__ == "__main__":
    main()
