"""
Password hashing utilities using bcrypt.

Bcrypt is intentionally slow (tunable work-factor) which makes brute-force
attacks expensive.  Salt generation is handled automatically by ``bcrypt.gensalt()``.

Note: We use the ``bcrypt`` library directly rather than through ``passlib``
because passlib 1.7.4 is incompatible with bcrypt >= 4.1.  Using bcrypt
directly is simpler and avoids the stale intermediary.
"""

import bcrypt


def hash_password(password: str) -> str:
    """Return a bcrypt hash of *password*.

    The password is encoded to UTF-8 before hashing.  The returned string
    is safe to store in a VARCHAR(255) column.
    """
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return ``True`` if *plain_password* matches *hashed_password*.

    Both values are encoded to UTF-8 before comparison.  Uses constant-time
    comparison internally to prevent timing attacks.
    """
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )
