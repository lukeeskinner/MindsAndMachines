import asyncio
from dataclasses import dataclass
from copy import deepcopy
from backend.app.agents.provider import call_budget
from backend.app.teaching.runtime_catalog import RuntimeAvailability
from contracts.interfaces import Assessor, Learner, Policy, Teaching
from contracts.models import (
    Candidate, HistoryEntry, LearnerState, LearnerUpdate,
    PublicAssessment, PublicDecision, Question, TeachingResult, TurnRequest, TurnResponse,
)


class IntegrationError(ValueError):
    """A seam violated the trusted policy/catalog contract."""


# Sequential provider waits total at most 16s, leaving 2s for local work and
# another 2s before the existing browser deadline. Smaller SDK settings win.
ASSESSOR_BUDGET_SECONDS = 4.0
TUTOR_BUDGET_SECONDS = 12.0
TURN_BUDGET_SECONDS = 18.0


class TurnTimeoutError(TimeoutError):
    """The turn exceeded its deadline; no partial result may be saved."""


@dataclass
class Coordinator:
    assessor: Assessor
    learner: Learner
    policy: Policy
    teaching: Teaching
    course_progression: RuntimeAvailability | None = None

    async def run_turn(self, request: TurnRequest, question: Question,
                       state: LearnerState, history: list[HistoryEntry],
                       candidates: list[Candidate], questions: dict[str, Question]
                       ) -> tuple[LearnerUpdate, TurnResponse]:
        try:
            async with asyncio.timeout(TURN_BUDGET_SECONDS):
                with call_budget(TURN_BUDGET_SECONDS):
                    return await self._run_turn(request, question, state, history, candidates, questions)
        except TimeoutError as exc:
            raise TurnTimeoutError("Learning turn timed out") from exc

    async def _run_turn(self, request: TurnRequest, question: Question,
                        state: LearnerState, history: list[HistoryEntry],
                        candidates: list[Candidate], questions: dict[str, Question]
                        ) -> tuple[LearnerUpdate, TurnResponse]:
        trace: list[str] = []
        bindings = {c.candidate_id: c.model_dump() for c in candidates}
        with call_budget(ASSESSOR_BUDGET_SECONDS):
            assessment = await self.assessor.assess(question, request.answer)
        trace.append("assess")
        update = self.learner.update(state, assessment, history)
        trace.append("update")
        decision = self.policy.choose(update.concepts, assessment, candidates, history)
        trace.append("select")
        # Snapshot policy authority before entering the replaceable teaching seam.
        decision = decision.model_copy(deep=True) if decision else None
        expected_next = decision.next_question_id if decision else None
        if self.course_progression is not None:
            progression = self.course_progression
            if decision is not None:
                if bindings.get(decision.candidate_id) != decision.model_dump(exclude={"reason"}):
                    raise IntegrationError("Policy selected an ineligible course candidate")
            elif not progression.concept_exhausted:
                raise IntegrationError("Policy stopped before the concept was exhausted")
            else:
                expected_next = progression.next_concept_question_id
            if (expected_next is None) != progression.course_exhausted:
                raise IntegrationError("Course completion does not match question exhaustion")
        if expected_next is not None and expected_next not in questions:
            raise IntegrationError("Policy selected an unknown next question")
        next_question = questions[expected_next].public() if expected_next is not None else None
        with call_budget(TUTOR_BUDGET_SECONDS):
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
