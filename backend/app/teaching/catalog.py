"""Authored questions and intervention content, loaded locally. No retrieval service."""
import json
from pathlib import Path
from contracts.models import Candidate, Question


class Catalog:
    def __init__(self) -> None:
        path = Path(__file__).resolve().parents[3] / "content" / "demo.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.concept_ids = data["concepts"]
        self.questions = {q["question_id"]: Question(**q) for q in data["questions"]}
        self.first_question_id = next(iter(self.questions))
        self.candidates = [Candidate(**c) for c in data["candidates"]]
        self.teaching = data["teaching"]

    def question(self, question_id: str) -> Question:
        return self.questions[question_id]
