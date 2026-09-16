import asyncio
import unittest

from backend.app.agents.provider import ProviderError, complete


class ProviderSeamTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
