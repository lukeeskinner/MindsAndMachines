from fastapi import APIRouter, Body, Header, HTTPException
from backend.app.agents.coordinator import Coordinator, IntegrationError
from backend.app.auth.cognito import AuthError, cognito_enabled, verify_id_token
from backend.app.storage.dynamo import DynamoStore
from backend.app.storage.memory import MemoryStore, Session
from backend.app.storage.courses import MemoryCourseRegistry
from backend.app.teaching.catalog import Catalog
from contracts.models import HistoryEntry, SessionRequest, SessionResponse, TurnRequest, TurnResponse


def router_for(coordinator: Coordinator, store: MemoryStore | DynamoStore, catalog: Catalog,
               course_registry: MemoryCourseRegistry) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.post("/sessions", response_model=SessionResponse, status_code=201)
    async def new_session(request: SessionRequest = Body(default=SessionRequest()),
                          authorization: str | None = Header(None)) -> SessionResponse:
        user_id = None
        if cognito_enabled() and authorization is not None:
            try:
                user_id = verify_id_token(authorization)
            except AuthError as exc:
                raise HTTPException(401, str(exc)) from None
        if request.course_id is None:
            concept_ids = catalog.concept_ids
            question = catalog.question(catalog.first_question_id)
        else:
            try:
                course_catalog = course_registry.catalog(request.course_id)
            except KeyError:
                raise HTTPException(404, "Course not found.") from None
            concept_ids = course_catalog.concept_ids
            question = course_catalog.question(course_catalog.first_question_id).question
        initial = coordinator.learner.initial_state(concept_ids)
        session_id = store.new_session(question.question_id, initial.state, user_id,
                                       course_id=request.course_id)
        return SessionResponse(session_id=session_id,
                               course_id=request.course_id, question=question.public(),
                               concepts=initial.concepts)

    @router.post("/turns", response_model=TurnResponse)
    async def turn(request: TurnRequest) -> TurnResponse:
        try:
            session = store.load_session(request.session_id)
        except KeyError:
            raise HTTPException(404, "Session not found. Start a new session.") from None
        if session.course_id is not None:
            # Foundation sessions are previews only. Never grade an uploaded item
            # using the demo assessor, candidates or Tutor.
            raise HTTPException(409, "Course learning is not enabled yet.")
        if request.question_id != session.question_id:
            raise HTTPException(400, "Please answer the current question or start a new session.")
        question = catalog.question(request.question_id)
        if request.answer not in {choice.id for choice in question.choices}:
            raise HTTPException(400, "Choose one of the listed answers.")
        try:
            update, response = await coordinator.run_turn(
                request, question, session.learner_state, session.history,
                catalog.candidates, catalog.questions,
            )
        except IntegrationError:
            raise HTTPException(500, "Learning activity configuration error. Start a new session.") from None
        entry = HistoryEntry(question_id=question.question_id,
                             evidence_applied=update.evidence_applied,
                             candidate_id=response.decision.candidate_id if response.decision else None)
        store.save_session(request.session_id, Session(
            response.next_question.question_id if response.next_question else None,
            update.state, [*session.history, entry], session.user_id, session.course_id,
        ))
        return response

    return router
