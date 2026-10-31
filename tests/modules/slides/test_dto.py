import pytest
from pydantic import ValidationError

from vashfindir.modules.slides.dto import SlideGenerationRequest


def test_request_strips_plot_and_uses_fixed_style() -> None:
    plot = "Финансовый директор анализирует падение выручки компании"

    request = SlideGenerationRequest(plot=f"  {plot}  ")

    assert request.plot == plot
    assert request.style_id == "style_01"


@pytest.mark.parametrize(
    "plot",
    [
        "коротко",
        "x" * 1001,
    ],
)
def test_request_rejects_invalid_plot_length(plot: str) -> None:
    with pytest.raises(ValidationError):
        SlideGenerationRequest(plot=plot)
