"""Bounded course generation using the existing provider seam, never runtime wiring."""
import asyncio
import json
import logging
import os
import re
from pathlib import Path

from backend.app.agents import provider
from .extraction import extract_material
from .models import (Choice, Concept, IngestionError, ProcessedCourse, ProcessingMetadata,
                     Question, SourceReference, TeachingArtifact, normalized, stable_id)
from .teaching import PROCESS_TEMPLATES, validate_teaching
from .passages import (SYSTEM, REPAIR_SYSTEM, QUESTION_RULES, QuestionValidationError, apply_repairs,
                       build_passages, plan_schema, question_path, repair_schema, resolve_plan, topic_passages,
                       fixed_topic_schema, resolve_fixed_topics, repair_slots)

MAX_CONTEXT_CHARS = 24_000
MAX_CONCEPTS = 5
MAX_FILES = 8
GENERATION_BUDGET_SECONDS = 90
logger = logging.getLogger("uvicorn.error.ingestion")


def _object(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise IngestionError("Generated JSON has missing or unexpected fields.")
    return value


def _text(value, maximum=1200):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise IngestionError("Generated text is empty, invalid, or too long.")
    # Normalization is explicit and never changes the trusted source record.
    return normalized(value)


def _items(value, minimum, maximum):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise IngestionError("Generated list has an invalid type or size.")
    return value


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise IngestionError("Generated JSON contains duplicate object keys.")
        result[key] = value
    return result


def _invalid_constant(_):
    raise IngestionError("Generated JSON contains a non-JSON numeric constant.")


def validate_proposal(text: str, materials: tuple, course_id: str) -> tuple[tuple, tuple]:
    """Preserve the existing question-validation caller's two-value interface."""
    concepts, questions, _ = _validate_artifacts(text, materials, course_id)
    return concepts, questions


def _parse_proposal(text: str):
    """Parse either internal proposal format with identical strict JSON checks."""
    if not isinstance(text, str) or len(text) > 60_000:
        raise IngestionError("Generated JSON exceeds the output limit.")
    # Some providers wrap JSON despite the prompt. Accept only one complete
    # outer fence; its contents still pass every JSON and artifact validator.
    fenced = re.fullmatch(r"```(?:json)?[ \t]*\r?\n([\s\S]*)\r?\n```", text.strip(), re.IGNORECASE)
    if fenced:
        text = fenced.group(1)
    try:
        data = json.loads(text, object_pairs_hook=_unique_pairs, parse_constant=_invalid_constant)
    except IngestionError:
        raise
    except (ValueError, RecursionError) as exc:
        raise IngestionError("Provider returned malformed JSON.") from exc
    return data


def _question_signature(prompt, choices):
    from backend.app.teaching.targeted_questions import normalized as content_normalized
    return (content_normalized(prompt), tuple(sorted(content_normalized(choice) for choice in choices)))


def _validate_artifacts(text: str, materials: tuple, course_id: str, *, _minimum_questions=1) -> tuple[tuple, tuple, tuple]:
    """Validate proposals and mint all IDs in trusted code. Does not prove semantics."""
    data = _parse_proposal(text)
    _object(data, {"concepts"})
    chunks = {chunk.chunk_id: chunk for material in materials for chunk in material.chunks
              if chunk.status == "extracted"}

    def references(value):
        refs = []
        for entry in _items(value, 1, 4):
            _object(entry, {"chunk_id", "quote"})
            key = _text(entry["chunk_id"], 64)
            quote = _text(entry["quote"], 2000)
            if key not in chunks or quote not in chunks[key].normalized_text:
                raise IngestionError("Unknown source reference or unsupported evidence quote.")
            if key in {ref.chunk_id for ref in refs}:
                raise IngestionError("Duplicate source reference.")
            refs.append(SourceReference(key, quote))
        return tuple(refs)

    concepts, questions, teaching = [], [], []
    names, question_signatures, ids, failures = set(), {}, set(), []
    for concept_index, item in enumerate(_items(data["concepts"], 1, MAX_CONCEPTS)):
        _object(item, {"name", "summary", "source_refs", "questions", "teaching"})
        name, summary = _text(item["name"], 100), _text(item["summary"])
        refs = references(item["source_refs"])
        if name.casefold() in names:
            raise IngestionError("Duplicate concept.")
        names.add(name.casefold())
        if not any(name in ref.quote and summary in ref.quote for ref in refs):
            raise IngestionError("Concept name and summary must be supported by the same source quote.")
        concept_id = stable_id("concept", course_id, name.casefold(), sorted(ref.chunk_id for ref in refs))
        if concept_id in ids:
            raise IngestionError("Duplicate concept ID.")
        ids.add(concept_id)
        concepts.append(Concept(concept_id, name, summary, refs))
        for question_index, proposal in enumerate(_items(item["questions"], _minimum_questions, 5)):
            _object(proposal, {"prompt", "choices", "answer_index", "explanation", "source_refs"})
            prompt = _text(proposal["prompt"])
            choices = tuple(_text(choice) for choice in _items(proposal["choices"], 2, 4))
            answer = proposal["answer_index"]
            explanation = _text(proposal["explanation"])
            evidence = references(proposal["source_refs"])
            if (type(answer) is not int or not 0 <= answer < len(choices)
                    or len({choice.casefold() for choice in choices}) != len(choices)):
                raise IngestionError("Question choices or answer key are invalid.")
            # A generic MCQ stem can introduce different sets of statements.
            # Compare the whole visible item, ignoring option order so rotating
            # the correct slot cannot disguise a copied question as fresh evidence.
            signature = _question_signature(prompt, choices)
            path = question_path(concept_index, question_index)
            question_failures = []
            if signature in question_signatures:
                question_failures.append({"question_id": path, "reason": "duplicate_question_content",
                                          "duplicate_of": question_signatures[signature]})
            else:
                question_signatures[signature] = path
            if name.casefold() not in prompt.casefold():
                raise IngestionError("Question does not identify its concept.")
            concept_sources = {ref.chunk_id for ref in refs}
            if not any(ref.chunk_id in concept_sources for ref in evidence):
                raise IngestionError("Question evidence must intersect its concept's sources.")
            if not any(ref.chunk_id in concept_sources and choices[answer] in ref.quote
                       and explanation in ref.quote for ref in evidence):
                raise IngestionError("Question answer and explanation lack shared source evidence.")
            for i, choice in enumerate(choices):
                # A source-supported alternative remains ambiguous even when it
                # changes capitalization or quotes another part of the concept.
                # Ignore a terminal prose mark (e.g. a formula followed by '.'
                # versus ':' in the source), retaining mathematical operators.
                if i != answer and any(choice.casefold().rstrip(".!?;:") in ref.quote.casefold()
                                       for ref in (*evidence, *refs)):
                    question_failures.append({"question_id": path, "reason": "ambiguous_question",
                        "field": f"wrong_option_{i + 1 if i < answer else i}",
                        "rule": "wrong_option_is_substring_of_evidence"})
            if question_failures:
                failures.extend(question_failures)
                continue  # Rejected questions are never minted or returned.
            question_id = stable_id("q", concept_id, prompt, choices, answer,
                                    sorted((ref.chunk_id, ref.quote) for ref in evidence))
            if question_id in ids:
                raise IngestionError("Duplicate question ID.")
            ids.add(question_id)
            questions.append(Question(question_id, concept_id, prompt,
                                      tuple(Choice(chr(97 + i), choice) for i, choice in enumerate(choices)),
                                      chr(97 + answer), explanation, evidence))
        kinds = set()
        for proposal in _items(item["teaching"], 3, 3):
            _object(proposal, {"kind", "paragraphs", "source_refs"})
            kind = _text(proposal["kind"], 32)
            if kind not in PROCESS_TEMPLATES or kind in kinds:
                raise IngestionError("Expected exactly one teaching item per intervention kind.")
            kinds.add(kind)
            paragraphs = tuple(_text(p, 800) for p in _items(proposal["paragraphs"], 1, 4))
            evidence = references(proposal["source_refs"])
            teaching_id = stable_id("teaching", concept_id, kind, paragraphs,
                                    sorted((r.chunk_id, r.quote) for r in evidence))
            teaching.append(TeachingArtifact(teaching_id, concept_id, kind, paragraphs, evidence))
    if failures:
        message = ("Duplicate question content." if failures[0]["reason"] == "duplicate_question_content"
                   else "Multiple choices appear in source evidence; extractive question is ambiguous.")
        raise QuestionValidationError(message, failures)
    # Protect all course answers/rubrics, including overlap across concepts.
    for artifact in teaching:
        concept = next(c for c in concepts if c.concept_id == artifact.concept_id)
        validate_teaching(artifact, concept, tuple(questions), materials)
    return tuple(concepts), tuple(questions), tuple(teaching)


def _local_proposal(materials):
    """Deterministic demo scaffolding from actual input; no fake-provider echo."""
    concepts, names = [], set()
    for material in materials:
        for chunk in material.chunks:
            words = chunk.normalized_text.split()
            if chunk.status != "extracted" or len(words) < 8:
                continue
            heading = next((line.strip() for line in chunk.text.splitlines() if line.strip()), "")
            name = normalized(heading)[:100] if len(heading) <= 100 else " ".join(words[:5])[:100].rstrip()
            excerpt = " ".join(words[:35])[:800].rstrip()
            # A single heading word such as "Which" or "The" also occurs in
            # generic teaching. Use a source phrase for the completion answer
            # rather than making ordinary guidance disclose that one-word key.
            answer_prefix = " ".join(excerpt.split()[:5])
            remainder = excerpt[len(answer_prefix):].lstrip()
            if name.casefold() in names:
                continue
            names.add(name.casefold())
            refs = [{"chunk_id": chunk.chunk_id, "quote": excerpt}]
            # This deliberately modest fixture mode tests source recall, not mastery.
            concepts.append({"name": name, "summary": excerpt, "source_refs": refs, "questions": [
                {"prompt": f"According to the material, which excerpt describes {name}?",
                 "choices": [excerpt, "This topic is not discussed in the material.", "The source contains no text."],
                 "answer_index": 0, "explanation": excerpt, "source_refs": refs},
                {"prompt": f"For {name}, complete this exact source excerpt: ___ {remainder}",
                 "choices": ["[no text]", answer_prefix, "[not stated]"],
                 "answer_index": 1, "explanation": excerpt, "source_refs": refs},
            ], "teaching": [
                {"kind": kind, "paragraphs": list(paragraphs), "source_refs": refs}
                for kind, paragraphs in PROCESS_TEMPLATES.items()
            ]})
            if len(concepts) == MAX_CONCEPTS:
                return _complete_local_bank(concepts)
    if not concepts:
        raise IngestionError("No readable source with at least eight words for local study questions.", materials=materials)
    return _complete_local_bank(concepts)


def _complete_local_bank(concepts):
    """Fill a short local source-recall bank with distinct masked source spans.

    Five source excerpts produce ten questions; narrow uploads receive five.
    This remains deterministic reading practice, not generated subject expertise.
    """
    missing = max(0, 5 - sum(len(c["questions"]) for c in concepts))
    for index in range(missing):
        concept = concepts[index % len(concepts)]
        words = concept["summary"].split()
        # Nonoverlapping tail/middle spans, separate from the existing prefix task.
        start = max(0, len(words) - 3 * (index // len(concepts) + 1))
        answer = " ".join(words[start:start + 3])
        masked = " ".join([*words[:start], "___", *words[start + 3:]])
        slot = (index + 2) % 3
        choices = ["[not stated in the source]", "[no matching source phrase]"]
        choices.insert(slot, answer)
        concept["questions"].append({
            "prompt": f"For {concept['name']}, recall the missing phrase: {masked}",
            "choices": choices, "answer_index": slot,
            "explanation": concept["summary"], "source_refs": concept["source_refs"],
        })
    return {"concepts": concepts}


def _inspect_plan(plan, passages, materials, course_id, *, protected_paths=(), rejected=()):
    """Inspect slots independently; never return unchecked generated questions.

    Structural/source failures remain fatal. The empty-question validation below
    is only an internal structural audit; _finish_generation enforces runtime
    minimums before any course can leave this module.
    """
    failures = list(rejected)
    try:
        resolved = resolve_plan(plan, passages)
        paths = [[question_path(ci, qi) for qi in range(len(c["questions"]))]
                 for ci, c in enumerate(resolved["concepts"])]
    except QuestionValidationError as exc:
        resolved, paths = exc.resolved, exc.question_paths
        failures.extend(exc.failures)
    structural = {"concepts": [{**c, "questions": []} for c in resolved["concepts"]]}
    _validate_artifacts(json.dumps(structural), materials, course_id, _minimum_questions=0)
    slots = [(path, ci, q) for ci, c in enumerate(resolved["concepts"])
             for path, q in zip(paths[ci], c["questions"], strict=True)]
    # A repair may not displace an originally valid question by duplicating it.
    slots.sort(key=lambda slot: slot[0] not in protected_paths)
    accepted, signatures = {}, {}
    local_errors = {
        "Generated text is empty, invalid, or too long.": "invalid_question_format",
        "Question choices or answer key are invalid.": "invalid_question_choices",
    }
    for path, ci, proposal in slots:
        if path in {f["question_id"] for f in rejected}:
            continue
        single = {"concepts": [{**resolved["concepts"][ci], "questions": [proposal]}]}
        try:
            _, questions, _ = _validate_artifacts(json.dumps(single), materials, course_id)
        except QuestionValidationError as exc:
            failures.extend({**f, "question_id": path} for f in exc.failures)
            continue
        except IngestionError as exc:
            # Source/answer integrity and teaching failures are deliberately not
            # in this allowlist: they reject the course, rather than being hidden.
            reason = local_errors.get(str(exc))
            if reason is None:
                raise
            failures.append({"question_id": path, "reason": reason})
            continue
        question = questions[0]
        passage = next(p for p in passages if p.passage_id == plan["concepts"][ci]["passage_id"])
        if passage.is_pool:
            source_texts = [chunk.normalized_text.casefold() for material in materials
                            for chunk in material.chunks if chunk.status == "extracted"]
            if any(choice.id != question.answer_key and any(
                    choice.text.casefold().rstrip(".!?;:") in source for source in source_texts)
                   for choice in question.choices):
                failures.append({"question_id": path, "reason": "ambiguous_question",
                                 "rule": "alternative_exact_source_statement"})
                continue
        signature = _question_signature(question.prompt, (c.text for c in question.choices))
        if signature in signatures:
            failures.append({"question_id": path, "reason": "duplicate_question_content",
                             "duplicate_of": signatures[signature]})
            continue
        signatures[signature] = path
        accepted[path] = proposal
    filtered = {"concepts": [{**c, "questions": [accepted[path] for path in paths[ci] if path in accepted]}
                             for ci, c in enumerate(resolved["concepts"])]}
    # Recheck the entire surviving bank, including cross-concept disclosure.
    artifacts = _validate_artifacts(json.dumps(filtered), materials, course_id, _minimum_questions=0)
    return artifacts, failures, frozenset(accepted)


def _finish_generation(inspection, calls, initial_invalid=(), *, minimum=1):
    artifacts, failures, accepted = inspection
    concepts, questions, _ = artifacts
    if any(not any(q.concept_id == c.concept_id for q in questions) for c in concepts):
        raise IngestionError("Every runtime concept needs at least one usable grounded question.")
    if any(sum(q.concept_id == c.concept_id for q in questions) <
           (minimum[i] if isinstance(minimum, tuple) else minimum) for i, c in enumerate(concepts)):
        raise IngestionError("The source supports a practice pool but fewer than three safe questions survived.")
    discarded = len({f["question_id"] for f in failures})
    repaired = len(set(initial_invalid) & accepted)
    return artifacts, calls, discarded, repaired


def _log_question_failures(failures, attempt):
    for failure in failures:
        logger.info("course_ingestion_question_rejected attempt=%s question=%s reason=%s keywords=%s",
                    attempt, failure["question_id"], failure["reason"],
                    ",".join(failure.get("matched_keywords", [])) or "none")


async def _generate_artifacts(passages, materials, course_id):
    topics = topic_passages(passages)
    if topics:
        passages = topics
    minimum = tuple(3 if p.is_pool else 1 for p in topics) if topics else 1
    payload = {"passages": [p.public_to_provider() for p in passages]}
    system = SYSTEM
    if topics:
        payload["required_passage_ids"] = [p.passage_id for p in passages]
        system = ("Where the schema fixes prompt to an enum, copy it exactly. These are explicitly "
                  "SOURCE RECALL questions asking for the exact missing ending of a quoted statement. "
                  "Generate THREE alternative ENDINGS, of similar length to assigned_answer_echo. "
                  "Do not repeat the prefix already displayed in the prompt in any option. "
                  "Do not output another exact source statement, a fragment of the correct answer, "
                  "or equivalent duplicate options. Keep alternatives plausible and similarly sized. "
                  "Never change the assigned original source statement or its prefix cue. "
                  "You are a distractor writer. The correct choice is ALREADY supplied. "
                  "First copy assigned_answer_echo, then write a positive prompt and THREE FALSE answers. "
                  "NEVER put a true statement in any wrong_option field, even if it omits a heading. "
                  "For a worked example, all three alternatives must yield a WRONG result or relationship. "
                  "For a rule, all three alternatives must CONTRADICT the supplied rule. "
                  "Write the question wording for EVERY named slot in the structured-response tool. "
                  "Each slot description contains its topic and EXACT assigned correct answer. "
                  "Return only the named question objects; no concepts or passage IDs. "
                  "For each object copy assigned_answer_echo exactly from its schema enum. That is "
                  "the correct option: ALL THREE wrong_option fields must be false alternatives. "
                  "Do not copy a question from another slot: each stem must be directly answered "
                  "by that slot's entire assigned answer. The mandatory answer echo is the only "
                  "exception to the no-answer-output rule below; it cannot change the server key.\n" + QUESTION_RULES)
    schema = fixed_topic_schema(passages) if topics else plan_schema(passages)
    initial, calls, targets = None, 0, []
    try:
        async with asyncio.timeout(GENERATION_BUDGET_SECONDS):
            with provider.call_budget(GENERATION_BUDGET_SECONDS):
                calls += 1
                result = await provider.complete(json.dumps(payload, ensure_ascii=True),
                    system=system, max_tokens=6000, purpose="course_ingestion",
                    response_schema=schema)
                if result.provider != "bedrock":
                    raise IngestionError("Unexpected provider response; course generation rejected.")
                plan = _parse_proposal(result.text)
                if topics:
                    plan = resolve_fixed_topics(plan, passages)
                inspected = _inspect_plan(plan, passages, materials, course_id)
                initial = inspected
                if not initial[1]:
                    return _finish_generation(initial, calls, minimum=minimum)
                _log_question_failures(initial[1], 1)
                targets = list(dict.fromkeys(f["question_id"] for f in initial[1]))
                logger.info("course_ingestion_revision reason=%s", initial[1][0]["reason"])
                payload.update(rejected_plan=plan, revision={"failures": initial[1], "repair_targets": targets})
                payload["repair_slots"] = repair_slots(plan, passages, targets)
                calls += 1
                try:
                    result = await provider.complete(json.dumps(payload, ensure_ascii=True),
                        system=REPAIR_SYSTEM, max_tokens=6000, purpose="course_ingestion",
                        response_schema=repair_schema(targets))
                    if result.provider != "bedrock":
                        raise IngestionError("Unexpected repair provider response.")
                    patched = apply_repairs(plan, _parse_proposal(result.text), targets)
                except (provider.ProviderError, IngestionError):
                    # An unusable repair envelope has no authority over the valid
                    # initial bank. Preserve it; do not claim anything was repaired.
                    logger.info("course_ingestion_repair_unavailable reason=invalid_or_failed_response")
                    return _finish_generation(initial, calls, targets, minimum=minimum)
                inspected = _inspect_plan(patched, passages, materials, course_id,
                                          protected_paths=initial[2])
                _log_question_failures(inspected[1], 2)
                return _finish_generation(inspected, calls, targets, minimum=minimum)
    except TimeoutError as exc:
        if initial is not None:
            logger.info("course_ingestion_repair_unavailable reason=deadline")
            return _finish_generation(initial, calls, targets, minimum=minimum)
        raise provider.ProviderError("Course generation deadline exceeded") from exc


async def process_course(paths: list[str | Path], *, title: str = "Uploaded course",
                         mode: str | None = None) -> ProcessedCourse:
    """Extract PDF/PPTX and validate a bounded bank. Never accesses runtime state.

    Default mode follows MODEL_PROVIDER (fake if absent); local and fake both
    bypass the provider. Explicit bedrock requires MODEL_PROVIDER=bedrock, keeping
    provider selection in the existing seam. Invalid slots permit one repair;
    remaining invalid slots are omitted only when every concept stays usable.
    Structural/source failures are fatal. No alternate provider or invented content.
    """
    title = _text(title, 200)
    if not isinstance(paths, (list, tuple)) or not 1 <= len(paths) <= MAX_FILES:
        raise IngestionError("Supply between one and eight PDF/PPTX files.")
    selected = mode if mode is not None else os.environ.get("MODEL_PROVIDER", "fake")
    if selected not in {"fake", "local", "bedrock"}:
        raise IngestionError("Ingestion mode must be fake, local, or bedrock.")
    if selected == "bedrock" and os.environ.get("MODEL_PROVIDER") != "bedrock":
        raise IngestionError("Set MODEL_PROVIDER=bedrock to use the existing Bedrock provider seam.")
    # Extraction includes filesystem, ZIP/XML and Poppler work. Keep the provider
    # coroutine on the caller's loop so its existing deadline remains effective.
    extraction = asyncio.create_task(asyncio.to_thread(
        lambda: tuple(extract_material(path) for path in paths)))
    try:
        materials = await asyncio.shield(extraction)
    except asyncio.CancelledError:
        # A cancelled await cannot kill a thread. Finish before an HTTP caller
        # removes the temporary source files that thread still owns.
        await asyncio.gather(extraction, return_exceptions=True)
        raise
    if len({material.material_id for material in materials}) != len(materials):
        raise IngestionError("Duplicate source material.", materials=materials)
    course_id = stable_id("course", "study-bank-6", title, sorted(material.material_id for material in materials))
    sources = [{"chunk_id": chunk.chunk_id, "normalized_text": chunk.normalized_text}
               for material in materials for chunk in material.chunks if chunk.status == "extracted"]
    if not sources:
        raise IngestionError("No extractable text; scanned pages/images need OCR outside this MVP.", materials=materials)
    warnings = [f"{material.material_id}:{material.status}" for material in materials if material.status != "extracted"]
    warnings.append("Source evidence checks do not prove factual or pedagogical correctness; review before learner use.")
    if selected in {"fake", "local"}:
        raw = json.dumps(_local_proposal(materials))
        warnings.append("Local demo templates use up to five distinct source excerpts; they are not a full course analysis.")
        calls, label, discarded, repaired = 0, "local", 0, 0
        try:
            concepts, questions, teaching = _validate_artifacts(raw, materials, course_id)
        except IngestionError as exc:
            raise IngestionError(str(exc), materials=materials) from exc
    else:
        if sum(len(source["normalized_text"]) for source in sources) > MAX_CONTEXT_CHARS:
            raise IngestionError("Bedrock context exceeds 24,000 characters; split the material before processing.", materials=materials)
        try:
            passages = build_passages(materials)
        except IngestionError as exc:
            raise IngestionError(str(exc), materials=materials) from exc
        try:
            (concepts, questions, teaching), calls, discarded, repaired = await _generate_artifacts(passages, materials, course_id)
        except provider.ProviderError as exc:
            raise IngestionError("Course generation failed at the provider; no fallback was attempted.", materials=materials) from exc
        except IngestionError as exc:
            raise IngestionError(str(exc), materials=materials) from exc
        label = "bedrock"
        warnings.append("Rich pools use explicitly labeled exact-source recall questions with server-bound missing endings and prefix cues. These assess source recall, not general application mastery; source truth still requires human review.")
        if repaired or discarded:
            warnings.append(f"One question repair attempted; {repaired} repaired questions accepted.")
        if discarded:
            warnings.append(f"Degraded generation: {discarded} invalid question slots omitted after one repair attempt.")
            logger.info("course_ingestion_degraded discarded_questions=%s repaired_questions=%s", discarded, repaired)
        logger.info("course_ingestion_ready concepts=%s questions=%s provider_calls=%s repaired_questions=%s discarded_questions=%s",
                    len(concepts), len(questions), calls, repaired, discarded)
    return ProcessedCourse(course_id, title, materials, concepts, questions,
                           ProcessingMetadata("2" if selected == "bedrock" and any(p.extra_evidence for p in topic_passages(passages)) else "1", label, calls, tuple(warnings), degraded=bool(discarded),
                                              discarded_question_count=discarded, repaired_question_count=repaired),
                           teaching=teaching)
