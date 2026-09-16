"""Composition root: real learner/policy with deterministic assessment/teaching."""
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from backend.app.agents.assessor import FakeAssessor
from backend.app.agents.coordinator import Coordinator
from backend.app.api.routes import router_for
from backend.app.learner.bayesian import BayesianLearner
from backend.app.policy.adaptive import AdaptivePolicy
from backend.app.storage.memory import MemoryStore
from backend.app.teaching.catalog import Catalog
from backend.app.teaching.fake import FakeTutor


def create_app(coordinator: Coordinator | None = None) -> FastAPI:
    catalog = Catalog()
    coordinator = coordinator or Coordinator(FakeAssessor(), BayesianLearner(), AdaptivePolicy(), FakeTutor(catalog))
    app = FastAPI(title="Minds & Machines — learning lab", docs_url=None, redoc_url=None)
    app.include_router(router_for(coordinator, MemoryStore(), catalog))
    frontend = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if frontend.exists():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app


app = create_app()
