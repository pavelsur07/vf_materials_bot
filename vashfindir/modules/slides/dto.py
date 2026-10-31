from pydantic import BaseModel, ConfigDict, Field, field_validator

from vashfindir.domain.slides import (
    MAX_PLOT_LENGTH,
    MIN_PLOT_LENGTH,
    SlideImageFormat,
    SlideStyleId,
)


class SlideGenerationRequest(BaseModel):
    """Input for one MVP slide generation."""

    model_config = ConfigDict(frozen=True)

    plot: str = Field(min_length=MIN_PLOT_LENGTH, max_length=MAX_PLOT_LENGTH)
    style_id: SlideStyleId = SlideStyleId.STYLE_01

    @field_validator("plot", mode="before")
    @classmethod
    def _strip_plot(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class SlideGenerationResult(BaseModel):
    """Prepared generation contract shared by admin UI, worker and integrations."""

    model_config = ConfigDict(frozen=True)

    plot: str = Field(min_length=MIN_PLOT_LENGTH, max_length=MAX_PLOT_LENGTH)
    style_id: SlideStyleId
    style_version: int = Field(ge=1)
    model: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    negative_prompt: str = Field(min_length=1)
    image_format: SlideImageFormat
    width: int = Field(ge=1)
    height: int = Field(ge=1)
