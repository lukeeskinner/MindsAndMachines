from dataclasses import dataclass
from contracts.interfaces import Assessor, Learner, Policy, Teaching
from contracts.models import (
    Candidate, HistoryEntry, LearnerState, LearnerUpdate,
    PublicAssessment, PublicDecision, Question, TeachingResult, TurnRequest, TurnResponse,
)


@dataclass
class Coordinator:
    assessor: Assessor
    learner: Learner
    policy: Policy
    teaching: Teaching

    async def run_turn(self, request: TurnRequest, question: Question,
                       state: LearnerState, history: list[HistoryEntry],
                       candidates: list[Candidate], questions: dict[str, Question]
                       ) -> tuple[LearnerUpdate, TurnResponse]:
        trace: list[str] = []
        assessment = await self.assessor.assess(question, request.answer)
        trace.append("assess")
        update = self.learner.update(state, assessment, history)
        trace.append("update")
        decision = self.policy.choose(update.concepts, assessment, candidates, history)
        trace.append("select")
        teaching: TeachingResult = await self.teaching.teach(
            decision, assessment, update.concepts, request.presentation_preferences,
        )
        trace.append("teach")
        # Teaching can format an intervention, never change its next question.
        expected_next = decision.next_question_id if decision else None
        if teaching.next_question_id != expected_next:
            raise ValueError("Teaching changed the policy's next question")
        next_question = questions[expected_next].public() if expected_next else None
        response = TurnResponse(
            session_id=request.session_id,
            assessment=PublicAssessment(**assessment.model_dump(
                include={"outcome", "misconception_id", "feedback"})),
            concepts=update.concepts,
            decision=PublicDecision(**decision.model_dump(
                include={"candidate_id", "concept_id", "kind", "reason"})) if decision else None,
            tutor={"text": teaching.text, "fallback": teaching.fallback},
            next_question=next_question, trace=trace,
        )
        return update, response
