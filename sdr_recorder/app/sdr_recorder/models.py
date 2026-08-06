from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class FrequencyBase(BaseModel):
    frequency_hz: int = Field(ge=70_000_000, le=6_000_000_000)
    name: str = Field(default="", max_length=80)
    category: str = Field(default="", max_length=80)
    enabled: bool = True
    squelch_dbfs: float = Field(default=-45.0, ge=-120, le=10)
    record_enabled: bool = True
    retention_days: int = Field(default=0, ge=0, le=3650)

    @field_validator("name", "category")
    @classmethod
    def clean_text(cls, value: str) -> str:
        return " ".join(value.strip().split())


class FrequencyCreate(FrequencyBase):
    pass


class FrequencyUpdate(FrequencyBase):
    pass


class RecordingPatch(BaseModel):
    label: str | None = Field(default=None, max_length=120)
    favorite: bool | None = None
    protected: bool | None = None

    @field_validator("label")
    @classmethod
    def clean_label(cls, value: str | None) -> str | None:
        return " ".join(value.strip().split()) if value is not None else None


class BulkDelete(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)
