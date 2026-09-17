"""Provider adapter seam: one normalized complete(...) call for fake/Bedrock.

Teaching calls this instead of importing provider SDKs directly. Fake mode stays
local; Bedrock runs in a worker thread with a bounded caller deadline.
"""
import asyncio
import math
import logging
import os
import time
from dataclasses import dataclass
from contextlib import contextmanager
from contextvars import ContextVar


logger = logging.getLogger("uvicorn.error.provider")
_deadline: ContextVar[float | None] = ContextVar("provider_deadline", default=None)


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


def log_configuration(event: str) -> None:
    # Only these non-secret configuration fields are diagnostic output. Never
    # dump the environment, SDK exceptions, request/response bodies or headers.
    logger.info("%s pid=%s configured_provider=%r configured_model=%r region=%r timeout_seconds=%r",
                event, os.getpid(), os.environ.get("MODEL_PROVIDER", "fake"),
                os.environ.get("BEDROCK_MODEL_ID"), os.environ.get("AWS_REGION"),
                os.environ.get("BEDROCK_TIMEOUT_SECONDS", "12"))


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
        log_configuration("provider_attempt")
        return await _complete_bedrock(prompt, system=system, max_tokens=max_tokens)
    raise ProviderError(f"Unsupported MODEL_PROVIDER: {provider!r}")


def _complete_fake(prompt: str) -> ProviderResult:
    return ProviderResult(text=f"[fake provider echo] {prompt}", provider="fake", model="fake", latency_ms=0.0)


async def _complete_bedrock(prompt: str, *, system: str | None, max_tokens: int) -> ProviderResult:
    try:
        timeout = float(os.environ.get("BEDROCK_TIMEOUT_SECONDS", "12"))
        if not math.isfinite(timeout) or not 0 < timeout <= 15:
            raise ValueError("timeout outside interactive budget")
        region = os.environ["AWS_REGION"]
        model_id = os.environ["BEDROCK_MODEL_ID"]
    except (ValueError, KeyError) as exc:
        logger.warning("provider_failed reason=configuration_error")
        raise ProviderError("Bedrock requires region, model and a timeout in (0, 15] seconds") from exc
    try:
        deadline = _deadline.get()
        if deadline is not None:
            timeout = min(timeout, deadline - time.monotonic())
        if timeout <= 0:
            raise TimeoutError("Provider budget exhausted")
        result = await asyncio.wait_for(asyncio.to_thread(
            _converse, prompt, system=system, max_tokens=max_tokens,
            region=region, model_id=model_id, timeout=timeout,
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
              region: str, model_id: str, timeout: float) -> ProviderResult:
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
    try:
        logger.info("bedrock_converse_started")
        response = client.converse(**kwargs)
        stop_reason = response.get("stopReason")
        allowed_stops = {"end_turn", "max_tokens", "stop_sequence", "tool_use",
                         "guardrail_intervened", "content_filtered"}
        logger.info("bedrock_response_received stop_reason=%s",
                    stop_reason if isinstance(stop_reason, str) and stop_reason in allowed_stops else "unknown")
        text = response["output"]["message"]["content"][0]["text"]
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Empty Bedrock text")
    finally:
        client.close()
    latency_ms = (time.monotonic() - start) * 1000
    return ProviderResult(text=text, provider="bedrock", model=model_id, latency_ms=latency_ms)
