"""Internal test-fixture seeder for TrustC generated backends.

Reused by Stage 4 smoke testing and Stage 5 attack harness.
Seeds two local users and typed data directly into SQLAlchemy models.
Tokens and secrets stay in memory; never logged or printed.
"""

from __future__ import annotations

import datetime
import secrets
import uuid
from typing import Any, Dict, Optional, Tuple

import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Deterministic test identities
USER_1_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
USER_1_EMAIL = "user1@example.com"
USER_1_HASH = "hash_user_1_secret_value"

USER_2_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
USER_2_EMAIL = "user2@example.com"
USER_2_HASH = "hash_user_2_secret_value"

DEFAULT_TEST_SECRET = "trustc-ephemeral-test-secret-at-least-32-bytes-long!!"
ALGORITHM = "HS256"
ISSUER = "trustc-local"
AUDIENCE = "trustc-api"


def generate_harness_secret(nbytes: int = 32) -> str:
    """Generate a cryptographically secure random secret key with at least 32 bytes."""
    return secrets.token_hex(max(nbytes, 32))


def create_access_token(
    user_id: uuid.UUID | str,
    secret: str = DEFAULT_TEST_SECRET,
    expires_in_seconds: int = 3600,
    issuer: str = ISSUER,
    audience: str = AUDIENCE,
    custom_claims: Optional[Dict[str, Any]] = None,
    expired: bool = False,
) -> str:
    """Generate in-memory JWT token for test actors.

    Tokens are kept in memory and never logged to console or stdout.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    if expired:
        exp = now - datetime.timedelta(seconds=60)
        iat = now - datetime.timedelta(seconds=120)
    else:
        exp = now + datetime.timedelta(seconds=expires_in_seconds)
        iat = now

    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "exp": exp,
        "iat": iat,
        "iss": issuer,
        "aud": audience,
    }
    if custom_claims:
        payload.update(custom_claims)

    token = jwt.encode(payload, secret, algorithm=ALGORITHM)
    return token


async def seed_test_users(
    session: AsyncSession,
    user_model: Any,
) -> Tuple[Any, Any]:
    """Seed the two canonical test users directly into the database."""
    # Check if User 1 exists
    res1 = await session.execute(select(user_model).where(user_model.id == USER_1_ID))
    u1 = res1.scalar_one_or_none()
    if u1 is None:
        u1 = user_model(
            id=USER_1_ID,
            email=USER_1_EMAIL,
            password_hash=USER_1_HASH,
        )
        session.add(u1)

    # Check if User 2 exists
    res2 = await session.execute(select(user_model).where(user_model.id == USER_2_ID))
    u2 = res2.scalar_one_or_none()
    if u2 is None:
        u2 = user_model(
            id=USER_2_ID,
            email=USER_2_EMAIL,
            password_hash=USER_2_HASH,
        )
        session.add(u2)

    await session.commit()
    await session.refresh(u1)
    await session.refresh(u2)
    return u1, u2


class SeededContext:
    """In-memory security context holding tokens and IDs for test actors."""

    def __init__(
        self,
        user1_id: uuid.UUID = USER_1_ID,
        user2_id: uuid.UUID = USER_2_ID,
        secret: str = DEFAULT_TEST_SECRET,
    ):
        self.user1_id = user1_id
        self.user2_id = user2_id
        self.secret = secret
        self.user1_token = create_access_token(user1_id, secret=secret)
        self.user2_token = create_access_token(user2_id, secret=secret)

    def __repr__(self) -> str:
        return (
            f"SeededContext(user1_id={self.user1_id}, user2_id={self.user2_id}, "
            f"tokens=<REDACTED_IN_MEMORY>)"
        )
