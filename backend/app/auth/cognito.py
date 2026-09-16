"""Cognito ID-token verification. Optional: only active when COGNITO_USER_POOL_ID
and COGNITO_APP_CLIENT_ID are both set, so the anonymous G1 session model keeps
working unchanged when auth isn't configured (CONTRACTS.md, AWS.md).
"""
import os
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jwt import PyJWKClient


class AuthError(RuntimeError):
    """A missing, malformed or invalid bearer token."""


def _config() -> tuple[str, str, str] | None:
    region = os.environ.get("AWS_REGION")
    pool_id = os.environ.get("COGNITO_USER_POOL_ID")
    client_id = os.environ.get("COGNITO_APP_CLIENT_ID")
    if not (region and pool_id and client_id):
        return None
    return region, pool_id, client_id


def cognito_enabled() -> bool:
    return _config() is not None


@lru_cache(maxsize=1)
def _jwk_client(issuer: str) -> "PyJWKClient":
    from jwt import PyJWKClient  # local import: unconfigured/anonymous path never needs PyJWT installed
    return PyJWKClient(f"{issuer}/.well-known/jwks.json")


def verify_id_token(authorization_header: str | None) -> str:
    """Return the Cognito user's stable `sub` from a valid Bearer ID token."""
    config = _config()
    if config is None:
        raise AuthError("Cognito is not configured")
    region, pool_id, client_id = config
    if not authorization_header or not authorization_header.startswith("Bearer "):
        raise AuthError("Missing bearer token")
    token = authorization_header.removeprefix("Bearer ")
    issuer = f"https://cognito-idp.{region}.amazonaws.com/{pool_id}"
    import jwt  # local import: only needed once a token actually needs verifying
    try:
        signing_key = _jwk_client(issuer).get_signing_key_from_jwt(token)
        claims = jwt.decode(token, signing_key.key, algorithms=["RS256"],
                             audience=client_id, issuer=issuer)
    except jwt.PyJWTError as exc:
        raise AuthError(f"Invalid token: {exc}") from exc
    if claims.get("token_use") != "id":
        raise AuthError("Not an ID token")
    return claims["sub"]
