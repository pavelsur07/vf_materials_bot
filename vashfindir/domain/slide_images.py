import asyncio
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from vashfindir.core.exceptions import SlideImageError
from vashfindir.domain.slides import SLIDE_HEIGHT, SLIDE_WIDTH


async def normalize_slide_png(
    content: bytes,
    *,
    width: int = SLIDE_WIDTH,
    height: int = SLIDE_HEIGHT,
) -> bytes:
    """Validate a PNG and return a center-cropped image in the target size."""
    if not content:
        raise SlideImageError("slide image is empty")
    if width <= 0 or height <= 0:
        raise SlideImageError("slide image dimensions must be positive")
    return await asyncio.to_thread(_normalize_slide_png, content, width, height)


def _normalize_slide_png(content: bytes, width: int, height: int) -> bytes:
    try:
        with Image.open(BytesIO(content)) as source:
            if source.format != "PNG":
                raise SlideImageError("slide image must be a PNG")
            image = ImageOps.exif_transpose(source)
            has_alpha = image.mode in ("RGBA", "LA") or "transparency" in image.info
            image = image.convert("RGBA" if has_alpha else "RGB")
            fitted = ImageOps.fit(image, (width, height), method=Image.Resampling.LANCZOS)
            output = BytesIO()
            fitted.save(output, format="PNG", optimize=True)
            return output.getvalue()
    except SlideImageError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise SlideImageError("slide image must be a valid PNG") from exc
