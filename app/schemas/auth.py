from pydantic import BaseModel


class LoginRequest(BaseModel):
    """Данные для входа через API."""

    email: str
    password: str


class TokenResponse(BaseModel):
    """Ответ после успешной проверки логина и пароля."""

    access_token: str
    token_type: str = "bearer"


class CurrentUserResponse(BaseModel):
    """Краткая информация о текущем пользователе."""

    id: int
    email: str
    full_name: str
    role: str
