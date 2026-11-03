import pytest

from vashfindir.core.exceptions import UseCaseError
from vashfindir.domain.slides import default_slide_style
from vashfindir.modules.slides.dto import (
    SlideGenerationRequest,
    SlideGenerationResult,
)
from vashfindir.modules.slides.use_cases import PrepareSlideGenerationUseCase


@pytest.fixture
def use_case() -> PrepareSlideGenerationUseCase:
    return PrepareSlideGenerationUseCase(default_slide_style())


def test_prepares_single_style_generation_contract(
    use_case: PrepareSlideGenerationUseCase,
) -> None:
    request = SlideGenerationRequest(
        plot="Финансовый директор анализирует падение выручки компании"
    )

    result = use_case.execute(request)

    assert result.plot == request.plot
    assert result.style_id == "style_01"
    assert result.style_version == 2
    assert result.model == "mock-model"
    assert result.image_format == "png"
    assert result.width == 1122
    assert result.height == 1402
    assert "Visual subject:" in result.prompt
    assert result.negative_prompt
    assert SlideGenerationResult.model_validate(result.model_dump()) == result


def test_rejects_disabled_style() -> None:
    style = default_slide_style().model_copy(update={"enabled": False})
    use_case = PrepareSlideGenerationUseCase(style)

    with pytest.raises(UseCaseError, match="disabled"):
        use_case.execute(SlideGenerationRequest(plot="Сюжет для тестовой генерации"))


def test_banking_scene_uses_reference_style_without_forbidding_interfaces(
    use_case: PrepareSlideGenerationUseCase,
) -> None:
    plot = "Человек сравнивает деньги в стеклянной банке и банковское приложение на телефоне"

    result = use_case.execute(SlideGenerationRequest(plot=plot))

    assert result.style_version == 2
    assert f"Visual subject: {plot}" in result.prompt
    assert "simple schematic interface" in result.prompt
    assert "UI elements" not in result.negative_prompt
    assert "photorealism" in result.negative_prompt
    assert "dark background" in result.negative_prompt
    assert (result.width, result.height) == (1122, 1402)
