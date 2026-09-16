import os
import unittest

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


if __name__ == "__main__":
    unittest.main()
