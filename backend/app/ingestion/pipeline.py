"""Bounded course generation using the existing provider seam, never runtime wiring."""
import asyncio
import json
import os
import re
from pathlib import Path

from backend.app.agents import provider
from .extraction import extract_material
from .models import (Choice, Concept, IngestionError, ProcessedCourse, ProcessingMetadata,
                     Question, SourceReference, TeachingArtifact, normalized, stable_id)
from .teaching import PROCESS_TEMPLATES, validate_teaching
from .passages import SYSTEM, build_passages, plan_schema, resolve_plan

MAX_CONTEXT_CHARS = 24_000
MAX_CONCEPTS = 5
MAX_FILES = 8


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


def _validate_artifacts(text: str, materials: tuple, course_id: str) -> tuple[tuple, tuple, tuple]:
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
    names, prompts, ids = set(), set(), set()
    for item in _items(data["concepts"], 1, MAX_CONCEPTS):
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
        for proposal in _items(item["questions"], 2, 5):
            _object(proposal, {"prompt", "choices", "answer_index", "explanation", "source_refs"})
            prompt = _text(proposal["prompt"])
            choices = tuple(_text(choice) for choice in _items(proposal["choices"], 2, 4))
            answer = proposal["answer_index"]
            explanation = _text(proposal["explanation"])
            evidence = references(proposal["source_refs"])
            if (type(answer) is not int or not 0 <= answer < len(choices)
                    or len({choice.casefold() for choice in choices}) != len(choices)):
                raise IngestionError("Question choices or answer key are invalid.")
            if prompt.casefold() in prompts:
                raise IngestionError("Duplicate question prompt.")
            if name.casefold() not in prompt.casefold():
                raise IngestionError("Question does not identify its concept.")
            concept_sources = {ref.chunk_id for ref in refs}
            if not any(ref.chunk_id in concept_sources for ref in evidence):
                raise IngestionError("Question evidence must intersect its concept's sources.")
            if not any(ref.chunk_id in concept_sources and choices[answer] in ref.quote
                       and explanation in ref.quote for ref in evidence):
                raise IngestionError("Question answer and explanation lack shared source evidence.")
            if any(choice in ref.quote for i, choice in enumerate(choices) if i != answer for ref in evidence):
                raise IngestionError("Multiple choices appear in source evidence; extractive question is ambiguous.")
            prompts.add(prompt.casefold())
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


async def process_course(paths: list[str | Path], *, title: str = "Uploaded course",
                         mode: str | None = None) -> ProcessedCourse:
    """Extract PDF/PPTX, then generate once. Never calls storage or learning runtime.

    Default mode follows MODEL_PROVIDER (fake if absent); local and fake both
    bypass the provider. Explicit bedrock requires MODEL_PROVIDER=bedrock, keeping
    provider selection in the existing seam. Failures raise IngestionError without
    retries, invented content, or a silent fallback.
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
    course_id = stable_id("course", "study-bank-2", title, sorted(material.material_id for material in materials))
    sources = [{"chunk_id": chunk.chunk_id, "normalized_text": chunk.normalized_text}
               for material in materials for chunk in material.chunks if chunk.status == "extracted"]
    if not sources:
        raise IngestionError("No extractable text; scanned pages/images need OCR outside this MVP.", materials=materials)
    warnings = [f"{material.material_id}:{material.status}" for material in materials if material.status != "extracted"]
    warnings.append("Source evidence checks do not prove factual or pedagogical correctness; review before learner use.")
    if selected in {"fake", "local"}:
        raw = json.dumps(_local_proposal(materials))
        warnings.append("Local demo templates use up to five distinct source excerpts; they are not a full course analysis.")
        calls, label = 0, "local"
    else:
        if sum(len(source["normalized_text"]) for source in sources) > MAX_CONTEXT_CHARS:
            raise IngestionError("Bedrock context exceeds 24,000 characters; split the material before processing.", materials=materials)
        try:
            passages = build_passages(materials)
        except IngestionError as exc:
            raise IngestionError(str(exc), materials=materials) from exc
        try:
            result = await provider.complete(json.dumps({"passages": [p.public_to_provider() for p in passages]}, ensure_ascii=True),
                                             system=SYSTEM, max_tokens=6000, purpose="course_ingestion",
                                             response_schema=plan_schema(passages))
        except provider.ProviderError as exc:
            raise IngestionError("Course generation failed at the provider; no retry or fallback was attempted.", materials=materials) from exc
        if result.provider != "bedrock":
            raise IngestionError("Unexpected provider response; course generation rejected.", materials=materials)
        raw, calls, label = result.text, 1, "bedrock"
    try:
        if selected == "bedrock":
            raw = json.dumps(resolve_plan(_parse_proposal(raw), passages))
            warnings.append("AI-written questions use server-resolved source evidence and authored reading guidance.")
        concepts, questions, teaching = _validate_artifacts(raw, materials, course_id)
    except IngestionError as exc:
        raise IngestionError(str(exc), materials=materials) from exc
    return ProcessedCourse(course_id, title, materials, concepts, questions,
                           ProcessingMetadata("1", label, calls, tuple(warnings)), teaching=teaching)
