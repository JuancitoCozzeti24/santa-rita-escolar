from __future__ import annotations

from functools import lru_cache

import jwt
from jwt import PyJWKClient
from mcp.server.auth.provider import AccessToken, TokenVerifier


class Auth0TokenVerifier(TokenVerifier):
    """Valida tokens JWT RS256 emitidos por un tenant de Auth0."""

    def __init__(self, *, issuer: str, audience: str) -> None:
        self.issuer = issuer.rstrip("/") + "/"
        self.audience = audience
        self.jwks = PyJWKClient(f"{self.issuer}.well-known/jwks.json")

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            signing_key = self.jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.issuer,
                options={"require": ["exp", "iat"]},
            )
            scopes = str(claims.get("scope") or "").split()
            subject = str(claims.get("sub") or "authenticated-user")
            return AccessToken(token=token, client_id=subject, scopes=scopes)
        except Exception:
            return None
