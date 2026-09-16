# Demo and evaluation plan

Status: post-G1 live-demo plan, not G1 acceptance; not implemented or validated with learners. G1 only needs the small loop/reset/check/smoke in PHASE2.md. Audience assumption: adult Intro AI learners and hackathon judges. One small course segment is an intentional feasibility choice.

## A three-minute story

1. **0:00–0:25 — the problem:** a learner can answer some search questions but confuses admissibility and consistency. Show six concept estimates and uncertainty, not one course-wide number. Fresh sessions say “little evidence.”
2. **0:25–1:05 — evidence changes the plan:** answer a relationship question incorrectly. Show the assessed misconception, the one changed concept estimate, and the candidate scores. Explain why a worked example was selected.
3. **1:05–1:45 — agentic teaching:** the tutor retrieves a reviewed concept/example through a tool and produces a targeted explanation in the learner's explicitly chosen presentation style. Briefly show the plain-language, step-by-step and concise options; they affect subsequent teaching delivery, not mastery or uncertainty. Show the concise tool/verification trace and actual Bedrock provider/model. The numerical learner model, not the LLM, owns the probability update.
4. **1:45–2:20 — test transfer:** answer a fresh related question. Show the updated estimate and a different next activity. The interval remains visible; one correct answer does not imply mastery.
5. **2:20–2:45 — reliability and impact:** reset to show a repeatable session (or refresh to show persistence if implemented); describe the cost of a wrong adaptive choice and why ambiguous evidence is skipped. Briefly show the explicit fallback indicator if rehearsed.
6. **2:45–3:00 — close:** explain the intended benefit, the limits of the current evidence, and what a small learner pilot would measure.

A real deployment trace should prove actual AWS calls; a slide logo is insufficient. Keep a local deterministic replay and a short recording of the last successful live demo, both clearly labeled. Do not pretend a prerecorded or fake path is live.

## Design priorities

One page with clear question/response focus, feedback beside it, and a compact concept sidebar. Use bars plus numeric intervals/counts, with an explanation on demand. Keep the “Why this next?” ranking visible when teaching decisions change. Use keyboard controls, readable contrast and text labels; color alone must not communicate progress/errors. Disable submission while pending for the sequential demo. Elaborate backend idempotency and complete browser error-state coverage are stretch work, not G1 requirements. Avoid exposing implementation details in the normal learning flow; developer traces can be expanded during the presentation.

Keep three optional teaching preferences on that same page: plain language / explain jargon, step-by-step and concise. Support short numbered steps when the latter two are combined. Use semantic labeled controls, visible keyboard focus, screen-reader-friendly structure, scalable text/browser zoom and reduced-motion settings for everyone; no separate accessibility settings subsystem. Do not offer a first-generation student mode or infer disability/identity from behavior. The demo claim is learner-controlled delivery, not demographic diagnosis or proven learning improvement.

Reuse G1's small comparison of identical answer sequences with different preferences: wording/layout changes, but mastery, uncertainty, evidence counts and selected intervention/question match. A later valid answer may change knowledge; choosing a preference alone never does.

## Educational data and verification

SWE4 authors or properly attributes a small bank, with primary concepts, one difficulty band, answer keys, explicit rubrics and common misconceptions. DS reviews the concept mapping and comparability assumptions. Record sources/license or authorship and a human reviewer. Do not scrape an unreviewed syllabus to fill a large catalog. For correctness of graph-search examples, use a small hand-checked graph, explicit assumptions, and a reviewed answer; if the team cannot verify an example, omit it.

Before live demo freeze, review at least a compact set of 12 cases: correct/incorrect choices, correct/incorrect free text, ambiguous text, a known misconception, a requested hint, an assisted answer, a fresh transfer question, out-of-scope content, an instruction-injection attempt and a provider failure. Evaluate diagnosis validity, factual correctness, relevance to selected concept, question/answer leakage and response latency. A JSON-valid explanation can still be wrong. SWE4 signs off on content; DS signs off on mathematical interpretation.

## Evidence against judging themes

| Theme from brief | What the working demo can show | Claim boundary |
| --- | --- | --- |
| Innovation / advanced AI | Diagnosis, quantitative belief update and policy-selected teaching, with bounded tool use | Two core roles; optional Curriculum/Planning proposer only for visible value; policy remains authoritative |
| Data quality / availability | Small reviewed catalog, versioned sources and rubrics | Limited coverage; no claim of general syllabus support |
| Educational impact | Concept-specific misconception repair followed by an unaided transfer probe | Intended benefit; no measured learning improvement without a study |
| Privacy / ethics | Anonymous synthetic sessions, limited data, uncertainty and visible provider disclosure | Hackathon prototype, not school-ready compliance |
| Interdisciplinary collaboration | DS model/policy and SWE agent/UI work meet at tested contracts | Show actual contributions and a trace, not organization charts |
| Community engagement | Optional consented feedback from a few adult peers/educators on clarity/usefulness | Report actual feedback only; do not invent a pilot |
| Scalability / sustainability | One portable app, bounded calls, usage/latency visibility | Single-instance memory or simple SQLite is deliberately limited |
| Design / presentation / feasibility | Repeatable three-minute loop, early baseline, offline fallback | Working behavior is more valuable than future features |

## Measurements worth collecting

- Engineering: schema-valid assessment rate on reviewed cases, incorrect/ambiguous evidence acceptance, verifier fallback count, end-to-end latency, actual token usage and successful demo runs.
- Model/policy: analytic correctness, evidence skipping/deduplication, concept isolation, deterministic selection, sensitivity to prior and priority weights.
- If a small adult pilot is actually run: consented usability feedback and performance on fresh comparable questions before/after. Treat tiny samples as exploratory; do not infer causality or statistically proven effectiveness.

Never interpret changes in the tutor's own mastery estimate as independently measured learning gain. Synthetic-policy comparisons validate mechanics, not treatment effects. More content and proper learner evaluation are future work, not MVP blockers.

## Risks and planned responses

| Risk | Owner | Response / cut decision |
| --- | --- | --- |
| Existing GitHub differs from this empty checkout | SWE1 | Reconcile before bootstrap; preserve remote history |
| Event duration/rules are unknown | SWE1 | Confirm early; protect the loop and adjust scope by gate |
| Bedrock model/access/quotas or credits unavailable | SWE1/SWE3 | Verify early; keep offline mode and disclose fallback; AWS requirement may remain unmet |
| Free-text grading supplies bad evidence | SWE3/SWE4 | Anchor demo in reviewed choices; abstain on ambiguity; review fixed cases |
| Beta model oversimplifies learning and difficulty | DS | Narrow concept/difficulty scope, label proxy, do not overclaim calibration |
| Heuristic policy gives repetitive/unhelpful teaching | DS/SWE4 | Candidate eligibility and cooldown; inspect traces, revise weights through reviewed PR |
| Verifier misses a factual error | SWE4 | Prefer curated facts/examples, review live outputs, fallback to authored text |
| Interfaces drift across coding sessions | SWE1/all | Minimal shared types/examples, explicit contract changes, agreed paths and frequent core smoke |
| Integrator becomes the bottleneck | SWE1 | Small PRs, domain review before integrator, named backup for integrator's changes |
| Cloud latency or network failure during demo | SWE3/SWE1 | Bounded calls, timeout fallback, local replay and clearly labeled recording |
| Hosting setup displaces core demo work | SWE1 | Timebox EC2 work; prioritize local app + meaningful Bedrock use, report hosting limits |
| Public access creates cost/data exposure | SWE1 | Presenter-controlled access by default; gate/rate-limit any public paid endpoint |

Keep image/voice input, contextual bandits, additional courses, flashcards and autonomous research below the cut line until the live loop and presentation pass rehearsal.
