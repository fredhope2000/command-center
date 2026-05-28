from __future__ import annotations

from io import BytesIO
from uuid import uuid4

from PIL import ImageOps, UnidentifiedImageError

from app.config import settings
from app.services.receipt_parser.pillow_setup import open_receipt_image

MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MAX_IMAGE_DIMENSION = 8000
MAX_IMAGE_PIXELS = 30_000_000
OUTPUT_MAX_DIMENSION = 2400
OUTPUT_CONTENT_TYPE = "image/jpeg"


def upload_restaurant_photo(upload_file, restaurant_id: int) -> dict[str, str]:
    if not settings.restaurant_photos_s3_bucket:
        raise ValueError("Set RESTAURANT_PHOTOS_S3_BUCKET before uploading photos.")

    image_bytes = _normalize_image(upload_file)
    key = _photo_key(restaurant_id)

    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

        client = boto3.client("s3")
        client.put_object(
            Bucket=settings.restaurant_photos_s3_bucket,
            Key=key,
            Body=image_bytes,
            ContentType=OUTPUT_CONTENT_TYPE,
            CacheControl="public, max-age=31536000, immutable",
        )
    except ImportError as exc:
        raise ValueError("Install boto3 before using restaurant photo uploads.") from exc
    except NoCredentialsError as exc:
        raise ValueError("AWS credentials are not configured for S3.") from exc
    except (BotoCoreError, ClientError) as exc:
        raise ValueError(f"AWS S3 upload failed: {exc}") from exc

    return {
        "storage_key": key,
        "url": _public_url(key),
        "content_type": OUTPUT_CONTENT_TYPE,
    }


def delete_restaurant_photo(storage_key: str) -> None:
    if not settings.restaurant_photos_s3_bucket:
        return

    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

        client = boto3.client("s3")
        client.delete_object(
            Bucket=settings.restaurant_photos_s3_bucket,
            Key=storage_key,
        )
    except (ImportError, NoCredentialsError, BotoCoreError, ClientError):
        return


def _normalize_image(upload_file) -> bytes:
    stream = upload_file.file
    original_position = stream.tell()

    try:
        stream.seek(0, 2)
        file_size = stream.tell()
        stream.seek(0)

        if file_size > MAX_UPLOAD_BYTES:
            raise ValueError(
                f"Photo is too large. Keep uploads under {_format_megabytes(MAX_UPLOAD_BYTES)} MB."
            )

        try:
            image = open_receipt_image(stream)
        except UnidentifiedImageError as exc:
            raise ValueError("The uploaded file is not a valid image.") from exc

        if image.width > MAX_IMAGE_DIMENSION or image.height > MAX_IMAGE_DIMENSION:
            raise ValueError(
                f"Photo dimensions are too large. Keep each side under {MAX_IMAGE_DIMENSION} pixels."
            )

        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise ValueError(
                f"Photo has too many pixels. Keep uploads under {MAX_IMAGE_PIXELS:,} total pixels."
            )

        image = ImageOps.exif_transpose(image)
        image.thumbnail((OUTPUT_MAX_DIMENSION, OUTPUT_MAX_DIMENSION))
        if image.mode != "RGB":
            image = image.convert("RGB")

        output = BytesIO()
        image.save(output, format="JPEG", quality=86, optimize=True)
        return output.getvalue()
    finally:
        stream.seek(original_position)


def _photo_key(restaurant_id: int) -> str:
    prefix = settings.restaurant_photos_s3_prefix
    filename = f"{uuid4().hex}.jpg"
    if not prefix:
        return f"restaurants/{restaurant_id}/{filename}"
    return f"{prefix}/restaurants/{restaurant_id}/{filename}"


def _public_url(storage_key: str) -> str:
    if settings.restaurant_photos_base_url:
        return f"{settings.restaurant_photos_base_url}/{storage_key}"

    bucket = settings.restaurant_photos_s3_bucket
    region = settings.aws_region
    if region:
        return f"https://{bucket}.s3.{region}.amazonaws.com/{storage_key}"
    return f"https://{bucket}.s3.amazonaws.com/{storage_key}"


def _format_megabytes(byte_count: int) -> str:
    return f"{byte_count / (1024 * 1024):.0f}"
