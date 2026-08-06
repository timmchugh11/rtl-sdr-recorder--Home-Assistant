from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class FrequencyBase(BaseModel):
    frequency_hz: int = Field(ge=70_000_000, le=6_000_000_000)
    name: str = Field(default="", max_length=80)
    category: str = Field(default="", max_length=80)
    enabled: bool = True
    squelch_dbfs: float = Field(default=-45.0, ge=-120, le=10)
    correction_hz: int = Field(default=0, ge=-50_000, le=50_000)
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


class ReceiverSettingsUpdate(BaseModel):
    center_frequency_hz: int = Field(ge=70_000_000, le=6_000_000_000)
    sample_rate_hz: int = Field(ge=520_834, le=20_000_000)
    rf_bandwidth_hz: int = Field(ge=200_000, le=20_000_000)
    gain_mode: Literal["manual", "slow_attack", "fast_attack"] = "manual"
    gain_db: float = Field(ge=-10, le=73)
    audio_sample_rate_hz: Literal[10_000] = 10_000
    audio_gain: float = Field(ge=0.01, le=1.0)
    pre_roll_seconds: float = Field(ge=0, le=5)
    post_roll_seconds: float = Field(ge=0, le=10)
    retention_days: int = Field(ge=0, le=3650)
    max_storage_mb: int = Field(ge=0, le=1_000_000)
    auto_start: bool = True
    debug: bool = False

    @model_validator(mode="after")
    def validate_rates(self):
        if self.sample_rate_hz % 50_000:
            raise ValueError("IQ sample rate must be an exact multiple of 50 kHz")
        if self.rf_bandwidth_hz > self.sample_rate_hz:
            raise ValueError("RF bandwidth cannot exceed IQ sample rate")
        return self
