from __future__ import annotations

from io import BytesIO
import os
import re

from PIL import ImageOps, UnidentifiedImageError

from app.services.receipt_parser.pillow_setup import open_receipt_image

SUMMARY_FIELD_MAP = {
    "VENDOR_NAME": "merchant",
    "SUBTOTAL": "subtotal",
    "TAX": "tax",
    "TOTAL": "total",
}


def extract_receipt_with_textract(upload_file) -> dict[str, object]:
    image_bytes, image_info = _load_image_bytes(upload_file)
    response = _analyze_expense(image_bytes)

    expense_document = (response.get("ExpenseDocuments") or [{}])[0]
    summary = _parse_summary_fields(expense_document.get("SummaryFields", []))
    items = _parse_line_items(expense_document.get("LineItemGroups", []))

    return {
        "provider": "aws_textract",
        "filename": image_info["filename"],
        "merchant": summary.get("merchant"),
        "subtotal": summary.get("subtotal"),
        "tax": summary.get("tax"),
        "total": summary.get("total"),
        "candidate_items": items,
    }


def _load_image_bytes(upload_file):
    try:
        original = open_receipt_image(upload_file.file)
    except UnidentifiedImageError as exc:
        raise ValueError("The uploaded file is not a valid image.") from exc

    normalized = ImageOps.exif_transpose(original)
    if normalized.mode not in ("RGB", "L"):
        normalized = normalized.convert("RGB")

    image_format = (normalized.format or original.format or "PNG").upper()
    if image_format in {"HEIF", "HEIC", "JPG"}:
        image_format = "JPEG"
    if image_format not in {"JPEG", "PNG", "TIFF"}:
        image_format = "JPEG"
    if image_format == "JPEG" and normalized.mode != "RGB":
        normalized = normalized.convert("RGB")

    image_buffer = BytesIO()
    normalized.save(image_buffer, format=image_format)

    return image_buffer.getvalue(), {
        "filename": upload_file.filename,
        "format": original.format or image_format,
    }


def _analyze_expense(image_bytes: bytes) -> dict[str, object]:
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    if not region:
        raise ValueError("Set AWS_REGION or AWS_DEFAULT_REGION before using receipt upload.")

    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

        client = boto3.client("textract", region_name=region)
        return client.analyze_expense(Document={"Bytes": image_bytes})
    except ImportError as exc:
        raise ValueError("Install boto3 before using receipt upload.") from exc
    except NoCredentialsError as exc:
        raise ValueError("AWS credentials are not configured for Textract.") from exc
    except (BotoCoreError, ClientError) as exc:
        raise ValueError(f"AWS Textract request failed: {exc}") from exc


def _parse_summary_fields(summary_fields: list[dict[str, object]]) -> dict[str, str]:
    parsed = {}
    for field in summary_fields:
        field_type = ((field.get("Type") or {}).get("Text") or "").upper()
        normalized_key = SUMMARY_FIELD_MAP.get(field_type)
        if not normalized_key:
            continue

        value = ((field.get("ValueDetection") or {}).get("Text") or "").strip()
        if not value:
            continue

        parsed[normalized_key] = value if normalized_key == "merchant" else _parse_amount(value)
    return parsed


def _parse_line_items(line_item_groups: list[dict[str, object]]) -> list[dict[str, str]]:
    items = []
    seen = set()

    for group in line_item_groups:
        for line_item in group.get("LineItems", []):
            fields = {}
            for expense_field in line_item.get("LineItemExpenseFields", []):
                field_type = ((expense_field.get("Type") or {}).get("Text") or "").upper()
                field_value = (
                    (expense_field.get("ValueDetection") or {}).get("Text") or ""
                ).strip()
                if field_type and field_value:
                    fields[field_type] = field_value

            name = fields.get("ITEM") or fields.get("DESCRIPTION")
            quantity = fields.get("QUANTITY") or _extract_quantity_from_unit_price(
                fields.get("UNIT_PRICE")
            )
            price_text = (
                fields.get("PRICE")
                or fields.get("AMOUNT")
                or fields.get("ITEM_PRICE")
                or fields.get("TOTAL")
            )

            if not name or not price_text:
                raw_text = _extract_line_item_raw_text(line_item)
                _extend_items_from_raw_text(items, seen, raw_text)
                continue

            item = {
                "name": _format_quantity_name(name, quantity),
                "price": _parse_amount(price_text),
            }
            _append_item(items, seen, item)
            _extend_items_from_raw_text(items, seen, _extract_line_item_raw_text(line_item))

    return _cleanup_items(items)


def _parse_amount(raw_value: str) -> str:
    cleaned = raw_value.replace("$", "").replace(",", "").strip()
    try:
        return f"{float(cleaned):.2f}"
    except ValueError:
        return raw_value.strip()


def _extract_line_item_raw_text(line_item: dict[str, object]) -> str:
    lines = []
    for expense_field in line_item.get("LineItemExpenseFields", []):
        if expense_field.get("ValueDetection", {}).get("Text"):
            lines.append(expense_field["ValueDetection"]["Text"].strip())
    return "\n".join(line for line in lines if line)


def _extend_items_from_raw_text(items: list[dict[str, str]], seen: set, raw_text: str) -> None:
    for line in raw_text.splitlines():
        parsed = _parse_item_line(line)
        if parsed:
            _append_item(items, seen, parsed)


def _parse_item_line(line: str) -> dict[str, str] | None:
    normalized = " ".join(line.split())
    match = re.search(r"^(?P<name>.+?)\s+\d+\s+\$?(?P<price>\d+[.,]\d{2})$", normalized)
    if not match:
        return None

    name = match.group("name").strip(" .:-")
    if len(name) < 2:
        return None

    return {
        "name": _format_quantity_name(name, _extract_inline_quantity(normalized)),
        "price": match.group("price").replace(",", "."),
    }


def _append_item(items: list[dict[str, str]], seen: set, item: dict[str, str]) -> None:
    key = (item["name"].strip().lower(), item["price"])
    if key in seen:
        return
    seen.add(key)
    items.append(item)


def _cleanup_items(items: list[dict[str, str]]) -> list[dict[str, str]]:
    normalized_names = {_normalize_name(item["name"]) for item in items}
    filtered = []

    for item in items:
        item_name = _normalize_name(item["name"])
        keep_item = True
        for candidate_base in items:
            if candidate_base is item or item["price"] != candidate_base["price"]:
                continue
            base_name = _normalize_name(candidate_base["name"])
            if not item_name.startswith(f"{base_name} "):
                continue
            trailing_name = item_name[len(base_name) :].strip()
            if trailing_name and trailing_name in normalized_names:
                keep_item = False
                break
        if keep_item:
            filtered.append(item)
    return filtered


def _normalize_name(name: str) -> str:
    return " ".join(name.lower().split())


def _format_quantity_name(name: str, quantity: str | None) -> str:
    cleaned_name = name.strip()
    normalized_quantity = _normalize_quantity(quantity)
    if not normalized_quantity:
        return cleaned_name
    return f"{normalized_quantity} x {cleaned_name}"


def _normalize_quantity(quantity: str | None) -> str | None:
    if not quantity:
        return None
    raw = str(quantity).strip()
    match = re.fullmatch(r"(\d+)(?:\.0+)?", raw)
    return match.group(1) if match else None


def _extract_inline_quantity(line: str) -> str | None:
    match = re.search(r"^(?P<name>.+?)\s+(?P<quantity>\d+)\s+\$?\d+[.,]\d{2}$", line)
    return match.group("quantity") if match else None


def _extract_quantity_from_unit_price(unit_price: str | None) -> str | None:
    if not unit_price:
        return None
    match = re.search(r"\((?P<quantity>\d+)\s*@\s*\$?\d+[.,]\d{2}\)", str(unit_price))
    return match.group("quantity") if match else None
