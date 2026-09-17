"""Workstream-local, immutable server-side records; no public API contract changes."""
from dataclasses import asdict, dataclass
import hashlib
import json
import re


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def stable_id(prefix: str, *parts: object) -> str:
    payload = json.dumps(parts, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return prefix + "_" + hashlib.sha256(payload.encode()).hexdigest()[:24]


@dataclass(frozen=True)
class SourceChunk:
    chunk_id: str
    location_kind: str  # page or slide
    number: int  # one-based, from the file structure
    text: str  # original extraction, never overwritten by normalization or generation
    normalized_text: str
    status: str  # extracted, empty, unreadable


@dataclass(frozen=True)
class SourceMaterial:
    material_id: str
    filename: str
    sha256: str
    format: str
    chunks: tuple[SourceChunk, ...]
    status: str  # extracted, partial, empty, unreadable
    issues: tuple[str, ...]


@dataclass(frozen=True)
class SourceReference:
    chunk_id: str
    quote: str  # exact substring of that chunk's normalized_text


@dataclass(frozen=True)
class Concept:
    concept_id: str
    name: str
    summary: str
    source_refs: tuple[SourceReference, ...]


@dataclass(frozen=True)
class Choice:
    id: str
    text: str


@dataclass(frozen=True)
class Question:
    question_id: str
    concept_id: str
    prompt: str
    choices: tuple[Choice, ...]
    answer_key: str
    explanation: str
    source_refs: tuple[SourceReference, ...]

    def public(self) -> dict:
        """Explicit projection: no answer, explanation, or evidence quotes."""
        return {key: value for key, value in asdict(self).items()
                if key in {"question_id", "concept_id", "prompt", "choices"}}


@dataclass(frozen=True)
class TeachingArtifact:
    """Private prose checked for use before every question of this concept.

    Only paragraphs are intended for learner display. References and review
    status remain server-side; source checks do not constitute human review.
    """

    teaching_id: str
    concept_id: str
    kind: str
    paragraphs: tuple[str, ...]
    source_refs: tuple[SourceReference, ...]
    requires_review: bool = True


@dataclass(frozen=True)
class ProcessingMetadata:
    schema_version: str
    mode: str
    provider_calls: int
    warnings: tuple[str, ...]
    requires_review: bool = True
    degraded: bool = False
    discarded_question_count: int = 0
    repaired_question_count: int = 0


@dataclass(frozen=True)
class ProcessedCourse:
    course_id: str
    title: str
    materials: tuple[SourceMaterial, ...]
    concepts: tuple[Concept, ...]
    questions: tuple[Question, ...]
    metadata: ProcessingMetadata
    teaching: tuple[TeachingArtifact, ...] = ()

    def to_dict(self) -> dict:
        """SERVER-ONLY artifact: includes answer keys and source text."""
        return asdict(self)


class IngestionError(ValueError):
    """Safe, actionable failure; extraction records remain available to callers."""

    def __init__(self, message: str, *, materials: tuple[SourceMaterial, ...] = ()):
        super().__init__(message)
        self.materials = materials
