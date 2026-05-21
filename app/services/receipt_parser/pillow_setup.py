from __future__ import annotations

import logging

from PIL import Image

logger = logging.getLogger(__name__)


def register_optional_image_decoders() -> None:
    try:
        from pillow_heif import register_heif_opener
    except ImportError:
        return

    register_heif_opener()


def open_receipt_image(stream):
    register_optional_image_decoders()

    image = Image.open(stream)
    detected_format = image.format
    frame_count = getattr(image, "n_frames", 1)
    logger.info(
        "Opened receipt image: format=%s mode=%s size=%sx%s frames=%s",
        detected_format,
        image.mode,
        image.width,
        image.height,
        frame_count,
    )

    if frame_count > 1:
        image.seek(0)
        first_frame = image.copy()
        first_frame.format = detected_format
        logger.info("Using first frame of multi-frame image for receipt processing.")
        return first_frame

    image.load()
    return image
