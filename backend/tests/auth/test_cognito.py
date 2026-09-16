import os
import time
import unittest
from unittest.mock import patch

from backend.app.auth.cognito import AuthError, cognito_enabled, verify_id_token


class CognitoDisabledByDefaultTests(unittest.TestCase):
    def setUp(self):
        for key in ("COGNITO_USER_POOL_ID", "COGNITO_APP_CLIENT_ID"):
            os.environ.pop(key, None)

    def test_disabled_when_env_vars_are_unset(self):
        self.assertFalse(cognito_enabled())

    def test_verify_raises_when_not_configured(self):
        with self.assertRaises(AuthError):
            verify_id_token("Bearer whatever")


class CognitoTokenShapeTests(unittest.TestCase):
    def setUp(self):
        os.environ["AWS_REGION"] = "us-east-1"
        os.environ["COGNITO_USER_POOL_ID"] = "us-east-1_test"
        os.environ["COGNITO_APP_CLIENT_ID"] = "test-client"

    def tearDown(self):
        for key in ("AWS_REGION", "COGNITO_USER_POOL_ID", "COGNITO_APP_CLIENT_ID"):
            os.environ.pop(key, None)

    def test_enabled_once_configured(self):
        self.assertTrue(cognito_enabled())

    def test_missing_bearer_prefix_rejected(self):
        with self.assertRaises(AuthError):
            verify_id_token("not-a-bearer-token")

    def test_missing_header_rejected(self):
        with self.assertRaises(AuthError):
            verify_id_token(None)


class ValidTokenVerificationTests(unittest.TestCase):
    """Proves the real signature/claims verification logic works, using a
    locally-generated keypair standing in for Cognito's JWKS -- no AWS
    account or live network call required."""

    @classmethod
    def setUpClass(cls):
        try:
            import jwt
            from cryptography.hazmat.primitives.asymmetric import rsa
        except ImportError:
            raise unittest.SkipTest("pyjwt[crypto] not installed; run `uv sync --project backend`")

        cls.jwt = jwt
        cls.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.issuer = "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_test"
        cls.client_id = "test-client"

    def setUp(self):
        os.environ["AWS_REGION"] = "us-east-1"
        os.environ["COGNITO_USER_POOL_ID"] = "us-east-1_test"
        os.environ["COGNITO_APP_CLIENT_ID"] = self.client_id
        from backend.app.auth import cognito
        cognito._jwk_client.cache_clear()
        self.signing_key_patch = patch(
            "backend.app.auth.cognito._jwk_client",
            return_value=type("FakeJWKClient", (), {
                "get_signing_key_from_jwt": lambda self, token: type(
                    "Key", (), {"key": ValidTokenVerificationTests.private_key.public_key()})(),
            })(),
        )
        self.signing_key_patch.start()

    def tearDown(self):
        self.signing_key_patch.stop()
        for key in ("AWS_REGION", "COGNITO_USER_POOL_ID", "COGNITO_APP_CLIENT_ID"):
            os.environ.pop(key, None)

    def _token(self, **overrides):
        now = int(time.time())
        claims = {
            "iss": self.issuer, "aud": self.client_id, "token_use": "id",
            "sub": "fake-user-sub-123", "iat": now, "exp": now + 3600,
            **overrides,
        }
        return self.jwt.encode(claims, self.private_key, algorithm="RS256")

    def test_valid_token_returns_the_user_sub(self):
        self.assertEqual(verify_id_token(f"Bearer {self._token()}"), "fake-user-sub-123")

    def test_wrong_audience_rejected(self):
        with self.assertRaises(AuthError):
            verify_id_token(f"Bearer {self._token(aud='someone-elses-client')}")

    def test_wrong_issuer_rejected(self):
        with self.assertRaises(AuthError):
            verify_id_token(f"Bearer {self._token(iss='https://not-cognito.example.com')}")

    def test_expired_token_rejected(self):
        with self.assertRaises(AuthError):
            verify_id_token(f"Bearer {self._token(exp=int(time.time()) - 60)}")

    def test_access_token_rejected_id_token_required(self):
        with self.assertRaises(AuthError):
            verify_id_token(f"Bearer {self._token(token_use='access')}")


if __name__ == "__main__":
    unittest.main()
