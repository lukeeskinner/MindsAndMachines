import asyncio
from collections import Counter
from copy import deepcopy
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.app.main import create_app
from backend.app.storage.memory import MemoryStore
from backend.app.storage.courses import MemoryCourseRegistry
from backend.tests.ingestion.pool_fixture import pool_course
from backend.app.learner.evidence import fingerprint


class AdaptivePoolsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.course = asyncio.run(pool_course())

    def setUp(self):
        self.store = MemoryStore()
        registry = MemoryCourseRegistry()
        registry.register(self.course)
        self.environment = patch.dict("os.environ", {"MODEL_PROVIDER": "fake", "DYNAMODB_TABLE_NAME": ""})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        with patch("backend.app.main.MemoryStore", return_value=self.store):
            self.client = TestClient(create_app(course_registry=registry))
        self.keys = {q.question_id: q.answer_key for q in self.course.questions}

    def start(self, previous=None, reset=False):
        r = self.client.post("/api/v1/sessions", json={
            "course_id": self.course.course_id, "previous_session_id": previous, "reset_learner": reset})
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()

    def turn(self, session, question, answer):
        r = self.client.post("/api/v1/turns", json={
            "session_id": session["session_id"], "question_id": question["question_id"], "answer": answer})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_three_unique_grounded_questions_and_cards_per_concept(self):
        self.assertEqual(set(Counter(q.concept_id for q in self.course.questions).values()), {4})
        self.assertEqual(len(self.keys), 16)
        session = self.start()
        self.assertEqual(set(Counter(c["concept_id"] for c in session["flashcards"]).values()), {3})
        self.assertEqual(len({c["card_id"] for c in session["flashcards"]}), 12)
        for card in session["flashcards"]:
            self.assertTrue(any(card["back"] in chunk.normalized_text
                                for m in self.course.materials for chunk in m.chunks))
        self.assertEqual(len({(q.prompt, tuple(sorted(c.text for c in q.choices))) for q in self.course.questions}), 16)

    def test_mixed_flow_fresh_retry_coverage_counts_and_duplicate_post(self):
        s = self.start()
        question = s["question"]
        seen, events = set(), []
        while question:
            self.assertNotIn(question["question_id"], seen)
            seen.add(question["question_id"])
            if len(seen) == 1:
                answer = next(c["id"] for c in question["choices"] if c["id"] not in {self.keys[question["question_id"]], "unsure"})
            elif len(seen) == 3:
                answer = "unsure"
            else:
                answer = self.keys[question["question_id"]]
            r = self.turn(s, question, answer)
            if len(seen) == 1:
                self.assertEqual(r["next_question"]["concept_id"], question["concept_id"])
                c = next(c for c in r["concepts"] if c["concept_id"] == question["concept_id"])
                self.assertEqual((c["alpha"], c["beta"]), (1,2))
            duplicate = self.client.post("/api/v1/turns", json={
                "session_id":s["session_id"], "question_id":question["question_id"], "answer":answer})
            self.assertEqual(duplicate.status_code, 400)
            events.append(r)
            self.assertEqual(r["counts"]["submitted_answers"], len(seen))
            self.assertEqual(r["counts"]["accepted_observations"], len(seen) - int(len(seen)>=3))
            question = r["next_question"]
        self.assertEqual(len(seen), 10)
        self.assertEqual(r["counts"]["unique_questions_seen"], 10)
        self.assertEqual(len({q.concept_id for q in self.course.questions if q.question_id in seen}), 4)
        self.assertEqual(sum(c["evidence_count"] for c in r["concepts"]),9)

    def test_retake_persists_beliefs_clears_practice_chat_and_explicit_reset(self):
        s = self.start()
        first = s["question"]
        self.client.post("/api/v1/chat",json={"session_id":s["session_id"],"message":"Explain the power rule"})
        result = self.turn(s, first, self.keys[first["question_id"]])
        again = self.start(s["session_id"])
        self.assertEqual(again["concepts"], result["concepts"])
        self.assertEqual(again["session_start"], result["concepts"])
        self.assertNotEqual(again["question"]["question_id"], first["question_id"])
        stored = self.store.load_session(again["session_id"])
        self.assertEqual((stored.history,stored.chat_history,stored.generated_questions),([],[],{}))
        self.assertIsNone(stored.remediation_focus)
        stale = self.client.post("/api/v1/turns",json={
            "session_id":s["session_id"],"question_id":result["next_question"]["question_id"],"answer":"a"})
        self.assertEqual(stale.status_code,409)
        reset = self.start(again["session_id"],True)
        self.assertTrue(all((c["alpha"],c["beta"],c["evidence_count"])==(1,1,0) for c in reset["concepts"]))
        self.assertFalse(reset["question"]["review"])

    def test_exhausted_lifetime_bank_is_labelled_review_without_new_evidence(self):
        s = self.start()
        for cycle in range(3):
            q = s["question"]
            while q:
                before = deepcopy(self.store.load_session(s["session_id"]).learner_state)
                r = self.turn(s,q,self.keys[q["question_id"]])
                if q["review"]:
                    self.assertEqual(before,self.store.load_session(s["session_id"]).learner_state)
                q = r["next_question"]
            if cycle == 2:
                self.assertEqual(r["counts"]["accepted_observations"],0)
            previous = s
            s = self.start(s["session_id"])
            self.assertEqual(s["concepts"],r["concepts"])
            self.assertNotEqual(s["question"]["question_id"],previous["question"]["question_id"])
        self.assertEqual(sum(c["evidence_count"] for c in s["concepts"]),16)

    def test_content_fingerprint_ignores_choice_order_and_punctuation(self):
        from backend.app.storage.courses import adapt_question
        q = adapt_question(self.course.questions[0]).question
        copy = q.model_copy(deep=True)
        copy.question_id = "different"
        copy.choices.reverse()
        copy.prompt += "!!"
        self.assertEqual(fingerprint(q),fingerprint(copy))

    def test_flashcards_and_chat_do_not_add_evidence(self):
        s=self.start()
        before=deepcopy(self.store.load_session(s["session_id"]).learner_state)
        response=self.client.post("/api/v1/chat",json={"session_id":s["session_id"],"message":"How do I review the chain rule?"})
        self.assertEqual(response.status_code,200)
        self.assertEqual(before,self.store.load_session(s["session_id"]).learner_state)

    def test_regenerated_source_fact_with_new_distractors_is_same_evidence(self):
        from backend.app.storage.courses import adapt_question
        q = adapt_question(self.course.questions[0]).question
        changed = q.model_copy(deep=True)
        changed.question_id = "regenerated"
        wrong = next(c for c in changed.choices if c.id != changed.answer_key)
        wrong.text = "A newly generated alternative ending."
        self.assertEqual(fingerprint(q), fingerprint(changed))
