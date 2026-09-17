"""Provider adapter seam: one normalized complete(...) call for fake/Bedrock.

Teaching calls this instead of importing provider SDKs directly. Fake mode stays
local; Bedrock runs in a worker thread with a bounded caller deadline.
"""
import asyncio
import json
import math
import logging
import os
import time
from dataclasses import dataclass
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Literal


logger = logging.getLogger("uvicorn.error.provider")
_deadline: ContextVar[float | None] = ContextVar("provider_deadline", default=None)
ProviderPurpose = Literal["interactive", "course_ingestion"]
_TIMEOUT_SETTINGS = {
    "interactive": ("BEDROCK_TIMEOUT_SECONDS", "12", 15),
    "course_ingestion": ("BEDROCK_INGESTION_TIMEOUT_SECONDS", "60", 90),
}


@contextmanager
def call_budget(seconds: float):
    """Cap provider waits in this task; nested budgets cannot extend a deadline."""
    deadline = time.monotonic() + seconds
    parent = _deadline.get()
    token = _deadline.set(min(deadline, parent) if parent is not None else deadline)
    try:
        yield
    finally:
        _deadline.reset(token)


def log_configuration(event: str, *, purpose: ProviderPurpose = "interactive") -> None:
    # Only these non-secret configuration fields are diagnostic output. Never
    # dump the environment, SDK exceptions, request/response bodies or headers.
    setting, default, _ = _TIMEOUT_SETTINGS[purpose]
    logger.info("%s pid=%s configured_provider=%r configured_model=%r region=%r timeout_seconds=%r purpose=%s",
                event, os.getpid(), os.environ.get("MODEL_PROVIDER", "fake"),
                os.environ.get("BEDROCK_MODEL_ID"), os.environ.get("AWS_REGION"),
                os.environ.get(setting, default), purpose)


@dataclass
class ProviderResult:
    text: str
    provider: str
    model: str
    latency_ms: float


class ProviderError(RuntimeError):
    """A failed/timed-out provider call. Callers use a curated fallback; never
    silently retry against a different provider (AWS.md)."""


async def complete(prompt: str, *, system: str | None = None, max_tokens: int = 512,
                   purpose: ProviderPurpose = "interactive",
                   response_schema: dict | None = None) -> ProviderResult:
    if purpose not in _TIMEOUT_SETTINGS:
        raise ProviderError("Unsupported provider call purpose")
    provider = os.environ.get("MODEL_PROVIDER", "fake")
    if provider == "fake":
        return _complete_fake(prompt)
    if provider == "bedrock":
        log_configuration("provider_attempt", purpose=purpose)
        return await _complete_bedrock(prompt, system=system, max_tokens=max_tokens, purpose=purpose,
                                       response_schema=response_schema)
    raise ProviderError(f"Unsupported MODEL_PROVIDER: {provider!r}")


def _complete_fake(prompt: str) -> ProviderResult:
    return ProviderResult(text=f"[fake provider echo] {prompt}", provider="fake", model="fake", latency_ms=0.0)


async def _complete_bedrock(prompt: str, *, system: str | None, max_tokens: int,
                            purpose: ProviderPurpose, response_schema: dict | None = None) -> ProviderResult:
    setting, default, maximum = _TIMEOUT_SETTINGS[purpose]
    try:
        timeout = float(os.environ.get(setting, default))
        if not math.isfinite(timeout) or not 0 < timeout <= maximum:
            raise ValueError("timeout outside configured purpose budget")
        region = os.environ["AWS_REGION"]
        model_id = os.environ["BEDROCK_MODEL_ID"]
    except (ValueError, KeyError) as exc:
        logger.warning("provider_failed reason=configuration_error")
        raise ProviderError(f"Bedrock requires region, model and {setting} in (0, {maximum}] seconds") from exc
    try:
        deadline = _deadline.get()
        if deadline is not None:
            timeout = min(timeout, deadline - time.monotonic())
        if timeout <= 0:
            raise TimeoutError("Provider budget exhausted")
        result = await asyncio.wait_for(asyncio.to_thread(
            _converse, prompt, system=system, max_tokens=max_tokens,
            region=region, model_id=model_id, timeout=timeout, response_schema=response_schema,
        ), timeout=timeout)
        logger.info("provider_returned provider=bedrock latency_ms=%.1f", result.latency_ms)
        return result
    except TimeoutError as exc:
        # Cancellation cannot kill an SDK thread. Its eventual result is ignored;
        # socket deadlines and disabled SDK retries also bound ordinary I/O.
        logger.warning("provider_failed reason=timeout")
        raise ProviderError("Bedrock request timed out") from exc
    except Exception as exc:
        # SDK error messages can contain request data. Log only fixed categories.
        from botocore.exceptions import ClientError, ConnectTimeoutError, NoCredentialsError, ReadTimeoutError
        reason = "provider_error"
        if isinstance(exc, (ConnectTimeoutError, ReadTimeoutError)):
            reason = "timeout"
        elif isinstance(exc, NoCredentialsError):
            reason = "credentials_unavailable"
        elif isinstance(exc, ClientError):
            code = exc.response.get("Error", {}).get("Code")
            allowed = {"ExpiredTokenException", "UnrecognizedClientException", "AccessDeniedException",
                       "ValidationException", "ThrottlingException", "ServiceUnavailableException",
                       "ModelTimeoutException", "ModelErrorException", "ResourceNotFoundException"}
            if isinstance(code, str) and code in allowed:
                reason = code
        logger.warning("provider_failed reason=%s", reason)
        raise ProviderError("Bedrock call failed") from exc


def _converse(prompt: str, *, system: str | None, max_tokens: int,
              region: str, model_id: str, timeout: float, response_schema: dict | None = None) -> ProviderResult:
    import boto3  # local import: fake mode never needs boto3 installed
    from botocore.config import Config

    start = time.monotonic()
    client = boto3.client("bedrock-runtime", region_name=region, config=Config(
        connect_timeout=min(5.0, timeout), read_timeout=timeout,
        retries={"total_max_attempts": 1},
    ))
    kwargs = {
        "modelId": model_id,
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "inferenceConfig": {"maxTokens": max_tokens},
    }
    if system:
        kwargs["system"] = [{"text": system}]
    if response_schema is not None:
        kwargs["inferenceConfig"]["temperature"] = 0
        # This tool is an output envelope only. No tool is executed and no
        # follow-up inference is made. The caller still validates its contents.
        kwargs["toolConfig"] = {
            "tools": [{"toolSpec": {"name": "submit_structured_response",
                       "description": "Submit the requested structured response.",
                       "inputSchema": {"json": response_schema}}}],
            "toolChoice": {"tool": {"name": "submit_structured_response"}},
        }
    try:
        logger.info("bedrock_converse_started")
        response = client.converse(**kwargs)
        stop_reason = response.get("stopReason")
        allowed_stops = {"end_turn", "max_tokens", "stop_sequence", "tool_use",
                         "guardrail_intervened", "content_filtered"}
        logger.info("bedrock_response_received stop_reason=%s",
                    stop_reason if isinstance(stop_reason, str) and stop_reason in allowed_stops else "unknown")
        content = response["output"]["message"]["content"]
        if response_schema is not None:
            uses = [block["toolUse"] for block in content if "toolUse" in block]
            if (stop_reason != "tool_use" or len(uses) != 1
                    or uses[0].get("name") != "submit_structured_response"
                    or not isinstance(uses[0].get("input"), dict)):
                raise ValueError("Expected one structured response")
            text = json.dumps(uses[0]["input"], allow_nan=False)
        else:
            text = content[0]["text"]
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Empty Bedrock text")
    finally:
        client.close()
    latency_ms = (time.monotonic() - start) * 1000
    return ProviderResult(text=text, provider="bedrock", model=model_id, latency_ms=latency_ms)
