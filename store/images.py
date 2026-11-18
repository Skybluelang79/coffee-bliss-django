import os

from PIL import Image, ImageOps


def optimize_image(image_field, max_dimension=1600, quality=85):
    """Resize and recompress an uploaded image in place, preserving format."""

    if not image_field:
        return False
    try:
        path = image_field.path
    except (ValueError, NotImplementedError):
        return False
    if not path or not os.path.exists(path):
        return False

    try:
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image)
            original_format = image.format or "JPEG"
            if max(image.size) > max_dimension:
                image.thumbnail((max_dimension, max_dimension))
            save_kwargs = {"optimize": True}
            if original_format in {"JPEG", "WEBP"}:
                save_kwargs["quality"] = quality
            if original_format == "JPEG" and image.mode not in {"RGB", "L"}:
                image = image.convert("RGB")
            image.save(path, format=original_format, **save_kwargs)
    except (OSError, ValueError):
        return False
    return True
