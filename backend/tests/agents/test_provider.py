import asyncio
import json
import os
import threading
import time
import unittest
from unittest.mock import patch

from backend.app.agents.provider import ProviderError, call_budget, complete


class ProviderSeamTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"MODEL_PROVIDER": "fake"})
        env.start()
        self.addCleanup(env.stop)

    def test_fake_is_the_default_provider(self):
        result = asyncio.run(complete("hello"))
        self.assertEqual(result.provider, "fake")
        self.assertIn("hello", result.text)

    def test_unknown_provider_raises(self):
        import os
        os.environ["MODEL_PROVIDER"] = "not-a-real-provider"
        try:
            with self.assertRaises(ProviderError):
                asyncio.run(complete("hello"))
        finally:
            del os.environ["MODEL_PROVIDER"]


class BedrockProviderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        env = patch.dict(os.environ, {
            "MODEL_PROVIDER": "bedrock", "AWS_REGION": "us-east-1",
            "BEDROCK_MODEL_ID": "test-model", "BEDROCK_TIMEOUT_SECONDS": "1",
        })
        env.start()
        self.addCleanup(env.stop)
        client_patch = patch("boto3.client")
        self.factory = client_patch.start()
        self.addCleanup(client_patch.stop)
        self.client = self.factory.return_value
        self.client.converse.return_value = {"output": {"message": {"content": [{"text": "hello"}]}}}

    async def test_normalized_result_and_single_attempt_sdk_config(self):
        result = await complete("prompt", system="system", max_tokens=123)
        self.assertEqual((result.text, result.provider, result.model), ("hello", "bedrock", "test-model"))
        self.assertGreaterEqual(result.latency_ms, 0)
        self.client.converse.assert_called_once_with(
            modelId="test-model", messages=[{"role": "user", "content": [{"text": "prompt"}]}],
            system=[{"text": "system"}], inferenceConfig={"maxTokens": 123})
        config = self.factory.call_args.kwargs["config"]
        self.assertEqual(config.retries, {"total_max_attempts": 1})
        self.assertLessEqual(config.connect_timeout, 1)
        self.assertEqual(config.read_timeout, 1)
        self.client.close.assert_called_once()

    async def test_structured_response_uses_one_forced_tool_and_preserves_json_strings(self):
        schema = {"type": "object", "properties": {"prompt": {"type": "string"}}, "required": ["prompt"]}
        payload = {"prompt": 'Explain "f(x)" with \\ notation.\nA second line.'}
        self.client.converse.return_value = {"stopReason": "tool_use", "output": {"message": {"content": [
            {"text": "Ignored commentary; never parsed as JSON."},
            {"toolUse": {"toolUseId": "mock", "name": "submit_structured_response", "input": payload}},
        ]}}}
        result = await complete("course", purpose="course_ingestion", response_schema=schema)
        self.assertEqual(json.loads(result.text), payload)
        self.client.converse.assert_called_once()
        config = self.client.converse.call_args.kwargs["toolConfig"]
        self.assertEqual(self.client.converse.call_args.kwargs["inferenceConfig"]["temperature"], 0)
        self.assertEqual(config["toolChoice"], {"tool": {"name": "submit_structured_response"}})
        self.assertEqual(config["tools"][0]["toolSpec"]["inputSchema"], {"json": schema})
        self.client.close.assert_called_once()

    async def test_missing_multiple_wrong_or_truncated_structured_responses_fail_without_retry(self):
        valid = {"toolUse": {"name": "submit_structured_response", "input": {"concepts": []}}}
        for stop, blocks in (
            ("end_turn", [{"text": '{"concepts":[]}'}]),
            ("tool_use", [valid, valid]),
            ("tool_use", [{"toolUse": {"name": "other_tool", "input": {}}}]),
            ("tool_use", [{"toolUse": {"name": "submit_structured_response", "input": "not an object"}}]),
            ("max_tokens", [valid]),
        ):
            self.client.converse.reset_mock()
            self.client.converse.return_value = {"stopReason": stop, "output": {"message": {"content": blocks}}}
            with self.subTest(stop=stop, blocks=len(blocks)), self.assertRaises(ProviderError):
                await complete("course", purpose="course_ingestion", response_schema={"type": "object"})
            self.client.converse.assert_called_once()

    async def test_ingestion_has_its_own_bounded_timeout_and_does_not_change_interactive_calls(self):
        with patch.dict(os.environ, {"BEDROCK_INGESTION_TIMEOUT_SECONDS": "60"}):
            with self.assertLogs("uvicorn.error.provider", level="INFO") as logs:
                await complete("course", purpose="course_ingestion", max_tokens=6000)
            config = self.factory.call_args.kwargs["config"]
            self.assertEqual(config.read_timeout, 60)
            self.assertEqual(config.connect_timeout, 5)
            self.assertEqual(config.retries, {"total_max_attempts": 1})
            self.assertIn("timeout_seconds='60' purpose=course_ingestion", "\n".join(logs.output))
            await complete("tutor")
            self.assertEqual(self.factory.call_args.kwargs["config"].read_timeout, 1)

    async def test_course_can_finish_after_interactive_deadline_without_retry(self):
        def slow_response(**kwargs):
            time.sleep(0.05)
            return {"output": {"message": {"content": [{"text": "course"}]}}}

        self.client.converse.side_effect = slow_response
        with patch.dict(os.environ, {"BEDROCK_TIMEOUT_SECONDS": "0.01",
                                    "BEDROCK_INGESTION_TIMEOUT_SECONDS": "0.5"}):
            result = await complete("course", purpose="course_ingestion")
            self.assertEqual(result.text, "course")
            self.client.converse.assert_called_once()
            with self.assertRaisesRegex(ProviderError, "timed out"):
                await complete("interactive")

    async def test_ingestion_configuration_is_bounded_and_respects_parent_deadline(self):
        for value in ("0", "-1", "nan", "inf", "91", "bad"):
            with self.subTest(value=value), patch.dict(os.environ, {"BEDROCK_INGESTION_TIMEOUT_SECONDS": value}):
                with self.assertRaises(ProviderError):
                    await complete("course", purpose="course_ingestion")
        self.factory.assert_not_called()
        with patch.dict(os.environ, {"BEDROCK_INGESTION_TIMEOUT_SECONDS": "90"}), call_budget(0.5):
            await complete("course", purpose="course_ingestion")
            self.assertLessEqual(self.factory.call_args.kwargs["config"].read_timeout, 0.5)

    async def test_ingestion_uses_sixty_seconds_when_unconfigured(self):
        with patch.dict(os.environ):
            os.environ.pop("BEDROCK_INGESTION_TIMEOUT_SECONDS", None)
            await complete("course", purpose="course_ingestion")
        self.assertEqual(self.factory.call_args.kwargs["config"].read_timeout, 60)

    async def test_blocked_sdk_does_not_block_loop_and_times_out(self):
        started = threading.Event()
        release = threading.Event()
        finished = threading.Event()
        loop_thread = threading.get_ident()

        def blocked(**kwargs):
            self.assertNotEqual(threading.get_ident(), loop_thread)
            started.set()
            try:
                release.wait(2)
                return {"output": {"message": {"content": [{"text": "late"}]}}}
            finally:
                finished.set()

        self.client.converse.side_effect = blocked
        with patch.dict(os.environ, {"BEDROCK_TIMEOUT_SECONDS": "0.05"}):
            task = asyncio.create_task(complete("prompt"))
            try:
                for _ in range(100):
                    if started.is_set():
                        break
                    await asyncio.sleep(0.001)
                self.assertTrue(started.is_set())
                # This assertion runs while the synchronous SDK call is pending.
                self.assertFalse(finished.is_set())
                with self.assertLogs("uvicorn.error.provider", level="INFO") as captured:
                    with self.assertRaisesRegex(ProviderError, "timed out"):
                        await task
                self.assertIn("provider_failed reason=timeout", "\n".join(captured.output))
                self.assertFalse(finished.is_set())
                self.client.converse.assert_called_once()
            finally:
                release.set()
                await asyncio.to_thread(finished.wait, 2)

    async def test_setup_sdk_and_response_failures_are_normalized(self):
        for malformed in [{}, {"output": {"message": {"content": [{"text": None}]}}}]:
            self.client.converse.return_value = malformed
            with self.assertRaises(ProviderError):
                await complete("prompt")
        self.client.converse.side_effect = RuntimeError("SDK error")
        with self.assertRaises(ProviderError):
            await complete("prompt")
        self.factory.side_effect = RuntimeError("client setup error")
        with self.assertRaises(ProviderError):
            await complete("prompt")

    async def test_invalid_configuration_never_starts_sdk(self):
        for timeout in ["0", "-1", "nan", "inf", "16", "bad"]:
            with self.subTest(timeout=timeout), patch.dict(os.environ, {"BEDROCK_TIMEOUT_SECONDS": timeout}):
                with self.assertRaises(ProviderError):
                    await complete("prompt")
        with patch.dict(os.environ):
            del os.environ["AWS_REGION"]
            with self.assertRaises(ProviderError):
                await complete("prompt")
        self.factory.assert_not_called()

    async def test_nested_budget_caps_socket_timeout_and_restores_parent(self):
        with call_budget(0.5):
            with call_budget(10):
                await complete("nested")
                self.assertLessEqual(self.factory.call_args.kwargs["config"].read_timeout, 0.5)
            with call_budget(0.1):
                await complete("shorter")
                self.assertLessEqual(self.factory.call_args.kwargs["config"].read_timeout, 0.1)
            await complete("parent")
            self.assertGreater(self.factory.call_args.kwargs["config"].read_timeout, 0.1)
        await complete("outside")
        self.assertEqual(self.factory.call_args.kwargs["config"].read_timeout, 1)

    async def test_exhausted_budget_starts_no_worker_and_resets_after_error(self):
        with call_budget(0):
            with self.assertRaises(ProviderError):
                await complete("exhausted")
        self.factory.assert_not_called()
        await complete("new turn")
        self.client.converse.assert_called_once()

    async def test_budget_is_isolated_between_tasks(self):
        scoped = asyncio.Event()
        checked = asyncio.Event()

        async def exhausted_task():
            with call_budget(0):
                scoped.set()
                await checked.wait()
                with self.assertRaises(ProviderError):
                    await complete("exhausted")

        async def ordinary_task():
            await scoped.wait()
            try:
                await complete("ordinary")
                self.assertEqual(self.factory.call_args.kwargs["config"].read_timeout, 1)
            finally:
                checked.set()

        await asyncio.gather(exhausted_task(), ordinary_task())
        self.client.converse.assert_called_once()
