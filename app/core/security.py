from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import get_settings

settings = get_settings()


def hash_password(password: str) -> str:
    """Пароль хранится только в виде bcrypt-хеша."""
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_bytes, salt).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    """Введенный пароль сравнивается с сохраненным хешем без восстановления исходного пароля."""
    return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    """JWT содержит идентификатор пользователя и время истечения токена."""
    expire_delta = timedelta(minutes=expires_minutes or settings.access_token_expire_minutes)
    expire_at = datetime.now(timezone.utc) + expire_delta
    payload = {"sub": subject, "exp": expire_at}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Токен проверяется по подписи и сроку действия."""
    return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
