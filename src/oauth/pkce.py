"""PKCE (RFC 7636) verifier and S256 challenge.

The verifier never leaves the board: it is generated when a flow starts, held
in memory, and sent only to the provider's token endpoint. That is what makes
an authorization code useless to anything that sees it in transit — including
the static relay page the provider redirects through.
"""

from __future__ import annotations

import base64
import hashlib
import secrets

CHALLENGE_METHOD = "S256"


def generate_verifier() -> str:
    """Return a fresh 43-character verifier (32 random bytes, base64url).

    RFC 7636 §4.1 allows 43–128 characters from the unreserved set; 32 bytes
    of entropy is the length the RFC itself recommends.
    """
    return secrets.token_urlsafe(32)


def challenge_for(verifier: str) -> str:
    """Return the S256 challenge for *verifier*: ``BASE64URL(SHA256(verifier))``."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
