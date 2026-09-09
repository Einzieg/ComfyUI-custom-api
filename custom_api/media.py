import base64
import io

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from .errors import APIError

MAX_IMAGE_BYTES = 32 * 1024 * 1024
MAX_PIXELS = 40_000_000
MAX_IMAGES = 16


def validate_image(data):
    if len(data) > MAX_IMAGE_BYTES:
        raise APIError("media_too_large", "Maximum image size: 32 MB.")
    try:
        with Image.open(io.BytesIO(data)) as im:
            if im.width * im.height > MAX_PIXELS:
                raise APIError("media_too_large", "Maximum image dimensions: 40 megapixels.")
            im.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise APIError("invalid_image", "Response is not a supported image.") from exc
    return data


def decode_image(value):
    if not isinstance(value, str):
        raise APIError("invalid_image", "Expected a data URL or base64 string.")
    if value.startswith("data:"):
        if not value.startswith("data:image/") or ";base64," not in value:
            raise APIError("invalid_image", "Expected a base64 image data URL.")
        value = value.split(",", 1)[1]
    if len(value) > MAX_IMAGE_BYTES * 4 // 3 + 4:
        raise APIError("media_too_large")
    try:
        data = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise APIError("invalid_image", "Invalid base64 image.") from exc
    return validate_image(data)


def data_url(data):
    with Image.open(io.BytesIO(data)) as im:
        mime = Image.MIME.get(im.format, "image/png")
    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


def preview_url(data):
    with Image.open(io.BytesIO(data)) as im:
        preview = ImageOps.exif_transpose(im).convert("RGB")
        preview.thumbnail((1024, 1024))
        buffer = io.BytesIO()
        preview.save(buffer, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def tensor_images(tensor):
    if tensor is None:
        return []
    if len(tensor) > MAX_IMAGES:
        raise APIError("media_too_large", f"Maximum batch: {MAX_IMAGES} images.")
    results = []
    for frame in tensor:
        pixels = np.clip(frame.detach().cpu().numpy() * 255, 0, 255).astype(np.uint8)
        if pixels.shape[0] * pixels.shape[1] > MAX_PIXELS:
            raise APIError("media_too_large")
        buffer = io.BytesIO()
        Image.fromarray(pixels).save(buffer, format="PNG")
        results.append(validate_image(buffer.getvalue()))
    return results


def tensor_mask(mask):
    if mask is None:
        return None
    pixels = np.clip(mask[0].detach().cpu().numpy() * 255, 0, 255).astype(np.uint8)
    # Comfy MASK: 1 = area to edit. Image-edit alpha masks: 0 = area to edit.
    im = Image.new("RGBA", (pixels.shape[1], pixels.shape[0]), (255, 255, 255, 255))
    im.putalpha(Image.fromarray(255 - pixels))
    buffer = io.BytesIO()
    im.save(buffer, format="PNG")
    return validate_image(buffer.getvalue())


def image_tensors(images):
    import torch

    output = []
    for data in images:
        validate_image(data)
        with Image.open(io.BytesIO(data)) as im:
            rgb = ImageOps.exif_transpose(im).convert("RGB")
            output.append(torch.from_numpy(np.array(rgb).astype(np.float32) / 255.0).unsqueeze(0))
    # A Comfy output list preserves different image sizes without resizing them.
    return output
