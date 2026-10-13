"""Offline unit tests for the shared provider using synthetic text and image input."""
import json
import unittest
from io import BytesIO
from urllib.request import Request
from unittest.mock import patch

from ai_provider import DEFAULT_CONFIG_PATH, ModelConfig, create_provider, load_model_config


def synthetic_response(content):
    return BytesIO(
        json.dumps(
            {
                "choices": [
                    {"message": {"content": content}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
            }
        ).encode("utf-8")
    )


def test_config():
    return ModelConfig(
        provider="deepseek",
        base_url="https://api.deepseek.com",
        model="synthetic-model",
        api_key="SYNTHETIC-KEY-NOT-USED",
        timeout_seconds=5,
    )


class ProviderTests(unittest.TestCase):
    def test_loads_existing_config_shape_without_reading_local_secrets(self):
        with patch(
            "ai_provider._read_env_file",
            return_value={
                "MODEL_PROVIDER": "deepseek",
                "MODEL_BASE_URL": "https://api.deepseek.com",
                "MODEL_NAME": "synthetic-model",
                "DEEPSEEK_API_KEY": "SYNTHETIC-KEY-NOT-USED",
                "MODEL_TIMEOUT_SECONDS": "5",
            },
        ) as read_config:
            config = load_model_config()

        read_config.assert_called_once_with(DEFAULT_CONFIG_PATH)
        self.assertEqual(config.provider, "deepseek")
        self.assertEqual(config.model, "synthetic-model")
        self.assertEqual(config.timeout_seconds, 5)

    def run_synthetic_request(self, messages, content):
        captured = {}

        def fake_opener(request, timeout):
            self.assertIsInstance(request, Request)
            captured["url"] = request.full_url
            captured["headers"] = request.headers
            captured["timeout"] = timeout
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return synthetic_response(content)

        from deepseek_provider import DeepSeekProvider

        provider = create_provider(config=test_config(), opener=fake_opener)
        self.assertIsInstance(provider, DeepSeekProvider)
        result = provider.complete(messages, max_tokens=128)
        self.assertEqual(captured["url"], "https://api.deepseek.com/chat/completions")
        self.assertEqual(captured["timeout"], 5)
        self.assertEqual(captured["payload"]["response_format"], {"type": "json_object"})
        self.assertEqual(captured["payload"]["stream"], False)
        self.assertEqual(result["content"], content)
        self.assertEqual(result["usage"]["total_tokens"], 18)
        self.assertEqual(result["finish_reason"], "stop")
        return captured

    def test_synthetic_text_request(self):
        message = {"role": "user", "content": "Synthetic test message only."}
        captured = self.run_synthetic_request(
            [message], '{"intent":"unknown"}'
        )
        self.assertEqual(captured["payload"]["messages"], [message])

    def test_synthetic_image_request(self):
        message = {
            "role": "user",
            "content": [
                {"type": "text", "text": "Synthetic image test only."},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/png;base64,c3ludGhldGlj",
                        "detail": "high",
                    },
                },
            ],
        }
        captured = self.run_synthetic_request(
            [message], '{"intent":"unknown"}'
        )
        self.assertEqual(captured["payload"]["messages"], [message])


if __name__ == "__main__":
    unittest.main()
