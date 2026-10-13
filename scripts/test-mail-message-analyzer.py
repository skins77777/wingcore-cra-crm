"""Synthetic-only tests for adapting mail records to customer analysis."""
import json
import unittest

from mail_message_analyzer import MailMessageRejected, analyze_mail_message


class FakeProvider:
    def __init__(self, result):
        self.result = result
        self.messages = None
        self.calls = 0

    def complete(self, messages, *, max_tokens, response_format=None):
        self.calls += 1
        self.messages = messages
        return {
            "content": json.dumps(self.result),
            "usage": {"prompt_tokens": 12, "completion_tokens": 9},
            "finish_reason": "stop",
        }


def base_result():
    return {
        "intent": "unknown",
        "product": None,
        "quantity": {"raw": None, "value": None, "unit": None},
        "country": None,
        "customer_type": "unknown",
        "priority": "unknown",
        "suggested_action": "human_review",
        "confidence": 0.5,
    }


def mail_record(subject, body, **extra):
    record = {
        "direction": "inbound",
        "headers": json.dumps(
            {
                "Subject": subject,
                "From": "Private Sender <sender@example.invalid>",
                "To": "private-recipient@example.invalid",
                "X-Internal-Note": "DO-NOT-SEND-METADATA",
            }
        ),
        "text": body,
        "completeness": "text_only",
        "metadata": {"private": "DO-NOT-SEND-METADATA"},
        "attachments": ["DO-NOT-SEND-ATTACHMENT"],
    }
    record.update(extra)
    return record


class MailMessageAnalyzerTests(unittest.TestCase):
    def analyze_synthetic(self, record, result):
        provider = FakeProvider(result)
        analysis = analyze_mail_message(record, provider=provider)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(
            list(analysis),
            [
                "intent", "product", "quantity", "country", "customer_type",
                "priority", "suggested_action", "confidence",
            ],
        )
        user_message = provider.messages[1]["content"]
        self.assertIn(record["headers"] and json.loads(record["headers"])["Subject"], user_message)
        self.assertIn(record["text"], user_message)
        for private_value in (
            "sender@example.invalid",
            "private-recipient@example.invalid",
            "DO-NOT-SEND-METADATA",
            "DO-NOT-SEND-ATTACHMENT",
        ):
            self.assertNotIn(private_value, user_message)
        return analysis

    def test_synthetic_quote_request(self):
        result = base_result()
        result.update(
            intent="quote_request",
            product="Demo charger",
            quantity={"raw": "20 pieces", "value": 20, "unit": "pieces"},
            country="Kenya",
            customer_type="potential_buyer",
            priority="normal",
            suggested_action="prepare_quote",
            confidence=0.94,
        )
        analysis = self.analyze_synthetic(
            mail_record(
                "Synthetic quote request",
                "Synthetic only: Please quote 20 pieces of the Demo charger for Kenya.",
            ),
            result,
        )
        self.assertEqual(analysis["intent"], "quote_request")

    def test_synthetic_product_inquiry(self):
        result = base_result()
        result.update(
            intent="product_inquiry",
            product="Demo X100 inverter",
            customer_type="potential_buyer",
            priority="low",
            suggested_action="reply_with_information",
            confidence=0.9,
        )
        analysis = self.analyze_synthetic(
            mail_record(
                "Synthetic product question",
                "Synthetic only: Can the Demo X100 work with a 48V battery?",
            ),
            result,
        )
        self.assertEqual(analysis["intent"], "product_inquiry")

    def test_synthetic_after_sales_message(self):
        result = base_result()
        result.update(
            intent="after_sales",
            product="Demo controller",
            customer_type="existing_buyer",
            priority="high",
            suggested_action="human_review",
            confidence=0.96,
        )
        analysis = self.analyze_synthetic(
            mail_record(
                "Synthetic support request",
                "Synthetic only: The Demo controller stopped powering on. Please help.",
            ),
            result,
        )
        self.assertEqual(analysis["intent"], "after_sales")

    def test_rejects_non_inbound_without_calling_provider(self):
        provider = FakeProvider(base_result())
        record = mail_record("Synthetic", "Synthetic body", direction="outbound")
        with self.assertRaisesRegex(MailMessageRejected, "email_not_inbound"):
            analyze_mail_message(record, provider=provider)
        self.assertEqual(provider.calls, 0)

    def test_rejects_empty_truncated_and_invalid_mail(self):
        provider = FakeProvider(base_result())
        cases = [
            (mail_record("Synthetic", "  "), "email_body_empty"),
            (mail_record("Synthetic", "Synthetic damaged text", completeness="text_decode_error"), "email_body_decode_error"),
            (mail_record("Synthetic", "Synthetic body", completeness="text_truncated"), "email_body_truncated"),
            (mail_record("Synthetic", "Synthetic body", completeness="no_supported_text"), "email_text_completeness_invalid"),
            (mail_record("Synthetic", "Synthetic body", headers="not-json"), "email_headers_invalid"),
            ({"direction": "inbound"}, "email_headers_invalid"),
        ]
        for record, error in cases:
            with self.subTest(error=error):
                with self.assertRaisesRegex(MailMessageRejected, error):
                    analyze_mail_message(record, provider=provider)
        self.assertEqual(provider.calls, 0)


if __name__ == "__main__":
    unittest.main()
