"""G1 composition root. All four replaceable implementations are deterministic."""
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from backend.app.agents.assessor import FakeAssessor
from backend.app.agents.coordinator import Coordinator
from backend.app.api.routes import router_for
from backend.app.learner.fake import FakeLearner
from backend.app.policy.fake import FakePolicy
from backend.app.storage.memory import MemoryStore
from backend.app.teaching.catalog import Catalog
from backend.app.teaching.fake import FakeTutor


def create_app(coordinator: Coordinator | None = None) -> FastAPI:
    catalog = Catalog()
    coordinator = coordinator or Coordinator(FakeAssessor(), FakeLearner(), FakePolicy(), FakeTutor(catalog))
    app = FastAPI(title="Minds & Machines — deterministic G1", docs_url=None, redoc_url=None)
    app.include_router(router_for(coordinator, MemoryStore(), catalog))
    frontend = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if frontend.exists():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app


app = create_app()
