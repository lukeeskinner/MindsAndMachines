"""Provider adapter seam: one normalized complete(...) call for fake/Bedrock.

Assessment and Teaching call this instead of importing provider SDKs directly
(AWS.md "Provider seam"; CONTRACTS.md "Provider boundary"). Not wired into the
G1 composition root; FakeAssessor/FakeLearner/FakePolicy/FakeTutor remain the
default in backend/app/main.py until G2 wiring is authorized.
"""
import os
import time
from dataclasses import dataclass


@dataclass
class ProviderResult:
    text: str
    provider: str
    model: str
    latency_ms: float


class ProviderError(RuntimeError):
    """A failed/timed-out provider call. Callers use a curated fallback; never
    silently retry against a different provider (AWS.md)."""


async def complete(prompt: str, *, system: str | None = None, max_tokens: int = 512) -> ProviderResult:
    provider = os.environ.get("MODEL_PROVIDER", "fake")
    if provider == "fake":
        return _complete_fake(prompt)
    if provider == "bedrock":
        return await _complete_bedrock(prompt, system=system, max_tokens=max_tokens)
    raise ProviderError(f"Unsupported MODEL_PROVIDER: {provider!r}")


def _complete_fake(prompt: str) -> ProviderResult:
    return ProviderResult(text=f"[fake provider echo] {prompt}", provider="fake", model="fake", latency_ms=0.0)


async def _complete_bedrock(prompt: str, *, system: str | None, max_tokens: int) -> ProviderResult:
    import boto3  # local import: fake mode never needs boto3 installed

    region = os.environ["AWS_REGION"]
    model_id = os.environ["BEDROCK_MODEL_ID"]
    client = boto3.client("bedrock-runtime", region_name=region)
    kwargs = {
        "modelId": model_id,
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "inferenceConfig": {"maxTokens": max_tokens},
    }
    if system:
        kwargs["system"] = [{"text": system}]
    start = time.monotonic()
    try:
        response = client.converse(**kwargs)
    except Exception as exc:  # noqa: BLE001 - normalized into ProviderError for callers
        raise ProviderError(f"Bedrock call failed: {exc}") from exc
    latency_ms = (time.monotonic() - start) * 1000
    text = response["output"]["message"]["content"][0]["text"]
    return ProviderResult(text=text, provider="bedrock", model=model_id, latency_ms=latency_ms)
