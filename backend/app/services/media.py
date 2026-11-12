"""Media hygiene: strip embedded metadata (EXIF GPS, camera serials...) from uploaded photos.

Without this, a photo attached to an "approximate" or sensitive-taxon observation would still carry the
exact GNSS fix in its EXIF block and defeat the coordinate privacy rules.
"""
from __future__ import annotations

import io

from PIL import Image, ImageOps

FORMATS = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}


def strip_image_metadata(data: bytes, content_type: str) -> bytes:
    """Return the image re-encoded without metadata, with EXIF orientation applied to the pixels.

    Non-image content (audio) is returned untouched. Raises ValueError for unreadable images.
    """
    fmt = FORMATS.get(content_type)
    if not fmt:
        return data
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.load()
            im = ImageOps.exif_transpose(im)
            if fmt == "JPEG" and im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            # Rebuild from raw pixels: nothing from the original container (EXIF, XMP, ICC, text chunks) survives.
            clean = Image.frombytes(im.mode, im.size, im.tobytes())
            if im.mode == "P" and im.getpalette():
                clean.putpalette(im.getpalette())
            out = io.BytesIO()
            kw = {"quality": 92, "optimize": True} if fmt == "JPEG" else {}
            clean.save(out, fmt, **kw)
            return out.getvalue()
    except Exception as e:  # noqa: BLE001 - PIL raises many types
        raise ValueError(f"Unreadable image: {e}") from e
