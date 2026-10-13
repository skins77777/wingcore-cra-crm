"""Synthetic-only tests for customer message analysis and strict output validation."""
import json
import unittest

from customer_message_analyzer import (
    CustomerMessageAnalysisError,
    analyze_customer_message,
)
from customer_message_schema import AnalysisSchemaError, parse_analysis_json


class FakeProvider:
    def __init__(self, content, finish_reason="stop"):
        self.content = content
        self.finish_reason = finish_reason
        self.messages = None
        self.max_tokens = None
        self.response_format = None

    def complete(self, messages, *, max_tokens, response_format=None):
        self.messages = messages
        self.max_tokens = max_tokens
        self.response_format = response_format
        return {
            "content": self.content,
            "usage": {"prompt_tokens": 20, "completion_tokens": 15},
            "finish_reason": self.finish_reason,
        }


def output(**overrides):
    result = {
        "intent": "unknown",
        "product": None,
        "quantity": {"raw": None, "value": None, "unit": None},
        "country": None,
        "customer_type": "unknown",
        "priority": "unknown",
        "suggested_action": "human_review",
        "confidence": 0.5,
    }
    result.update(overrides)
    return result


class CustomerMessageAnalyzerTests(unittest.TestCase):
    def analyze_synthetic(self, text, fields):
        provider = FakeProvider(json.dumps(fields))
        result = analyze_customer_message(text, provider=provider)
        self.assertEqual(list(result), [
            "intent", "product", "quantity", "country", "customer_type",
            "priority", "suggested_action", "confidence",
        ])
        self.assertEqual(provider.messages[1], {"role": "user", "content": text})
        self.assertEqual(provider.response_format, {"type": "json_object"})
        self.assertEqual(provider.max_tokens, 800)
        return result

    def test_synthetic_quote_request(self):
        result = self.analyze_synthetic(
            "Synthetic: Please quote 250 units of the Demo solar controller for Kenya.",
            output(
                intent="quote_request",
                product="Demo solar controller",
                quantity={"raw": "250 units", "value": 250, "unit": "units"},
                country="Kenya",
                customer_type="potential_buyer",
                priority="normal",
                suggested_action="prepare_quote",
                confidence=0.96,
            ),
        )
        self.assertEqual(result["intent"], "quote_request")
        self.assertEqual(result["quantity"]["value"], 250)

    def test_synthetic_product_inquiry(self):
        result = self.analyze_synthetic(
            "Synthetic: Can the Demo X100 inverter work with a 48V battery?",
            output(
                intent="product_inquiry",
                product="Demo X100 inverter",
                customer_type="potential_buyer",
                priority="low",
                suggested_action="reply_with_information",
                confidence=0.91,
            ),
        )
        self.assertEqual(result["intent"], "product_inquiry")
        self.assertIsNone(result["quantity"]["value"])

    def test_synthetic_after_sales_issue(self):
        result = self.analyze_synthetic(
            "Synthetic: The Demo controller we received stopped powering on. Please help.",
            output(
                intent="after_sales",
                product="Demo controller",
                customer_type="existing_buyer",
                priority="high",
                suggested_action="human_review",
                confidence=0.97,
            ),
        )
        self.assertEqual(result["intent"], "after_sales")
        self.assertEqual(result["suggested_action"], "human_review")

    def test_rejects_extra_fields_and_duplicate_json_keys(self):
        with self.assertRaises(AnalysisSchemaError):
            parse_analysis_json(json.dumps(output(extra="not allowed")))
        with self.assertRaises(AnalysisSchemaError):
            parse_analysis_json('{"intent":"unknown","intent":"other"}')

    def test_rejects_invalid_confidence_and_truncated_output(self):
        with self.assertRaises(AnalysisSchemaError):
            parse_analysis_json(json.dumps(output(confidence=1.1)))
        provider = FakeProvider(json.dumps(output()), finish_reason="length")
        with self.assertRaises(CustomerMessageAnalysisError):
            analyze_customer_message("Synthetic text", provider=provider)

    def test_rejects_malformed_or_non_json_output(self):
        for content in ('not JSON', '```json\n{}\n```', '{"intent":"unknown","x":NaN}'):
            with self.subTest(content=content):
                with self.assertRaises(CustomerMessageAnalysisError):
                    analyze_customer_message(content, provider=FakeProvider(content))


if __name__ == "__main__":
    unittest.main()
