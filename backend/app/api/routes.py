from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import replace
from uuid import uuid4
from backend.app.learner.bayesian import BayesianLearner
from backend.app.policy.focus import coach_context
from backend.app.teaching.focus_questions import apply_focus_questions, generate_focus_questions, record_exposure, already_exposed
from backend.app.policy.practice import PracticeSelection, session_budget, has_pools
from backend.app.teaching.chat import answer_message
from backend.app.agents.provider import ProviderError
from fastapi import APIRouter, Body, Header, HTTPException
from backend.app.agents.coordinator import Coordinator, IntegrationError, TurnTimeoutError
from backend.app.auth.cognito import AuthError, cognito_enabled, verify_id_token
from backend.app.storage.dynamo import DynamoStore
from backend.app.storage.memory import MemoryStore, Session, LearnerProfile
from backend.app.storage.courses import MemoryCourseRegistry
from backend.app.teaching.catalog import Catalog
from backend.app.teaching.flashcards import demo_flashcards, course_flashcards
from backend.app.teaching.remediation import RemediationTurn, rank_flashcards
from backend.app.ingestion.models import IngestionError
from backend.app.teaching.runtime_catalog import RuntimeAvailability, RuntimeCatalog, build_runtime_catalog
from contracts.models import FocusRequest, PracticeCounts, ChatRequest, ChatResponse, HistoryEntry, SessionRequest, SessionResponse, TurnRequest, TurnResponse


def router_for(coordinator: Coordinator, store: MemoryStore | DynamoStore, catalog: Catalog,
               course_registry: MemoryCourseRegistry,
               course_coordinator: Callable[[RuntimeCatalog, RuntimeAvailability], Coordinator]) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    active_sessions: set[str] = set()

    @contextmanager
    def session_request(session_id: str):
        # Single-process demo: reject overlapping writes instead of queuing a
        # request with stale question/context. Always release on failure.
        try:
            stored = store.load_session(session_id)
            lock_id = stored.profile_id or session_id
            if stored.profile_id and store.load_profile(stored.profile_id).active_session_id != session_id:
                raise HTTPException(409, "This practice session has been replaced. Use the current session.")
        except KeyError:
            lock_id = session_id
        if lock_id in active_sessions:
            raise HTTPException(409, "A request is already running for this session.")
        active_sessions.add(lock_id)
        try:
            yield
        finally:
            active_sessions.discard(lock_id)

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
        profile_id = str(uuid4())
        profile = LearnerProfile(initial.state, request.course_id, user_id)
        previous = None
        if request.previous_session_id:
            try:
                previous = store.load_session(request.previous_session_id)
                if previous.course_id != request.course_id or previous.user_id != user_id:
                    raise HTTPException(400, "The previous session belongs to another learner or course.")
                if previous.profile_id:
                    profile_id = previous.profile_id
                    profile = store.load_profile(profile_id)
            except KeyError:
                raise HTTPException(404, "Session not found. Start a new session.") from None
        elif request.reset_learner:
            raise HTTPException(400, "Choose the learner profile to reset.")
        with session_request(request.previous_session_id or profile_id):
            if request.reset_learner:
                profile = LearnerProfile(initial.state, request.course_id, user_id)
            elif previous is not None:
                profile.session_number += 1
            initial = BayesianLearner().describe(profile.state)
            runtime = course_catalog if request.course_id else catalog
            if request.course_id:
                apply_focus_questions(runtime, profile)
            budget = session_budget(runtime) if request.course_id else question_count
            if request.course_id and (has_pools(runtime) or previous is not None):
                selection = PracticeSelection(profile.recent, profile.session_number, budget, profile.first_question_id, exposed=profile.exposed)
                question = selection.pick(runtime, initial.concepts, [])
            elif previous is not None:
                choices = [q for q in catalog.questions.values() if q.question_id != profile.first_question_id]
                question = min(choices or list(catalog.questions.values()), key=lambda q:
                               profile.recent.index(q.question_id) if q.question_id in profile.recent else -1)
            public = question.public()
            public.review = already_exposed(profile, question)
            # Issued questions count as exposed, even if a session is abandoned.
            record_exposure(profile, question)
            session_id = str(uuid4())
            profile.active_session_id = session_id
            profile.first_question_id = question.question_id
            session = Session(question.question_id, initial.state, user_id=user_id,
                              course_id=request.course_id, profile_id=profile_id,
                              session_start=initial.state.model_copy(deep=True), budget=budget)
            # Current question freshness is stored separately from the exposure
            # ledger (which reserves it immediately on issue).
            session.current_review = public.review
            store.save_progress(session_id, session, profile_id, profile)
            cards = rank_flashcards(cards, initial.concepts, None, request.course_id)
            if profile.session_number:
                # Rotate within each concept without changing mastery priority.
                groups = {}
                for card in cards:
                    groups.setdefault(card.concept_id, []).append(card)
                cards = [card for group in groups.values()
                         for card in group[profile.session_number % len(group):] + group[:profile.session_number % len(group)]]
            return SessionResponse(session_id=session_id, course_id=request.course_id,
                                   question=public, concepts=initial.concepts,
                                   session_start=initial.concepts, question_count=budget,
                                   counts=PracticeCounts(unique_questions_seen=1, lifetime_evidence=sum(c.evidence_count for c in initial.concepts)),
                                   analytics=coach_context(runtime, initial.concepts, session, profile), flashcards=cards)

    @router.post("/focus-practice", response_model=SessionResponse, status_code=201)
    async def focus_practice(request: FocusRequest) -> SessionResponse:
        with session_request(request.session_id):
            try:
                previous = store.load_session(request.session_id)
            except KeyError:
                raise HTTPException(404, "Session not found.") from None
            if not previous.course_id or not previous.profile_id:
                raise HTTPException(400, "Focus practice needs uploaded course sources.")
            runtime = course_runtime(previous.course_id)
            if request.concept_id not in runtime.concept_ids:
                raise HTTPException(400, "Unknown course concept.")
            profile = store.load_profile(previous.profile_id)
            apply_focus_questions(runtime, profile)
            choices = [q for q in runtime.questions.values() if q.concept_id == request.concept_id]
            def fresh(q):
                return not already_exposed(profile, q)
            unseen = [q for q in choices if fresh(q)]
            if len(unseen) < 3:
                records = await generate_focus_questions(runtime, request.concept_id, profile, 3 - len(unseen))
                for record in records:
                    profile.focus_questions[record["question"]["question_id"]] = record
                apply_focus_questions(runtime, profile)
                choices = [q for q in runtime.questions.values() if q.concept_id == request.concept_id]
                unseen = [q for q in choices if fresh(q)]
            # Never pad a partly fresh set with review. A smaller set is honest.
            selected = unseen[:3] if unseen else sorted(choices, key=lambda q:
                profile.recent.index(q.question_id) if q.question_id in profile.recent else -1)[:3]
            if not selected:
                raise HTTPException(409, "No safe practice questions are available.")
            notice = (f"{len(selected)} fresh questions. Your existing learner model continues."
                      if unseen else "Only review items remain; no safe fresh questions survived. Review adds no new mastery evidence.")
            initial = BayesianLearner().describe(profile.state)
            question = selected[0]
            public = question.public()
            public.review = not fresh(question)
            record_exposure(profile, question)
            session_id = str(uuid4())
            profile.active_session_id = session_id
            profile.session_number += 1
            session = Session(question.question_id, initial.state, user_id=previous.user_id,
                course_id=previous.course_id, profile_id=previous.profile_id,
                session_start=initial.state.model_copy(deep=True), budget=len(selected),
                current_review=public.review, session_kind="focus", focus_concept_id=request.concept_id,
                focus_question_ids=[q.question_id for q in selected])
            store.save_progress(session_id, session, previous.profile_id, profile)
            analytics = coach_context(runtime, initial.concepts, session, profile)
            cards = rank_flashcards(course_flashcards(runtime.course), initial.concepts, None, previous.course_id)
            return SessionResponse(session_id=session_id, course_id=previous.course_id,
                question=public, concepts=initial.concepts, session_start=initial.concepts,
                question_count=len(selected), counts=PracticeCounts(unique_questions_seen=1,
                    lifetime_evidence=sum(c.evidence_count for c in initial.concepts)),
                flashcards=cards, analytics=analytics, session_kind="focus",
                focus_concept_id=request.concept_id, practice_notice=notice)

    @router.post("/turns", response_model=TurnResponse)
    async def turn(request: TurnRequest) -> TurnResponse:
        with session_request(request.session_id):
            return await run_turn(request)

    async def run_turn(request: TurnRequest) -> TurnResponse:
        try:
            session = store.load_session(request.session_id)
        except KeyError:
            raise HTTPException(404, "Session not found. Start a new session.") from None
        profile = store.load_profile(session.profile_id) if session.profile_id else None
        runtime = course_runtime(session.course_id) if session.course_id is not None else catalog
        if isinstance(runtime, RuntimeCatalog):
            try:
                runtime.apply_session_questions(session.generated_questions)
                if profile:
                    apply_focus_questions(runtime, profile)
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
            consumed = {entry.question_id for entry in session.history} | {question.question_id}
            candidates = [c for c in runtime.candidates if c.next_question_id not in consumed]
            if isinstance(runtime, RuntimeCatalog):
                if (set(session.learner_state.skills) != set(runtime.concept_ids)
                        or request.question_id in {entry.question_id for entry in session.history}):
                    raise IntegrationError("Course session state does not match its current activity")
                try:
                    availability = runtime.eligible_candidates(
                        current_question_id=request.question_id,
                        consumed_question_ids=[entry.question_id for entry in session.history],
                        consumed_candidate_ids=[entry.candidate_id for entry in session.history
                                                if entry.candidate_id is not None and not has_pools(runtime)
                                                and session.session_kind != "focus" and not (profile and profile.focus_questions)],
                    )
                except ValueError as exc:
                    raise IntegrationError("Course history contains foreign IDs") from exc
                candidates = list(availability.candidates)
                active_coordinator = course_coordinator(runtime, availability)
            if profile is not None:
                active_coordinator = replace(active_coordinator, evidence_eligible=not session.current_review)
                if isinstance(runtime, RuntimeCatalog) and (has_pools(runtime) or session.session_kind == "focus" or profile.focus_questions):
                    active_coordinator.practice_selection = PracticeSelection(
                        profile.recent, profile.session_number, session.budget,
                        allowed_ids=session.focus_question_ids if session.session_kind == "focus" else None,
                        exposed=profile.exposed)
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
                             candidate_id=response.decision.candidate_id if response.decision else None, review=session.current_review)
        generated = dict(session.generated_questions)
        if remediation.generated is not None:
            generated[remediation.generated.question.question_id] = remediation.generated
        cards = course_flashcards(runtime.course) if isinstance(runtime, RuntimeCatalog) else demo_flashcards()
        response.flashcards = rank_flashcards(cards, update.concepts, remediation.focus, session.course_id)
        updated_session = replace(session,
            question_id=response.next_question.question_id if response.next_question else None,
            learner_state=update.state, history=[*session.history, entry],
            remediation_focus=remediation.focus, generated_questions=generated)
        if profile is not None:
            profile.state = update.state
            if response.next_question:
                next_item = (remediation.generated.question if remediation.generated is not None
                             else runtime.questions[response.next_question.question_id])
                review = already_exposed(profile, next_item)
                response.next_question.review = review
                updated_session.current_review = review
                record_exposure(profile, next_item)
            store.save_progress(request.session_id, updated_session, session.profile_id, profile)
        else:
            store.save_session(request.session_id, updated_session)
        response.counts = PracticeCounts(
            submitted_answers=len(updated_session.history),
            unique_questions_seen=len({h.question_id for h in updated_session.history}
                                      | ({updated_session.question_id} if updated_session.question_id else set())),
            accepted_observations=sum(h.evidence_applied for h in updated_session.history),
            review_attempts=sum(h.review for h in updated_session.history),
            focus_observations=sum(h.evidence_applied for h in updated_session.history) if session.session_kind == "focus" else 0,
            lifetime_evidence=sum(c.evidence_count for c in update.concepts))
        response.session_start = BayesianLearner().describe(session.session_start or session.learner_state).concepts
        response.analytics = coach_context(runtime, update.concepts, updated_session, profile)
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
            profile = store.load_profile(session.profile_id) if session.profile_id else None
            if isinstance(runtime, RuntimeCatalog) and profile:
                apply_focus_questions(runtime, profile)
            current_concept = next((q.concept_id for q in runtime.questions.values()
                                    if q.question_id == session.question_id), None)
            if session.question_id in session.generated_questions:
                current_concept = session.generated_questions[session.question_id].question.concept_id
            analytics = coach_context(runtime, BayesianLearner().describe(session.learner_state).concepts, session, profile)
            try:
                exchange = await answer_message(request, cards, title, current_concept, session, analytics)
            except ProviderError:
                raise HTTPException(503, "The tutor is unavailable. Please retry your message.") from None
            store.save_session(request.session_id, replace(
                session, chat_history=[*session.chat_history, exchange][-12:]))
            from backend.app.teaching.chat import requested_concept
            return ChatResponse(session_id=request.session_id, **exchange.model_dump(), analytics=analytics,
                                practice_concept_id=requested_concept(request.message, analytics) if session.course_id else None)

    return router
