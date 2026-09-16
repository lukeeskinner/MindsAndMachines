from dataclasses import dataclass
from copy import deepcopy
from contracts.interfaces import Assessor, Learner, Policy, Teaching
from contracts.models import (
    Candidate, HistoryEntry, LearnerState, LearnerUpdate,
    PublicAssessment, PublicDecision, Question, TeachingResult, TurnRequest, TurnResponse,
)


class IntegrationError(ValueError):
    """A seam violated the trusted policy/catalog contract."""


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
        # Snapshot policy authority before entering the replaceable teaching seam.
        decision = decision.model_copy(deep=True) if decision else None
        expected_next = decision.next_question_id if decision else None
        if expected_next is not None and expected_next not in questions:
            raise IntegrationError("Policy selected an unknown next question")
        next_question = questions[expected_next].public() if expected_next is not None else None
        teaching: TeachingResult = await self.teaching.teach(
            decision.model_copy(deep=True) if decision else None,
            assessment.model_copy(deep=True), deepcopy(update.concepts), request.presentation_preferences,
        )
        trace.append("teach")
        # Teaching can format an intervention, never change its next question.
        if teaching.next_question_id != expected_next:
            raise IntegrationError("Teaching changed the policy's next question")
        response = TurnResponse(
            session_id=request.session_id,
            assessment=PublicAssessment(**assessment.model_dump(
                include={"outcome", "misconception_id", "feedback"})),
            concepts=update.concepts,
            decision=PublicDecision(**decision.model_dump(
                include={"candidate_id", "concept_id", "kind", "reason"})) if decision else None,
            tutor=teaching.model_dump(exclude={"next_question_id"}),
            mode="live" if teaching.teaching_source == "bedrock" else "dummy",
            provider="bedrock" if teaching.teaching_source == "bedrock" else "fake",
            next_question=next_question, trace=trace,
        )
        return update, response
