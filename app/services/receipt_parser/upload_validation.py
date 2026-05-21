from __future__ import annotations

import logging

from PIL import UnidentifiedImageError

from app.services.receipt_parser.pillow_setup import open_receipt_image

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_IMAGE_DIMENSION = 8000
MAX_IMAGE_PIXELS = 25_000_000
ALLOWED_IMAGE_FORMATS = {
    "JPEG",
    "PNG",
    "WEBP",
    "HEIC",
    "HEIF",
    "TIFF",
    "BMP",
    "GIF",
    "MPO",
}


def validate_uploaded_receipt(upload_file) -> None:
    stream = upload_file.file
    original_position = stream.tell()

    try:
        stream.seek(0, 2)
        file_size = stream.tell()
        stream.seek(0)

        if file_size > MAX_UPLOAD_BYTES:
            raise ValueError(
                f"Receipt image is too large. Keep uploads under {_format_megabytes(MAX_UPLOAD_BYTES)} MB."
            )

        logger.info(
            "Validating uploaded receipt: filename=%s content_type=%s size_bytes=%s",
            getattr(upload_file, "filename", None),
            getattr(upload_file, "content_type", None),
            file_size,
        )

        try:
            image = open_receipt_image(stream)
        except UnidentifiedImageError as exc:
            raise ValueError("The uploaded file is not a valid image.") from exc

        image_format = (image.format or "").upper()
        if image_format not in ALLOWED_IMAGE_FORMATS:
            raise ValueError("Upload a receipt photo as an image file such as JPG, PNG, or HEIC.")

        if image.width > MAX_IMAGE_DIMENSION or image.height > MAX_IMAGE_DIMENSION:
            raise ValueError(
                f"Receipt image dimensions are too large. Keep each side under {MAX_IMAGE_DIMENSION} pixels."
            )

        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise ValueError(
                f"Receipt image has too many pixels. Keep uploads under {MAX_IMAGE_PIXELS:,} total pixels."
            )
    finally:
        stream.seek(original_position)


def _format_megabytes(byte_count: int) -> str:
    return f"{byte_count / (1024 * 1024):.0f}"
