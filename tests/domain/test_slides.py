import pytest
from pydantic import ValidationError

from vashfindir.domain.slides import (
    SLIDE_ASPECT_RATIO,
    SLIDE_HEIGHT,
    SLIDE_WIDTH,
    SlideOutputSpec,
    SlidePromptTemplate,
    default_slide_style,
)


def test_default_style_matches_mvp_contract() -> None:
    style = default_slide_style()

    assert style.id == "style_01"
    assert style.version == 1
    assert style.enabled is True
    assert style.output.format == "png"
    assert style.output.width == SLIDE_WIDTH
    assert style.output.height == SLIDE_HEIGHT
    assert style.generation.aspect_ratio == SLIDE_ASPECT_RATIO
    assert style.postprocessing.target_width == SLIDE_WIDTH
    assert style.postprocessing.target_height == SLIDE_HEIGHT


def test_build_prompt_renders_plot_without_placeholder() -> None:
    plot = "Финансовый директор анализирует падение выручки компании"

    prompt = default_slide_style().build_prompt(plot)

    assert f"Visual subject: {plot}" in prompt
    assert "{plot}" not in prompt
    assert "Style: modern editorial illustration" in prompt
    assert "Palette: deep navy blue, warm ivory, muted gold accents" in prompt


def test_prompt_template_requires_plot_placeholder() -> None:
    with pytest.raises(ValidationError, match="placeholder"):
        SlidePromptTemplate(subject_placeholder="{subject}")


def test_output_spec_rejects_non_mvp_size() -> None:
    with pytest.raises(ValidationError, match="1080x1350"):
        SlideOutputSpec(width=1920, height=1080)
