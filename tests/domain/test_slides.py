from pathlib import Path

import pytest
from pydantic import ValidationError

from vashfindir.domain.slides import (
    SLIDE_ASPECT_RATIO,
    SLIDE_HEIGHT,
    SLIDE_WIDTH,
    SlideOutputSpec,
    SlidePromptTemplate,
    SlideStyle,
    default_slide_style,
)


def test_default_style_matches_mvp_contract() -> None:
    style = default_slide_style()

    assert style.id == "style_01"
    assert style.version == 2
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
    assert "2D cartoon illustration" in prompt
    assert "near-white faces" in prompt
    assert "Saturated red #C9002B" in prompt
    assert "soft cinematic lighting" not in prompt
    assert "warm ivory, muted gold" not in prompt


def test_prompt_template_requires_plot_placeholder() -> None:
    with pytest.raises(ValidationError, match="placeholder"):
        SlidePromptTemplate(subject_placeholder="{subject}")


def test_output_spec_rejects_non_mvp_size() -> None:
    with pytest.raises(ValidationError, match="1122x1402"):
        SlideOutputSpec(width=1920, height=1122)


def test_style_01_matches_reference_dimensions_and_documented_profile() -> None:
    style = default_slide_style()
    documented = SlideStyle.model_validate_json(Path("docs/style_01.json").read_text())

    assert (style.output.width, style.output.height) == (1122, 1402)
    assert style.generation.aspect_ratio == "561:701"
    assert documented == style


def test_style_01_rejects_previous_output_size() -> None:
    with pytest.raises(ValidationError, match="1122x1402"):
        SlideOutputSpec(width=1080, height=1350)
