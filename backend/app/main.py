"""Composition root: deterministic assessment, real learner/policy and Tutor."""
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from backend.app.agents.assessor import FakeAssessor
from backend.app.agents.coordinator import Coordinator
from backend.app.agents.provider import log_configuration
from backend.app.api.routes import router_for
from backend.app.learner.bayesian import BayesianLearner
from backend.app.policy.adaptive import AdaptivePolicy
from backend.app.storage.dynamo import DynamoStore, dynamo_configured
from backend.app.storage.memory import MemoryStore
from backend.app.storage.courses import MemoryCourseRegistry
from backend.app.teaching.catalog import Catalog
from backend.app.teaching.tutor import Tutor


def create_app(coordinator: Coordinator | None = None, *,
               course_registry: MemoryCourseRegistry | None = None) -> FastAPI:
    catalog = Catalog()
    coordinator = coordinator or Coordinator(FakeAssessor(), BayesianLearner(), AdaptivePolicy(), Tutor(catalog))
    log_configuration("runtime_start")
    app = FastAPI(title="Minds & Machines — learning lab", docs_url=None, redoc_url=None)
    store = DynamoStore() if dynamo_configured() else MemoryStore()
    course_registry = course_registry if course_registry is not None else MemoryCourseRegistry()
    app.include_router(router_for(coordinator, store, catalog, course_registry))
    frontend = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if frontend.exists():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app


app = create_app()
