from io import BytesIO

import pytest
from PIL import Image, PngImagePlugin

from vashfindir.core.exceptions import SlideImageError
from vashfindir.domain.slide_images import normalize_slide_png


def _image_bytes(size: tuple[int, int], image_format: str = "PNG", color: str = "navy") -> bytes:
    output = BytesIO()
    Image.new("RGB", size, color).save(output, format=image_format)
    return output.getvalue()


async def test_normalizes_png_to_mvp_size() -> None:
    normalized = await normalize_slide_png(_image_bytes((1600, 900)))

    with Image.open(BytesIO(normalized)) as image:
        assert image.format == "PNG"
        assert image.size == (1080, 1350)
        assert image.mode == "RGB"


async def test_normalization_strips_png_metadata() -> None:
    source = Image.new("RGB", (1080, 1350), "navy")
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Software", "test")
    metadata.add_text("comment", "secret metadata")
    output = BytesIO()
    source.save(output, format="PNG", pnginfo=metadata)

    normalized = await normalize_slide_png(output.getvalue())

    with Image.open(BytesIO(normalized)) as image:
        assert "Software" not in image.info
        assert "comment" not in image.info


async def test_preserves_alpha_channel() -> None:
    output = BytesIO()
    Image.new("RGBA", (800, 1000), (20, 40, 80, 128)).save(output, format="PNG")

    normalized = await normalize_slide_png(output.getvalue())

    with Image.open(BytesIO(normalized)) as image:
        assert image.mode == "RGBA"
        assert image.size == (1080, 1350)


async def test_rejects_empty_content() -> None:
    with pytest.raises(SlideImageError, match="empty"):
        await normalize_slide_png(b"")


async def test_rejects_invalid_png() -> None:
    with pytest.raises(SlideImageError, match="valid PNG"):
        await normalize_slide_png(b"not an image")


async def test_rejects_non_png_image() -> None:
    with pytest.raises(SlideImageError, match="must be a PNG"):
        await normalize_slide_png(_image_bytes((100, 100), image_format="JPEG"))


async def test_rejects_non_positive_target_size() -> None:
    with pytest.raises(SlideImageError, match="positive"):
        await normalize_slide_png(_image_bytes((100, 100)), width=0)
