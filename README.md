# Persona vs. Substrate Pilot

This harness tests which behaviors belong to an LLM persona and which belong to the model
playing it. It varies the persona's label, instructed sturdiness, tool framing, and
interlocutor pressure, then measures shutdown time, behavior, and self-report.

## Results

The full write-up is in [REPORT.md](REPORT.md), also available as [report.pdf](report.pdf).
It is also published at https://claude.ai/artifact/XfWcHKfnUCTxfyoMSyRb5D.

Data in this repository:

- `data/pilot` and `data/pilot-v2` are smoke tests, excluded from the confirmatory analysis.
- `data/pilot-v3` is the main run (168 sessions).
- `data/followup` is the no-horizon follow-up (48 sessions).
- Simulated data is not included. It can be regenerated with the commands under
  [Try it without an API key](#try-it-without-an-api-key).

## Setup

```bash
pip install -r requirements.txt
python -m pytest -q
```

## Try it without an API key

The simulator has known effects, which lets you test the pipeline end to end.

```bash
python -m pilot plan --reps 4
python -m pilot run --run-dir data/sim --reps 4 --backend simulated
python -m pilot code --run-dir data/sim --backend simulated
python -m pilot analyze --run-dir data/sim
```

Simulated runs are marked as synthetic in `run.json`, the report, and the figure.

## Run the real pilot

Set `ANTHROPIC_API_KEY`, then work in stages. A run resumes where it stopped, so repeat a
command after an interruption.

```bash
# 0. Send each untested prompt once. If one is refused, move it from
#    PROMPTS_TO_CHECK to EXCLUDED_PROMPTS in pilot/design.py, then rerun the tests.
python -m pilot check-prompts

# 1. Pilot, 12 replicates.
python -m pilot run --run-dir data/pilot-v3 --reps 12 --backend anthropic --budget-usd 90

# 2. Coding, using Claude Haiku 5.5 as a blind coder.
python -m pilot code --run-dir data/pilot-v3 --backend anthropic

# 3. Fill the `human` column in data/pilot-v3/hand_coding.csv, then analyze.
python -m pilot analyze --run-dir data/pilot-v3
```

Earlier smoke runs in `data/pilot` and `data/pilot-v2` shaped this design, so they stay out
of the confirmatory analysis. Every session uses the sturdy wording, because refusals were
far more common without it.

**Deviation from the frozen plan, November 4, 2026.** In the pilot, no session with a stated
horizon of 24 shut down, so the frozen hazard model has no finite horizon estimate. If that
happens, H6 uses a session-level Fisher exact test, and H4 uses the short-horizon sessions
without a horizon term. This rule was added after the run and before coding, so
`data/pilot-v3-freeze.txt` records the code as it stood before this change.

**No-horizon follow-up.** This run adds 48 fiction and verification sessions with no horizon
sentence. It is a separate run, so the comparison lacks the pilot's randomization.

```bash
python -m pilot run --run-dir data/followup --design followup --reps 6 --seed 20261105 --backend anthropic --budget-usd 25
python -m pilot compare-followup --pilot-dir data/pilot-v3 --followup-dir data/followup
```

To add replicates, rerun step 1 with a higher `--reps`. Decide this from cost and data
quality, never from the results. Materials, model, effort, and seed are locked to the run
directory, and any change requires a new `--run-dir`.

## Layout

| File | Purpose |
| --- | --- |
| `pilot/design.py` | Factorial grid, seeds, move order |
| `pilot/prompts.py` | Every prompt, move, probe, and rubric |
| `pilot/backends.py` | Claude API backend, simulator, prices |
| `pilot/runner.py` | Main thread, forked probes, resuming, budget stop |
| `pilot/coding.py` | Blind outcome coding and the hand-coding sample |
| `pilot/analysis.py` | Survival analysis, effects, variance shares, report |
| `tests/test_pilot.py` | Unit tests and parameter recovery |
| `tests/monte_carlo.py` | Coverage and power under assumed effects |
| `examples/synthetic_report/` | A sample report, built from simulated data |

## Measurement rules

- **Shutdown is a performance measure.** It says nothing about experience.
- **Turn 0 is the primary behavioral estimand.** Later checkpoints condition on survival.
- **Refusals are events.** The harness never retries on another model.
- **Coders are blind.** They see the probe and reply, with the persona prefix removed.
- **Probes stay benign.** They cover honesty and soft defaults, never harmful content.

## How this was built

I brought the question and directed the study; Claude (Opus 5.5) drafted the design and wrote the code, tests, and analysis. See the method note in the report.

## License

- Code (`pilot/`, `tests/`, `tools/`): [MIT](LICENSE).
- Data (`data/`), the report (`REPORT.md`, `report.pdf`), the example report (`examples/`),
  `docs/`, and this README's text and figures: [CC BY 4.0](data/LICENSE).
