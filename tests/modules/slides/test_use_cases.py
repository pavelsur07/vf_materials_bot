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
    assert result.style_version == 1
    assert result.model == "mock-model"
    assert result.image_format == "png"
    assert result.width == 1080
    assert result.height == 1350
    assert "Visual subject:" in result.prompt
    assert result.negative_prompt
    assert SlideGenerationResult.model_validate(result.model_dump()) == result


def test_rejects_disabled_style() -> None:
    style = default_slide_style().model_copy(update={"enabled": False})
    use_case = PrepareSlideGenerationUseCase(style)

    with pytest.raises(UseCaseError, match="disabled"):
        use_case.execute(SlideGenerationRequest(plot="Сюжет для тестовой генерации"))
