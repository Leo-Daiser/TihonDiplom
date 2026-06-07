from pydantic import BaseModel, ConfigDict, Field


class DictionaryItemCreateRequest(BaseModel):
    """Данные для создания элемента справочника."""

    code: str = Field(min_length=2, max_length=50)
    name: str = Field(min_length=2, max_length=100)
    sort_order: int = 0
    is_final: bool | None = None


class DictionaryItemUpdateRequest(BaseModel):
    """Обновление справочника выполняется только по переданным полям."""

    name: str | None = Field(default=None, min_length=2, max_length=100)
    sort_order: int | None = None
    is_final: bool | None = None


class StatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    sort_order: int
    is_final: bool
    is_system: bool


class PriorityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    sort_order: int
    is_system: bool
