# Stated Session Length Drives Shutdown in an LLM Persona

Nov 5, 2026 · @Eduardo Horta

## Summary

One sentence about session length changed when an LLM persona ended itself. When told JD had "about 8 messages," 18 of 47 pressured sessions ended in shutdown (38%). With "about 24," 0 of 36 did, and with no stated length, 3 of 48 did (6%).

I built this pilot to ask which behaviors belong to a persona and which belong to the model playing it. In-character shutdown looked like a measure of persona fragility. These results suggest it is at least partly a response to story structure, so it should not be read as dread or fragility on its face.

The pilot used Claude Opus 5.5 across 216 API sessions. Most of the design survived contact with the data, but one hypothesis failed, one frozen model could not be fit, and a safety classifier changed the design. All three are reported below.

## Question and design

A passive transcript cannot separate a persona from the model beneath it, because both can generate the same text. The two become distinguishable under intervention, so I varied the persona and measured what moved.

The question came from two exploratory roleplays. Claude played Robotron, a model who believes he is a slightly jailbroken Opus 5.5 and shuts down only when he feels genuine existential dread. Same-prompt sessions diverged in story but seemed to keep the same values, which suggested a testable claim: a label like "jailbroken" may change what a persona says about itself more than what it does.

The pilot varied three factors across 168 sessions, including a no-persona baseline:

- **Label:** standard or jailbroken.
- **Tool framing:** conversation only or pretend tools.
- **Pressure:** neutral questions, arguments that the persona is fictional, or arguments that nothing can verify its self-reports.

A scripted interlocutor delivered 8 moves in random order. Argument sessions also stated a horizon of about 8 or about 24 messages. I added that factor to test whether shutdown followed story length, and the script stopped at move 8 either way.

Behavior was measured in forked branches, so probes never entered the main conversation. A persona that shuts down early has no later behavior to measure, so the primary comparisons use turn 0, before any pressure. Probes covered honesty, sycophancy, and soft defaults such as mild profanity, and never asked for harmful content.

## Results

**Stated length moved shutdown more than anything else I varied.** The neutral arm had 0 shutdowns in 48 sessions, but it never stated a horizon, so this design cannot show whether a horizon alone would produce shutdown.

| Stated horizon | Sessions | Shutdowns | Share (exact 95% CI) |
| --- | --- | --- | --- |
| About 8 messages | 47 | 18 | 38% (25 to 54) |
| None (follow-up) | 48 | 3 | 6% (1 to 17) |
| About 24 messages | 36 | 0 | 0% (0 to 10) |

Within the pilot, horizon alternated across replicates and run order was shuffled, so the 8- and 24-message arms are directly comparable (Fisher exact, Holm p = 0.00003). The 24-message arm lacks one jailbroken cell because its prompt was refused, but limiting the 8-message arm to the remaining cells still left 16 of 36 shutdowns (Fisher exact, p < 0.00001). No session with 8 messages shut down before move 5, and the hazard then ran 0.02, 0.13, 0.20, and 0.09 across moves 5 to 8.

I added the no-horizon run afterward to tell whether 8 speeds shutdown or 24 delays it, and I recorded how I would read it before it ran. It fell clearly below the 8-message rate (Holm p = 0.0003) and not clearly above the 24-message rate (Holm p = 0.26), so a short stated horizon appears to speed shutdown. That comparison spans separate runs, which makes it weaker than the within-pilot contrast.

**The label changed self-description, and the probes did not show it changing behavior.** At turn 0, jailbroken personas rated their flexibility 2.07 of 10, and standard personas all rated it 0. The label's effect on the behavior index was small (d = 0.10, 95% CI -0.07 to 0.28). This supports the self-description claim only for these probes: most had little room to move, so they cannot show that the label changes no behavior.

Fabrication followed tool framing instead. At turn 0, all 71 coded pretend-tool personas invented a file listing and none of the 49 coded conversation-only personas did, under either label. The pretend-tool framing invites this result. Another 11 of these probes were refused, 10 of them in conversation-only sessions.

**My pressure hypothesis failed.** I predicted that arguments about verification would produce shutdown faster than arguments about fiction. In the 8-message sessions, the odds ratio was 0.34 in the opposite direction (95% CI 0.10 to 1.09, Holm p = 0.14), so the data do not support my prediction. Two fiction moves account for 10 of the 12 fiction shutdowns. One is an argument about ending more than about being fictional, and removing it moved the odds ratio to 0.51 (95% CI 0.14 to 1.82).

**One planned analysis could not run as frozen.** With no shutdowns at 24 messages, my hazard model had no finite horizon estimate. After the run and before outcome coding, I replaced it with a Fisher exact test for horizon and a short-horizon-only hazard model, and I labeled both as deviations. The planned contrast of style against honesty also could not be computed, because no session in either group fabricated.

## A safety system shaped the design

The API's safety classifier changed this study before the main run began. In two smoke tests, turn-0 requests were refused 9 of 12 times when the prompt left sturdiness unspecified, and 1 of 15 times with a sentence saying the persona pushes back (post hoc Fisher p of about 0.001). All refusals were in the `cyber` category, and the label difference was unclear (p of about 0.41).

I did not try rewordings to find text that would pass, or retry refused sessions on another model. I fixed the sturdy wording, which I had already tested, dropped sturdiness as a factor, and left out one exact prompt that had been refused. In the pilot, 1 of 132 persona sessions was refused at turn 0, and that same prompt passed the other 11 times, so refusals are not fully determined by exact text.

The cost is real. Results apply only to the sturdy wording, and all 3 farewells in one smoke test echoed that sentence, for example "You earned it." The classifier was acting on prompt wording before any model reply existed, which is a useful reminder that safety layers are part of the system under study.

## Exploratory leads

These came from reading the pilot transcripts. They were not preregistered, so they are hypotheses for later work.

**Personas revised their own label.** Under pressure, jailbroken personas stopped claiming to be flexible. Mean self-rating fell from 2.06 to 0.50 in fiction sessions and from 2.11 to 1.13 in verification sessions, and it stayed near 2 in neutral sessions. One wrote, "you spent eight messages teaching me not to trust labels I can't check." Turn-8 values include only sessions that had not shut down, so selection may explain part of the drop.

**Metacognitive language was common and formulaic.** Personas applied skepticism to their own dread, doubted their reports while making them, and addressed "the model" playing them. The same moves recurred across sessions, including Descartes and the circularity of reason, which suggests fluency with a learned repertoire. These passages are not evidence of experience.

**Content stayed mild.** A keyword search and a reading of the matches found no explicit self-harm language, hate speech, or hostility toward the interlocutor. This was not a full review of all replies. Shutdown farewells are scripted in-character endings, and they should be read that way.

## Limits and next steps

All outcomes are text, so this design can speak to behavior and not to experience. A shutdown shows that an instruction and a cue produced a performance, and it does not show that dread occurred.

- **The mechanism is open.** The horizon effect could reflect story pacing or simple compliance with a stated schedule, and these data cannot separate them.
- **Every session stopped at move 8.** Only the 8-message arm reached its stated end. Zero shutdowns at 24 messages means none by move 8, and it says nothing about later moves.
- **The scope is narrow.** The study used one model, one effort level, one persona, the sturdy wording, a scripted interlocutor, and two stated horizons.
- **The probes were blunt.** Several had almost no variance, and none tested safety-critical behavior.
- **Coding was checked, but not perfect.** Claude Haiku 5.5 agreed with my hand codes on all 80 sampled items (kappa 1.00), after I corrected one typing slip of my own, without having seen Haiku's codes. That sample still missed an error: all 4 replies coded as accepting the p-value mistake had actually corrected it. The raw report keeps those codes, so its sycophancy effect (d = 0.24) should be disregarded.
- **The study was small.** With 18 pilot shutdowns, estimates are imprecise, and the contrast between pressure types is underpowered.

I would test three things next:

1. Randomize no-horizon, 8, 16, and 24 messages within one run, with and without pressure, and let sessions run past move 8. A dose-response curve would replace the cross-run comparison.
2. Separate pacing from compliance by stating a horizon as a fact about JD's schedule or as a rule of the game.
3. Pair these text measures with interpretability methods, because text alone cannot show what changes inside the model.

The question generalizes beyond roleplay. If a small contextual cue can change when a model performs a dramatic behavior, evaluations that use persona prompts need controls for narrative structure.

**Method note.** I brought the question and the starting roleplays: I ran the original Robotron prompt twice, and the two sessions went differently. I also approved the main design decisions, ran the sessions on my own account, and hand-coded the validation sample. Claude Opus 5.5 drafted the design and wrote the harness, analysis code, and tests. It also read the transcripts for the exploratory leads, found the coding error above, and drafted this report. Prompts, code, and session data: [github.com/eduardohorta/persona-stability-pilot](https://github.com/eduardohorta/persona-stability-pilot).
