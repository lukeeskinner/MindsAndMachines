from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import replace
from backend.app.teaching.chat import answer_message
from backend.app.agents.provider import ProviderError
from fastapi import APIRouter, Body, Header, HTTPException
from backend.app.agents.coordinator import Coordinator, IntegrationError, TurnTimeoutError
from backend.app.auth.cognito import AuthError, cognito_enabled, verify_id_token
from backend.app.storage.dynamo import DynamoStore
from backend.app.storage.memory import MemoryStore, Session
from backend.app.storage.courses import MemoryCourseRegistry
from backend.app.teaching.catalog import Catalog
from backend.app.teaching.flashcards import demo_flashcards, course_flashcards
from backend.app.teaching.remediation import RemediationTurn, rank_flashcards
from backend.app.ingestion.models import IngestionError
from backend.app.teaching.runtime_catalog import RuntimeAvailability, RuntimeCatalog, build_runtime_catalog
from contracts.models import ChatRequest, ChatResponse, HistoryEntry, SessionRequest, SessionResponse, TurnRequest, TurnResponse


def router_for(coordinator: Coordinator, store: MemoryStore | DynamoStore, catalog: Catalog,
               course_registry: MemoryCourseRegistry,
               course_coordinator: Callable[[RuntimeCatalog, RuntimeAvailability], Coordinator]) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    active_sessions: set[str] = set()

    @contextmanager
    def session_request(session_id: str):
        # Single-process demo: reject overlapping writes instead of queuing a
        # request with stale question/context. Always release on failure.
        if session_id in active_sessions:
            raise HTTPException(409, "A request is already running for this session.")
        active_sessions.add(session_id)
        try:
            yield
        finally:
            active_sessions.discard(session_id)

    def course_runtime(course_id: str) -> RuntimeCatalog:
        try:
            return build_runtime_catalog(course_registry.get(course_id))
        except KeyError:
            raise HTTPException(404, "Course not found. Upload the materials again.") from None
        except IngestionError:
            raise HTTPException(422, "Course learning content is invalid. Upload the materials again.") from None

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
            question_count = len(catalog.questions)
            cards = demo_flashcards()
        else:
            course_catalog = course_runtime(request.course_id)
            concept_ids = course_catalog.concept_ids
            question = course_catalog.question(course_catalog.first_question_id)
            question_count = len(course_catalog.questions)
            cards = course_flashcards(course_catalog.course)
        initial = coordinator.learner.initial_state(concept_ids)
        session_id = store.new_session(question.question_id, initial.state, user_id,
                                       course_id=request.course_id)
        return SessionResponse(session_id=session_id,
                               course_id=request.course_id, question=question.public(),
                               concepts=initial.concepts, question_count=question_count,
                               flashcards=cards)

    @router.post("/turns", response_model=TurnResponse)
    async def turn(request: TurnRequest) -> TurnResponse:
        with session_request(request.session_id):
            return await run_turn(request)

    async def run_turn(request: TurnRequest) -> TurnResponse:
        try:
            session = store.load_session(request.session_id)
        except KeyError:
            raise HTTPException(404, "Session not found. Start a new session.") from None
        runtime = course_runtime(session.course_id) if session.course_id is not None else catalog
        if isinstance(runtime, RuntimeCatalog):
            try:
                runtime.apply_session_questions(session.generated_questions)
            except ValueError:
                raise HTTPException(500, "Learning activity configuration error. Start a new session.") from None
        if request.question_id != session.question_id:
            raise HTTPException(400, "Please answer the current question or start a new session.")
        try:
            question = runtime.question(request.question_id)
        except KeyError:
            raise HTTPException(500, "Learning activity configuration error. Start a new session.") from None
        if request.answer not in {choice.id for choice in question.choices}:
            raise HTTPException(400, "Choose one of the listed answers.")
        try:
            active_coordinator = coordinator
            candidates = runtime.candidates
            if isinstance(runtime, RuntimeCatalog):
                if (set(session.learner_state.skills) != set(runtime.concept_ids)
                        or request.question_id in {entry.question_id for entry in session.history}):
                    raise IntegrationError("Course session state does not match its current activity")
                try:
                    availability = runtime.eligible_candidates(
                        current_question_id=request.question_id,
                        consumed_question_ids=[entry.question_id for entry in session.history],
                        consumed_candidate_ids=[entry.candidate_id for entry in session.history
                                                if entry.candidate_id is not None],
                    )
                except ValueError as exc:
                    raise IntegrationError("Course history contains foreign IDs") from exc
                candidates = list(availability.candidates)
                active_coordinator = course_coordinator(runtime, availability)
            remediation = RemediationTurn(session.course_id, session.remediation_focus)
            update, response = await active_coordinator.run_turn(
                request, question, session.learner_state, session.history,
                candidates, runtime.questions, remediation=remediation,
            )
        except TurnTimeoutError:
            raise HTTPException(504, "Learning turn timed out. Start a new session.") from None
        except IntegrationError:
            raise HTTPException(500, "Learning activity configuration error. Start a new session.") from None
        entry = HistoryEntry(question_id=question.question_id,
                             evidence_applied=update.evidence_applied,
                             candidate_id=response.decision.candidate_id if response.decision else None)
        generated = dict(session.generated_questions)
        if remediation.generated is not None:
            generated[remediation.generated.question.question_id] = remediation.generated
        cards = course_flashcards(runtime.course) if isinstance(runtime, RuntimeCatalog) else demo_flashcards()
        response.flashcards = rank_flashcards(cards, update.concepts, remediation.focus, session.course_id)
        store.save_session(request.session_id, Session(
            response.next_question.question_id if response.next_question else None,
            update.state, [*session.history, entry], session.user_id, session.course_id,
            remediation.focus, generated, session.chat_history,
        ))
        return response

    @router.post("/chat", response_model=ChatResponse)
    async def chat(request: ChatRequest) -> ChatResponse:
        if not request.message.strip():
            raise HTTPException(422, "Enter a message.")
        with session_request(request.session_id):
            try:
                session = store.load_session(request.session_id)
            except KeyError:
                raise HTTPException(404, "Session not found. Start a new session.") from None
            runtime = course_runtime(session.course_id) if session.course_id is not None else catalog
            cards = course_flashcards(runtime.course) if isinstance(runtime, RuntimeCatalog) else demo_flashcards()
            title = runtime.course.title if isinstance(runtime, RuntimeCatalog) else "Intro AI"
            current_concept = next((q.concept_id for q in runtime.questions.values()
                                    if q.question_id == session.question_id), None)
            if session.question_id in session.generated_questions:
                current_concept = session.generated_questions[session.question_id].question.concept_id
            try:
                exchange = await answer_message(request, cards, title, current_concept, session)
            except ProviderError:
                raise HTTPException(503, "The tutor is unavailable. Please retry your message.") from None
            store.save_session(request.session_id, replace(
                session, chat_history=[*session.chat_history, exchange][-12:]))
            return ChatResponse(session_id=request.session_id, **exchange.model_dump())

    return router
