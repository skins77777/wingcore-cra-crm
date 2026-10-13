"""Adapt one locally collected inbound email to the customer text analyzer."""
from __future__ import annotations

import json
from email.header import decode_header, make_header
from typing import Any, Mapping

from ai_provider import AIProvider
from customer_message_analyzer import analyze_customer_message


class MailMessageRejected(ValueError):
    """Raised when a mail record is not a complete, valid inbound text email."""


def _parse_headers(value: Any) -> Mapping[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError) as exc:
            raise MailMessageRejected("email_headers_invalid") from exc
    if not isinstance(value, Mapping):
        raise MailMessageRejected("email_headers_invalid")
    return value


def _subject_from_headers(headers: Mapping[str, Any]) -> str | None:
    matches = [
        value
        for key, value in headers.items()
        if isinstance(key, str) and key.casefold() == "subject"
    ]
    if len(matches) > 1:
        raise MailMessageRejected("email_subject_ambiguous")
    if not matches:
        return None
    raw_subject = matches[0]
    if not isinstance(raw_subject, str):
        raise MailMessageRejected("email_subject_invalid")
    try:
        subject = str(make_header(decode_header(raw_subject))).strip()
    except (LookupError, UnicodeError, ValueError) as exc:
        raise MailMessageRejected("email_subject_invalid") from exc
    return subject or None


def _customer_text(record: Mapping[str, Any]) -> str:
    if record.get("direction") != "inbound":
        raise MailMessageRejected("email_not_inbound")

    headers = _parse_headers(record.get("headers"))
    subject = _subject_from_headers(headers)

    body = record.get("text")
    if not isinstance(body, str) or not body.strip():
        raise MailMessageRejected("email_body_empty")
    if "\ufffd" in body:
        raise MailMessageRejected("email_body_decode_error")

    completeness = record.get("completeness")
    if completeness == "text_decode_error":
        raise MailMessageRejected("email_body_decode_error")
    if completeness == "text_truncated":
        raise MailMessageRejected("email_body_truncated")
    if completeness != "text_only":
        raise MailMessageRejected("email_text_completeness_invalid")

    if subject:
        return f"Subject:\n{subject}\n\nMessage:\n{body}"
    return f"Message:\n{body}"


def analyze_mail_message(
    record: Mapping[str, Any],
    *,
    provider: AIProvider | None = None,
) -> dict[str, Any]:
    """Analyze a single inbound email without persisting its text or metadata."""
    if not isinstance(record, Mapping):
        raise MailMessageRejected("email_record_invalid")
    customer_text = _customer_text(record)
    return analyze_customer_message(customer_text, provider=provider)
