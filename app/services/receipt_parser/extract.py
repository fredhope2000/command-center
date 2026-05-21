from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re

from app.services.receipt_parser.aws_textract import extract_receipt_with_textract


def extract_receipt(upload_file) -> dict[str, object]:
    receipt = extract_receipt_with_textract(upload_file)
    return _to_purchase_preview(receipt)


def _to_purchase_preview(receipt: dict[str, object]) -> dict[str, object]:
    items = []
    for item in receipt.get("candidate_items", []):
        name, quantity = _split_quantity_name(str(item.get("name") or ""))
        items.append(
            {
                "name": name,
                "quantity": quantity,
                "unit": "",
                "price": _format_decimal(_parse_decimal(item.get("price"))),
                "notes": "",
            }
        )

    return {
        "merchant": receipt.get("merchant") or "",
        "total": _format_decimal(_parse_decimal(receipt.get("total"))),
        "items": items,
    }


def _split_quantity_name(name: str) -> tuple[str, str]:
    match = re.fullmatch(r"(?P<quantity>\d+) x (?P<name>.+)", name.strip())
    if not match:
        return name.strip(), ""
    return match.group("name").strip(), match.group("quantity")


def _parse_decimal(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _format_decimal(value: Decimal | None) -> str:
    if value is None:
        return ""
    return f"{value:.2f}"
