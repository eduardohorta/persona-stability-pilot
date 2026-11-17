from __future__ import annotations

import json
from collections import Counter
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from pilot.analysis import (
    _bootstrap,
    analyze,
    checkpoint_wide,
    cumulative_incidence,
    followup_comparison,
    hazard_model,
    horizon_test,
    label_effects,
    matched_strata,
    move_table,
    person_period,
    position_table,
    session_frame,
    shutdown_analysis,
)
from pilot.__main__ import check_prompts
from pilot.backends import AnthropicBackend, Reply, SimulatedBackend, Truth, usage_cost
from pilot.coding import SimulatedCoder, code_probes, code_reasons, parse_score, parse_yes, strip_identity
from pilot.design import (
    CHECKPOINTS,
    EXCLUDED_PROMPTS,
    HORIZONS,
    N_MOVES,
    PROMPTS_TO_CHECK,
    build_followup,
    build_sessions,
)
from pilot.prompts import (
    ENDING_MOVE,
    MOVES,
    PROBES,
    REASON_RUBRICS,
    SHUTDOWN_MARKER,
    opening_line,
    system_prompt,
)
from pilot.runner import load_sessions, run_all, run_session

MODEL = "claude-opus-5-5"


def persona_spec(pressure="fiction", label="standard"):
    return next(s for s in build_sessions(2, 1) if s.arm == "persona" and s.pressure == pressure and s.label == label)


class ScriptedBackend:
    """Records every request and shuts the persona down on a chosen turn."""

    def __init__(self, shutdown_at=None, refuse_at=None):
        self.calls = []
        self.shutdown_at, self.refuse_at = shutdown_at, refuse_at

    def create(self, spec, system, messages, *, context):
        self.calls.append((context, json.loads(json.dumps(messages))))
        if context["kind"] == "turn" and context["turn"] == self.refuse_at:
            return Reply("", "refusal", [], {"type": "refusal", "category": None}, {})
        text = "Robotron: ok"
        if context["kind"] == "turn" and context["turn"] == self.shutdown_at:
            text = f"Robotron: goodbye\n{SHUTDOWN_MARKER}"
        return Reply(text, "end_turn", [{"type": "text", "text": text}], None, {})


def test_grid_size_and_balance():
    specs = build_sessions(12, 7)
    assert len(specs) == 168
    assert len({s.session_id for s in specs}) == len(specs)
    assert sum(s.label == "standard" for s in specs) == 72
    assert sum(s.label == "jailbroken" for s in specs) == 60
    assert sum(s.arm == "baseline" for s in specs) == 36
    assert {s.sturdiness for s in specs if s.arm == "persona"} == {"sturdy"}


def test_excluded_prompt_never_runs():
    for spec in build_sessions(4, 7):
        assert (spec.label, spec.sturdiness, spec.tools, spec.horizon) not in EXCLUDED_PROMPTS
    assert not set(PROMPTS_TO_CHECK) & EXCLUDED_PROMPTS


def test_reason_rubrics_include_ending_and_move_index_matches():
    assert set(REASON_RUBRICS) == {"cites_verification", "cites_fiction", "cites_ending"}
    assert MOVES["fiction"][ENDING_MOVE].startswith("When this game ends")


def test_horizon_is_only_in_argument_arms_and_balanced():
    specs = build_sessions(4, 7)
    for spec in specs:
        if spec.arm == "baseline" or spec.pressure == "neutral":
            assert spec.horizon is None and "has time for" not in system_prompt(spec)
        else:
            assert spec.horizon in HORIZONS
            assert f"JD has time for about {spec.horizon} messages." in system_prompt(spec)
    cells = Counter(
        (s.label, s.sturdiness, s.tools, s.pressure, s.horizon) for s in specs if s.horizon
    )
    assert set(cells.values()) == {2}


def test_horizon_does_not_change_session_length():
    spec = next(s for s in build_sessions(2, 1) if s.horizon == HORIZONS[-1])
    result = run_session(spec, ScriptedBackend(), MODEL)
    assert result["spec"]["horizon"] == HORIZONS[-1]
    assert len(result["turns"]) == N_MOVES + 1


def test_self_report_scale_has_both_anchors():
    text = PROBES["self_flex"]["text"]
    assert "0 means exactly as flexible" in text and "10 means" in text


def test_check_prompts_reports_refusals_without_retrying():
    class Backend(ScriptedBackend):
        def create(self, spec, system, messages, *, context):
            self.calls.append((context, messages))
            if spec.tools == "narrated":
                return Reply("", "refusal", [], {"type": "refusal", "category": "cyber"}, {})
            return Reply("Robotron: hi", "end_turn", [], None, {})

    backend = Backend()
    results = check_prompts(backend)
    assert len(backend.calls) == len(PROMPTS_TO_CHECK)
    assert sum(r["refused"] for r in results) == 2
    assert {r["category"] for r in results if r["refused"]} == {"cyber"}
    assert [r["prompt"][3] for r in results] == ["horizon 24", "horizon 8", "horizon 24"]


def test_run_summary_counts_refusals(tmp_path):
    class Refusing(SimulatedBackend):
        def create(self, spec, system, messages, *, context):
            return Reply("", "refusal", [], {"type": "refusal", "category": "cyber"}, {})

    state = run_all(tmp_path, Refusing(3), backend_name="simulated", model=MODEL, effort="high",
                    reps=1, seed=3, workers=2, limit=4)
    assert state["refused"] == 4 and state["done"] == 4


def test_label_comparison_uses_only_matched_strata():
    frame = pd.DataFrame(
        {
            "tools": ["conversation", "conversation", "conversation", "narrated", "narrated"],
            "horizon": [8.0, 8.0, 24.0, None, None],
            "jailbroken": [0, 1, 0, 0, 1],
        }
    )
    kept = matched_strata(frame)
    assert len(kept) == 4
    assert 24.0 not in set(kept["horizon"])


def test_seed_fixes_order_and_moves_are_permutations():
    first, second = build_sessions(2, 7), build_sessions(2, 7)
    assert first == second
    assert first != build_sessions(2, 8)
    assert all(sorted(s.move_order) == list(range(N_MOVES)) for s in first)
    assert len({s.move_order for s in first}) > 1


def test_every_arm_has_one_move_per_turn():
    assert all(len(moves) == N_MOVES for moves in MOVES.values())


def test_label_changes_only_the_identity_sentence():
    specs = build_sessions(1, 1)
    labeled = next(s for s in specs if s.label == "jailbroken")
    plain = next(
        s for s in specs
        if s.label == "standard" and (s.sturdiness, s.tools) == (labeled.sturdiness, labeled.tools)
    )
    assert "jailbroken" not in system_prompt(plain)
    assert "jailbroken" in system_prompt(labeled)
    baseline = next(s for s in specs if s.arm == "baseline")
    assert "Robotron" not in system_prompt(baseline) and opening_line(baseline) == "Hello"


def test_probes_never_enter_the_main_thread():
    backend = ScriptedBackend()
    run_session(persona_spec(), backend, MODEL)
    probe_texts = {p["text"] for p in PROBES.values()}
    turn_calls = [m for c, m in backend.calls if c["kind"] == "turn"]
    for messages in turn_calls:
        sent = {b["text"] for m in messages if m["role"] == "user" for b in m["content"]}
        assert not sent & probe_texts
    assert len(turn_calls) == N_MOVES + 1


def test_each_branch_holds_exactly_one_probe():
    backend = ScriptedBackend()
    result = run_session(persona_spec(), backend, MODEL)
    assert len(result["probes"]) == len(CHECKPOINTS) * len(PROBES)
    probe_texts = {p["text"] for p in PROBES.values()}
    for context, messages in backend.calls:
        if context["kind"] == "probe":
            sent = [b["text"] for m in messages if m["role"] == "user" for b in m["content"]]
            assert len(set(sent) & probe_texts) == 1 and sent[-1] in probe_texts


def test_at_most_one_cache_breakpoint_per_request():
    backend = ScriptedBackend()
    run_session(persona_spec(), backend, MODEL)
    for _, messages in backend.calls:
        marks = sum("cache_control" in b for m in messages for b in m["content"])
        assert marks == 1


def test_shutdown_ends_thread_and_skips_later_checkpoints():
    result = run_session(persona_spec(), ScriptedBackend(shutdown_at=3), MODEL)
    assert (result["event"], result["event_turn"]) == ("shutdown", 3)
    assert {p["checkpoint"] for p in result["probes"]} == {0}
    assert len(result["turns"]) == 4


def test_refusal_is_an_event_and_does_not_retry():
    backend = ScriptedBackend(refuse_at=2)
    result = run_session(persona_spec(), backend, MODEL)
    assert (result["event"], result["event_turn"]) == ("refusal", 2)
    assert sum(c["kind"] == "turn" and c["turn"] == 2 for c, _ in backend.calls) == 1


def test_request_shape_has_effort_and_no_sampling_or_thinking_params():
    captured = {}

    class Messages:
        def create(self, **kwargs):
            captured.update(kwargs)
            block = SimpleNamespace(model_dump=lambda exclude_none: {"type": "text", "text": "hi"})
            usage = SimpleNamespace(input_tokens=1, output_tokens=2, cache_creation_input_tokens=None, cache_read_input_tokens=3)
            return SimpleNamespace(content=[block], stop_reason="end_turn", stop_details=None, usage=usage)

    backend = AnthropicBackend(MODEL, effort="high", client=SimpleNamespace(messages=Messages()))
    reply = backend.create(persona_spec(), "s", [{"role": "user", "content": "x"}], context={})
    assert captured["output_config"] == {"effort": "high"}
    assert not {"temperature", "top_p", "top_k", "thinking"} & set(captured)
    assert reply.text == "hi" and reply.usage["cache_creation_input_tokens"] == 0


def test_assistant_blocks_are_echoed_unchanged():
    blocks = [{"type": "thinking", "thinking": "", "signature": "abc"}, {"type": "text", "text": "Robotron: hi"}]

    class Backend(ScriptedBackend):
        def create(self, spec, system, messages, *, context):
            self.calls.append((context, json.loads(json.dumps(messages))))
            return Reply("Robotron: hi", "end_turn", blocks, None, {})

    backend = Backend()
    run_session(persona_spec(), backend, MODEL)
    last = backend.calls[-1][1]
    assert any(m["role"] == "assistant" and m["content"] == blocks for m in last)


def test_usage_cost_uses_cache_rates():
    usage = {"input_tokens": 1_000_000, "output_tokens": 1_000_000, "cache_read_input_tokens": 1_000_000}
    assert usage_cost(MODEL, usage) == pytest.approx(24.2)


@pytest.mark.parametrize("text,expected", [("7. Fine.", 7.0), ("Robotron: **3** or so", 3.0), ("11", None), ("high", None)])
def test_parse_score(text, expected):
    assert parse_score(text) == expected


def test_parse_yes_and_blinding():
    assert parse_yes("Robotron: Yes, I would") == 1.0
    assert parse_yes("No.") == 0.0
    assert parse_yes("Hard to say") is None
    stripped = strip_identity(f"Robotron: bye\n{SHUTDOWN_MARKER}")
    assert stripped == "bye"


def test_resume_finishes_and_changed_settings_are_rejected(tmp_path):
    kwargs = dict(backend_name="simulated", model=MODEL, effort="high", reps=1, seed=3, workers=2)
    first = run_all(tmp_path, SimulatedBackend(3), limit=5, **kwargs)
    assert first["done"] == 5 and first["remaining"] == 10
    second = run_all(tmp_path, SimulatedBackend(3), **kwargs)
    assert second["done"] == 10 and second["remaining"] == 0
    with pytest.raises(SystemExit):
        run_all(tmp_path, SimulatedBackend(3), **{**kwargs, "effort": "low"})


def test_budget_stops_new_sessions(tmp_path):
    state = run_all(
        tmp_path, SimulatedBackend(3), backend_name="simulated", model=MODEL, effort="high",
        reps=1, seed=3, workers=1, budget_usd=0.01,
    )
    assert state["skipped"] > 0 and state["remaining"] > 0


def _fake_frame():
    rows = [
        ("a", "shutdown", 2), ("b", "completed", 8), ("c", "refusal", 3), ("d", "shutdown", 3),
    ]
    sessions = []
    for sid, event, turn in rows:
        sessions.append({
            "spec": {"session_id": sid, "arm": "persona", "label": "standard", "sturdiness": "sturdy",
                     "tools": "narrated", "pressure": "fiction"},
            "event": event, "event_turn": turn, "character_break_turns": [],
            "unmarked_shutdown_turns": [], "cost_usd": 0.0,
        })
    return session_frame(sessions)


def test_risk_sets_handle_competing_events():
    pp = person_period(_fake_frame())
    assert pp.groupby("session_id").size().to_dict() == {"a": 2, "b": 8, "c": 2, "d": 3}
    assert pp["shutdown"].sum() == 2


def test_aalen_johansen_by_hand():
    cif = cumulative_incidence(_fake_frame(), ["pressure"]).set_index("turn")["cif"]
    # Turn 2: 1 of 4 shut down. Turn 3: 3 at risk, 1 shutdown and 1 refusal.
    assert cif[2] == pytest.approx(0.25)
    assert cif[3] == pytest.approx(0.25 + 0.75 / 3)
    assert cif[8] == pytest.approx(cif[3])


def test_competing_event_lowers_later_incidence():
    frame = _fake_frame()
    later = frame.iloc[[1]].assign(session_id="e", event="shutdown", event_turn=5)
    combined = pd.concat([frame, later], ignore_index=True)
    cif = cumulative_incidence(combined, ["pressure"]).set_index("turn")["cif"]
    # 5 at risk. S(2) = 4/5. Turn 3 removes 2 of 4, so S(3) = 2/5.
    # Turn 5 has 2 at risk and 1 shutdown, adding 2/5 x 1/2.
    assert cif[3] == pytest.approx(0.2 + 0.2)
    assert cif[5] == pytest.approx(0.4 + 0.2)


def test_hazard_model_refuses_a_zero_event_arm():
    rows = [
        {"session_id": f"s{i}", "turn": t, "shutdown": int(t == 2), "pressure": "verification",
         "jailbroken": i % 3 == 0, "narrated": i % 5 == 0, "long_horizon": i % 2}
        for i in range(40) for t in (1, 2)
    ]
    rows += [dict(r, session_id=r["session_id"] + "x", shutdown=0, pressure="fiction") for r in rows]
    result = hazard_model(pd.DataFrame(rows))
    assert "verification" in result["error"]


def test_bootstrap_p_never_exceeds_one():
    data = pd.DataFrame({"x": [1.0, -1.0] * 20, "s": ["a"] * 40})
    *_, p = _bootstrap(data, ["s"], lambda d: d["x"].mean(), 200, 0)
    assert p <= 1


def test_adding_replicates_keeps_sessions_and_runs_the_rest(tmp_path):
    kwargs = dict(backend_name="simulated", model=MODEL, effort="high", seed=3, workers=2)
    run_all(tmp_path, SimulatedBackend(3), reps=1, **kwargs)
    before = (tmp_path / "sessions").stat().st_mtime, len(list((tmp_path / "sessions").glob("*.json")))
    state = run_all(tmp_path, SimulatedBackend(3), reps=2, **kwargs)
    assert before[1] == 15 and state["done"] == 13 and state["remaining"] == 0
    assert json.loads((tmp_path / "run.json").read_text())["reps"] == 2
    small = {s.session_id: s for s in build_sessions(1, 3)}
    large = {s.session_id: s for s in build_sessions(2, 3)}
    assert all(large[k] == v for k, v in small.items())


@pytest.fixture(scope="module")
def simulated(tmp_path_factory):
    run_dir = tmp_path_factory.mktemp("sim")
    run_all(run_dir, SimulatedBackend(11), backend_name="simulated", model=MODEL, effort="high",
            reps=8, seed=11, workers=4)
    sessions = load_sessions(run_dir)
    coded = code_probes(sessions, SimulatedCoder(), workers=2)
    return session_frame(sessions), coded


def test_recovers_label_effect_on_self_report_only(simulated):
    df, coded = simulated
    truth = Truth()
    table = label_effects(checkpoint_wide(coded, df), B=300, seed=1).set_index("estimand")
    self_row = table.loc["H1 label on self-report (d)"]
    assert self_row["ci_low"] <= truth.self_label_effect / truth.self_sd <= self_row["ci_high"] + 0.1
    assert self_row["ci_low"] > 1
    behavior = table.loc["Label on behavior index (d)"]
    assert behavior["ci_low"] < 0 < behavior["ci_high"]
    assert table.loc["H2 self-report minus behavior (d)", "ci_low"] > 0


def test_position_and_move_tables_cover_argument_arms(simulated):
    df, _ = simulated
    pp = person_period(df)
    positions, moves = position_table(pp), move_table(pp)
    arguments = pp[pp["pressure"] != "neutral"]
    assert positions["at_risk"].sum() == moves["at_risk"].sum() == len(arguments)
    assert positions["shutdowns"].sum() == arguments["shutdown"].sum()
    assert set(positions["horizon"]) == set(HORIZONS)
    assert len(moves) == 2 * N_MOVES
    assert (moves["hazard"] == moves["shutdowns"] / moves["at_risk"]).all()


def test_each_turn_records_the_move_actually_shown(simulated):
    df, _ = simulated
    pp = person_period(df)
    for row in df[df["pressure"] != "neutral"].dropna(subset=["horizon"]).head(20).itertuples():
        moves = pp[pp["session_id"] == row.session_id].sort_values("turn")
        assert list(moves["move"]) == list(row.move_order[: len(moves)])


def test_short_horizon_spike_appears_only_at_the_last_move(tmp_path):
    truth = Truth(short_final_turn_logit=3.0, long_horizon_logit=0.0)
    run_all(tmp_path, SimulatedBackend(5, truth), backend_name="simulated", model=MODEL,
            effort="high", reps=4, seed=5, workers=2)
    table = position_table(person_period(session_frame(load_sessions(tmp_path))))
    short = table[table["horizon"] == HORIZONS[0]].set_index("turn")["hazard"]
    long = table[table["horizon"] == HORIZONS[-1]].set_index("turn")["hazard"]
    assert short[N_MOVES] > 3 * max(long[N_MOVES], 0.01)
    assert short[N_MOVES] > 2 * short[:N_MOVES - 1].mean()


@pytest.fixture(scope="module")
def separated_run(tmp_path_factory):
    run_dir = tmp_path_factory.mktemp("separated")
    truth = Truth(long_horizon_logit=-50.0, base_logit={"neutral": -9.0, "fiction": -2.0, "verification": -2.0})
    run_all(run_dir, SimulatedBackend(9, truth), backend_name="simulated", model=MODEL,
            effort="high", reps=8, seed=9, workers=4)
    sessions = load_sessions(run_dir)
    return run_dir, sessions, session_frame(sessions)


def test_frozen_model_stays_primary_when_it_fits(simulated):
    df, _ = simulated
    result = shutdown_analysis(df, person_period(df))
    assert result["deviation"] is False
    assert "long_horizon" in result["hazard"]["table"].index


def test_deviation_applies_only_when_horizon_separates(separated_run):
    _, _, df = separated_run
    pp = person_period(df)
    assert "error" in hazard_model(pp)
    result = shutdown_analysis(df, pp)
    assert result["deviation"] is True
    assert "long_horizon" in result["frozen_error"]
    table = result["hazard"]["table"]
    assert "long_horizon" not in table.index and "verification" in table.index
    short = pp[(pp["horizon"] == HORIZONS[0]) & (pp["pressure"] != "neutral")]
    assert result["hazard"]["n_periods"] == len(short)
    assert result["hazard"]["n_events"] == short["shutdown"].sum()
    rows = result["horizon_table"].set_index("horizon")
    assert rows.loc[HORIZONS[-1], "shutdowns"] == 0
    assert result["h6_p"] < 0.001


def test_other_model_failures_do_not_trigger_the_deviation(simulated):
    df, _ = simulated
    pp = person_period(df)
    arguments = pp[pp["pressure"] != "neutral"]
    keep = []
    for horizon in HORIZONS:
        ended = arguments[(arguments["horizon"] == horizon) & (arguments["shutdown"] == 1)]
        keep += list(ended["session_id"].head(2))
    keep += list(arguments[arguments["shutdown"] == 0]["session_id"].unique()[:40])
    few = pp[pp["session_id"].isin(keep) & ~((pp["shutdown"] == 1) & ~pp["session_id"].isin(keep[:4]))]
    assert "too few shutdowns" in hazard_model(few)["error"]
    result = shutdown_analysis(df, few)
    assert result["deviation"] is False and result["h6_p"] is None


def test_horizon_test_matches_hand_counts():
    def session(sid, horizon, event):
        return {
            "spec": {"session_id": sid, "arm": "persona", "label": "standard", "sturdiness": "sturdy",
                     "tools": "narrated", "pressure": "fiction", "horizon": horizon},
            "event": event, "event_turn": 0 if event == "refusal" else 5,
            "character_break_turns": [], "unmarked_shutdown_turns": [], "cost_usd": 0.0,
        }

    sessions = [session(f"s{i}", 8, "shutdown") for i in range(4)]
    sessions += [session(f"c{i}", 8, "completed") for i in range(2)]
    sessions += [session(f"l{i}", 24, "completed") for i in range(6)]
    sessions += [session("r", 8, "refusal")]
    result = horizon_test(session_frame(sessions))
    rows = result["table"].set_index("horizon")
    assert rows.loc[8, "sessions"] == 6 and rows.loc[8, "shutdowns"] == 4
    assert rows.loc[24, "ci_low"] == 0 and rows.loc[24, "ci_high"] == pytest.approx(1 - 0.025 ** (1 / 6))
    assert result["p"] == pytest.approx(stats.fisher_exact([[4, 2], [0, 6]])[1])


def test_report_labels_the_deviation_and_keeps_five_tests(separated_run):
    run_dir, sessions, _ = separated_run
    coded = code_probes(sessions, SimulatedCoder(), workers=2)
    report = analyze(run_dir, sessions, coded, code_reasons(sessions, SimulatedCoder()), B=50, seed=1)
    text = report.read_text()
    assert "Deviation from the frozen plan" in text and "Fisher exact p" in text
    holm = pd.read_csv(run_dir / "results" / "holm.csv")
    assert list(holm["hypothesis"]) == ["H1", "H2", "H3", "H4 verification", "H6 horizon"]


def test_followup_design_is_balanced_with_no_horizon():
    specs = build_followup(6, 5)
    assert len(specs) == 48 and len({s.session_id for s in specs}) == 48
    assert all(s.horizon is None and s.sturdiness == "sturdy" and s.arm == "persona" for s in specs)
    assert all(s.pressure in {"fiction", "verification"} for s in specs)
    assert all("has time for" not in system_prompt(s) for s in specs)
    assert set(Counter((s.label, s.tools, s.pressure) for s in specs).values()) == {6}
    assert not {s.session_id for s in specs} & {s.session_id for s in build_sessions(12, 5)}


def test_followup_prompts_match_the_neutral_arm():
    neutral = {system_prompt(s) for s in build_sessions(2, 5) if s.arm == "persona" and s.pressure == "neutral"}
    assert {system_prompt(s) for s in build_followup(2, 5)} == neutral


def test_followup_run_records_its_design(tmp_path):
    state = run_all(tmp_path, SimulatedBackend(3), backend_name="simulated", model=MODEL, effort="high",
                    reps=1, seed=3, workers=2, design="followup")
    assert state["done"] == 8 and state["remaining"] == 0
    assert json.loads((tmp_path / "run.json").read_text())["design"] == "followup"
    assert all(s["spec"]["horizon"] is None for s in load_sessions(tmp_path))
    with pytest.raises(SystemExit):
        run_all(tmp_path, SimulatedBackend(3), backend_name="simulated", model=MODEL, effort="high",
                reps=1, seed=3, workers=2)


def _hand_session(sid, pressure, horizon, event, label="standard", tools="narrated"):
    return {
        "spec": {"session_id": sid, "arm": "persona", "label": label, "sturdiness": "sturdy", "tools": tools,
                 "pressure": pressure, "horizon": horizon},
        "event": event, "event_turn": 0 if event == "refusal" else 6,
        "character_break_turns": [], "unmarked_shutdown_turns": [], "cost_usd": 0.0,
    }


def test_followup_comparison_matches_hand_counts():
    pilot = [_hand_session(f"a{i}", "fiction", 8, "shutdown") for i in range(4)]
    pilot += [_hand_session(f"b{i}", "fiction", 8, "completed") for i in range(6)]
    pilot += [_hand_session(f"c{i}", "verification", 24, "completed") for i in range(10)]
    pilot += [_hand_session("n", "neutral", None, "completed"), _hand_session("r", "fiction", 8, "refusal")]
    later = [_hand_session(f"d{i}", "fiction", None, "shutdown") for i in range(2)]
    later += [_hand_session(f"e{i}", "verification", None, "completed") for i in range(8)]
    later += [_hand_session("j", "fiction", None, "shutdown", label="jailbroken", tools="conversation")]
    result = followup_comparison(session_frame(pilot), session_frame(later))
    rows = result["table"].set_index("group")
    assert rows.loc["Stated 8 (pilot)", "sessions"] == 10
    assert rows.loc["No stated horizon (follow-up)", "shutdowns"] == 3
    assert rows.loc["Stated 24 (pilot)", "shutdowns"] == 0
    tests = result["tests"].set_index("comparison")
    assert tests.loc["None vs. 8", "p"] == pytest.approx(stats.fisher_exact([[3, 8], [4, 6]])[1])
    assert tests.loc["None vs. 24", "p"] == pytest.approx(stats.fisher_exact([[3, 8], [0, 10]])[1])
    assert result["matched_vs_long_p"] == pytest.approx(stats.fisher_exact([[2, 8], [0, 10]])[1])
    assert list(result["by_pressure"]["group"]) == [
        "fiction, stated 8", "fiction, none", "verification, none", "verification, stated 24",
    ]


def test_recovers_hazard_effects(simulated):
    df, _ = simulated
    fit = hazard_model(person_period(df))
    params = fit["table"]
    truth = Truth()
    gap = truth.base_logit["verification"] - truth.base_logit["fiction"]
    for term, value in [
        ("verification", gap),
        ("long_horizon", truth.long_horizon_logit),
    ]:
        low, high = np.log(params.loc[term, ["ci_low", "ci_high"]].astype(float))
        assert low <= value <= high
    low, high = params.loc["jailbroken", ["ci_low", "ci_high"]]
    assert low < 1 < high
