from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: RoleResponse
    is_active: bool


class UserCreateRequest(BaseModel):
    """Данные для создания пользователя администратором."""

    email: EmailStr
    full_name: str = Field(min_length=2, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    role_code: str
    is_active: bool = True


class UserUpdateRequest(BaseModel):
    """При обновлении пользователя передаются только изменяемые поля."""

    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    role_code: str | None = None
    is_active: bool | None = None
