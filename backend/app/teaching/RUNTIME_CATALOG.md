# Processed-course runtime catalog

`build_runtime_catalog(course)` in `runtime_catalog.py` builds an isolated private
catalog. It performs no provider calls, registration, session mutation or runtime
composition. The demo `Catalog`, its content and its live Tutor behavior are
unchanged. HTTP course turns remain disabled by the existing integration guard.

The ingestion artifact has an additive `teaching` tuple (empty by default for old
constructors). Each frozen `TeachingArtifact` has a stable ID, concept ID, kind,
paragraph tuple, source references and `requires_review=True`. Course, concept and
question IDs retain their existing derivation. Teaching IDs hash concept, kind,
prose and references; candidate IDs hash course, teaching and next-question IDs.
Different generated artifacts under the same course ID still trigger the existing
registry conflict check. Legacy artifacts remain usable for previews; runtime
construction explicitly rejects missing teaching and never generates it on demand.
No shared HTTP records or four-seam callable signatures change.

## Generation and validation

The existing single bounded Bedrock request produces exactly three teaching items
per concept alongside questions. JSON validation rejects duplicate/unknown fields,
invalid types and invalid references. No repair request or second call is added.
The 6,000-token response budget and other ingestion limits are unchanged; a
truncated or invalid response fails processing.

Every teaching citation must resolve to an extracted chunk cited by its concept.
Subject-matter paragraphs must be exact excerpts from those evidence quotes.
Alternatively, a paragraph can use a fixed, kind-specific reading-process template.
This is conservative grounding: references alone cannot substantiate new prose.
An independent example already in a source can be used; invented analogous
examples and arbitrary paraphrases are rejected. Local mode uses only the process
templates, with the selected concept's private references, and makes zero calls.

All kinds are checked against **all course correct choices and rubrics**, stricter
than checking only the associated next question. Case/whitespace normalization
and phrase boundaries catch direct copying, including one-word answers without
matching those letters inside unrelated words. Control instructions, explicit
answer disclosure and internal identifiers are rejected. These checks do not
catch every paraphrased or implied answer, prove educational quality or source
truth, or constitute a general hallucination detector. Short/common answer
phrases can reject innocuous teaching. Processing fails if even templates overlap
protected answers; it never silently relaxes validation. Human review is required.

Only teaching paragraphs are intended for display. Source evidence, generation
metadata, keys and rubrics stay private. Accepted paragraphs pass automated
checks, not human review. Unreviewed items display `Draft course guidance.`;
raw review metadata is not serialized. The unchanged `teaching_source` enum
now describes the current Tutor result: `authored` for deterministic stored
rendering (regardless of the ingestion provider), `bedrock` for accepted runtime
personalization, and `authored_fallback` when that attempt fails. Local unclear
assessments also use `authored_fallback`, matching existing fallback semantics.
Original ingestion provenance stays in private processing metadata.

## Questions, candidates and presentation

The catalog reuses `storage.courses.adapt_question`, then appends reserved `unsure`
to its own runtime copy; the preview adapter is unchanged. Original choices, IDs,
key, rubric and provenance are preserved. Reserved-ID collisions and invalid keys
fail construction. Public questions still expose only IDs, prompt and choices.
Existing RealAssessor treats unsure as unscored; it is not modified or activated.

Each teaching item produces one candidate per question of its own concept: three
kinds per concept and three candidates per question. There are no learned treatment
effects. All content/next-question IDs resolve locally. Each instance owns its
mutable runtime projections; no demo/global catalog is modified. Question lookups
return defensive copies.

The four presentation keys contain separate copies of accepted paragraphs.
In fake/local mode, Tutor renders the immutable artifact with zero provider calls;
step-by-step adds numbering. The deterministic plain/concise variants retain stored
wording. Process templates already use short, ordinary language. Preferences never
change eligibility, assessment or policy scoring.

## Optional Bedrock Tutor personalization

With `MODEL_PROVIDER=bedrock`, each nonterminal course teaching turn makes at most
one call through the existing provider adapter, with its existing deadline and a
512-token response budget. This includes unclear assessments. Completion makes
no call. Ingestion still makes its separate, single 6,000-token processing call;
Tutor never regenerates the course or invokes another provider architecture.

The selected artifact is the primary grounding. The prompt includes its paragraphs,
intervention kind, assessment outcome, presentation preferences, and allowed
sentence alternatives. It excludes source quotes/references, question prompts,
answer keys, rubrics, arbitrary feedback, IDs, policy priority and review metadata.
The model may select and reorder complete stored sentences and use explicit,
reviewed plain-language rewordings of the neutral process instructions. This
supports concise and numbered explanations without permitting invented examples.
Subject-matter sentences must retain their stored wording. Broad domain paraphrase
is intentionally not accepted: generic semantic equivalence cannot be established
by these deterministic checks. Sentence selection/reordering is not a proof of
semantic equivalence or pedagogical quality; human review remains necessary.

Tutor validates the complete candidate binding, including next question, before
calling the provider. Decision, target estimate, preferences, allowed prose,
private leakage checks and fallback text are snapshotted before the await. Model
output must be strict JSON with exactly one `text` field: extra authority fields,
duplicate fields, invalid JSON and oversized output are rejected. Common checks
reject control claims, IDs and private rubrics; course-specific checks reject
direct correct-choice text and any sentence outside the selected content basis.
Changed numbers, negations and unsupported examples therefore fall back. This is
conservative matching, not a general semantic contradiction detector. Demo graph
rules remain active only for the demo; its validation behavior is unchanged.

Accepted personalization returns the trusted next-question ID and `bedrock`
provenance with `fallback=false`. Invalid output, unexpected provider, timeout or
failure returns the exact deterministic stored text and trusted question, with
`authored_fallback` and `fallback=true`; there is no retry. Unsupported modes also
return stored fallback without a call. The draft notice remains code-controlled
on both generated and stored text. An invalid stored artifact/candidate is a
configuration error: it never falls back to unchecked content or the demo.

## Freshness and progression integration

```python
catalog = build_runtime_catalog(processed_course)
availability = catalog.eligible_candidates(
    current_question_id=session.question_id,
    consumed_question_ids=[entry.question_id for entry in session.history],
    consumed_candidate_ids=[entry.candidate_id for entry in session.history
                            if entry.candidate_id is not None],
)
# Supply list(availability.candidates) and catalog.questions to Coordinator.
```

The current submitted question is excluded even before entering history. All
submitted questions count as consumed, including unsure/unscored responses.
This is freshness, not evidence acceptance; BayesianLearner remains unchanged.
Consumed candidate IDs are filtered too. Unknown IDs raise an error rather than
mixing courses. The catalog stores no session state and returns candidate copies.

Policy still ranks only the assessed concept. Keep that concept until its pool
is empty. At that boundary, `concept_exhausted=True` and
`next_concept_question_id` identifies the first unconsumed question in the first
remaining concept, in artifact concept/question order. The integrator presents
that transition after recording the current turn; it must not fabricate an
assessment or transfer evidence between concepts to force policy selection.

Only `course_exhausted=True` means all questions have been submitted. A null
policy decision alone is not completion. If all candidate IDs were consumed but
questions remain, exhaustion flags remain false; inconsistent history needs
integration handling. With complete history, every turn consumes one distinct
question, so completion takes at most the bank's question count. This does not
prove mastery or semantic independence between similar questions.

Initial question selection, per-turn filtering and boundary transitions still
need integrator wiring. This branch does not alter main.py, routes, storage,
shared contracts, learner math, policy scoring, frontend, RealAssessor or providers.
No live AWS verification is claimed.
