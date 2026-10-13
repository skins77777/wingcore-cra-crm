"""Strict JSON schema validation for customer-message analysis results."""
from __future__ import annotations

import json
import math
from typing import Any


INTENTS = {
    "quote_request",
    "product_inquiry",
    "order_update",
    "after_sales",
    "other",
    "unknown",
}
CUSTOMER_TYPES = {
    "potential_buyer",
    "existing_buyer",
    "reseller",
    "supplier",
    "other",
    "unknown",
}
PRIORITIES = {"low", "normal", "high", "urgent", "unknown"}
SUGGESTED_ACTIONS = {
    "ask_for_details",
    "prepare_quote",
    "reply_with_information",
    "follow_up",
    "human_review",
    "no_action",
}
TOP_LEVEL_FIELDS = (
    "intent",
    "product",
    "quantity",
    "country",
    "customer_type",
    "priority",
    "suggested_action",
    "confidence",
)
QUANTITY_FIELDS = ("raw", "value", "unit")


class AnalysisSchemaError(ValueError):
    """Raised when model output is malformed or outside the fixed schema."""


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AnalysisSchemaError("duplicate_json_key")
        result[key] = value
    return result


def _reject_nonstandard_number(value: str) -> None:
    raise AnalysisSchemaError("nonstandard_json_number")


def _require_optional_text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise AnalysisSchemaError(f"{field}_must_be_text_or_null")
    return value


def _require_choice(value: Any, choices: set[str], field: str) -> str:
    if not isinstance(value, str) or value not in choices:
        raise AnalysisSchemaError(f"{field}_invalid")
    return value


def _validate_quantity(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != set(QUANTITY_FIELDS):
        raise AnalysisSchemaError("quantity_shape_invalid")

    raw = _require_optional_text(value["raw"], "quantity_raw")
    unit = _require_optional_text(value["unit"], "quantity_unit")
    amount = value["value"]
    if amount is not None:
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            raise AnalysisSchemaError("quantity_value_must_be_number_or_null")
        if not math.isfinite(amount) or amount < 0:
            raise AnalysisSchemaError("quantity_value_out_of_range")
    if raw is None and (amount is not None or unit is not None):
        raise AnalysisSchemaError("quantity_raw_required")

    return {"raw": raw, "value": amount, "unit": unit}


def validate_analysis_object(value: Any) -> dict[str, Any]:
    """Validate exact fields and return a normalized, insertion-ordered object."""
    if not isinstance(value, dict):
        raise AnalysisSchemaError("top_level_must_be_object")
    if set(value) != set(TOP_LEVEL_FIELDS):
        raise AnalysisSchemaError("top_level_fields_mismatch")

    intent = _require_choice(value["intent"], INTENTS, "intent")
    customer_type = _require_choice(value["customer_type"], CUSTOMER_TYPES, "customer_type")
    priority = _require_choice(value["priority"], PRIORITIES, "priority")
    suggested_action = _require_choice(
        value["suggested_action"], SUGGESTED_ACTIONS, "suggested_action"
    )

    confidence = value["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise AnalysisSchemaError("confidence_must_be_number")
    if not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise AnalysisSchemaError("confidence_out_of_range")

    return {
        "intent": intent,
        "product": _require_optional_text(value["product"], "product"),
        "quantity": _validate_quantity(value["quantity"]),
        "country": _require_optional_text(value["country"], "country"),
        "customer_type": customer_type,
        "priority": priority,
        "suggested_action": suggested_action,
        "confidence": float(confidence),
    }


def parse_analysis_json(content: str) -> dict[str, Any]:
    """Parse strict JSON and reject malformed, duplicated, or extra fields."""
    if not isinstance(content, str):
        raise AnalysisSchemaError("content_must_be_text")
    try:
        parsed = json.loads(
            content,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_nonstandard_number,
        )
    except AnalysisSchemaError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise AnalysisSchemaError("json_invalid") from exc
    return validate_analysis_object(parsed)
