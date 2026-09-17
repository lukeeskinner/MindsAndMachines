import json
from pathlib import Path
from unittest.mock import AsyncMock, patch
from backend.app.agents.provider import ProviderResult
from backend.app.ingestion import process_course, extract_material
from backend.app.ingestion.passages import build_passages, topic_passages

CALCULUS = Path(__file__).parent / "fixtures/calculus_derivatives_mini_lecture.pdf"


def wording():
    passages = topic_passages(build_passages((extract_material(CALCULUS),)))
    probes = ["What foundational definition describes this concept?",
              "How is the rule interpreted in detail?",
              "Which worked application follows the source example?",
              "What purpose does this technique serve?"]
    return {f"topic_{i+1}_question_{j+1}": {
        "prompt": p.completion_prompt(j),
        "assigned_answer_echo": p.answer_for_slot(j),
        "wrong_option_1": "Every changing quantity always has zero derivative.",
        "wrong_option_2": "Every derivative equals the original input without any operation.",
        "wrong_option_3": "Differentiation always squares the original output.",
    } for i,p in enumerate(passages) for j,prompt in enumerate(probes)}


async def pool_course():
    with patch.dict("os.environ", {"MODEL_PROVIDER": "bedrock"}), patch(
        "backend.app.ingestion.pipeline.provider.complete",
        AsyncMock(return_value=ProviderResult(json.dumps(wording()), "bedrock", "mock", 0))):
        return await process_course([CALCULUS], title="Calculus")
