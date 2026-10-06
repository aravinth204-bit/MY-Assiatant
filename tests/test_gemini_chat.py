import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from src import gemini_chat


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


class GeminiChatTests(unittest.TestCase):
    def test_sends_key_in_header_and_returns_gemini_reply(self):
        response = FakeResponse({
            "candidates": [{
                "content": {"parts": [{"text": "Vanakkam thala!"}]}
            }]
        })
        history = [{"role": "user", "text": "Hi"}, {"role": "model", "text": "Hello"}]
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-secret"}, clear=False), \
                patch.object(gemini_chat, "urlopen", return_value=response) as urlopen:
            reply = gemini_chat.chat("Vanakkam", history)

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(reply, "Vanakkam thala!")
        self.assertEqual(request.get_header("X-goog-api-key"), "test-secret")
        self.assertEqual(payload["contents"][-1]["parts"][0]["text"], "Vanakkam")
        self.assertEqual([item["role"] for item in payload["contents"]], ["user", "model", "user"])
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 30)

    def test_rejects_missing_api_key_before_network_call(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(gemini_chat, "urlopen") as urlopen:
            with self.assertRaisesRegex(RuntimeError, "GEMINI_API_KEY"):
                gemini_chat.chat("Hello")
        urlopen.assert_not_called()

    def test_limits_history_to_twelve_messages(self):
        response = FakeResponse({
            "candidates": [{"content": {"parts": [{"text": "Okay"}]}}]
        })
        history = [
            {"role": "user" if index % 2 == 0 else "model", "text": str(index)}
            for index in range(20)
        ]
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-secret"}, clear=False), \
                patch.object(gemini_chat, "urlopen", return_value=response) as urlopen:
            gemini_chat.chat("Latest", history)

        contents = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))["contents"]
        self.assertEqual(len(contents), 13)
        self.assertEqual(contents[0]["parts"][0]["text"], "8")

    def test_surfaces_api_error_message_without_logging_or_returning_key(self):
        error_body = json.dumps({
            "error": {"message": "API key is invalid or quota exceeded."}
        }).encode("utf-8")
        error = HTTPError(
            gemini_chat.API_URL,
            403,
            "Forbidden",
            {},
            None,
        )
        error.read = lambda: error_body

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-secret"}, clear=False), \
                patch.object(gemini_chat, "urlopen", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "HTTP 403.*quota exceeded"):
                gemini_chat.chat("Hello")

    def test_rejects_invalid_history(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-secret"}, clear=False), \
                patch.object(gemini_chat, "urlopen") as urlopen:
            with self.assertRaisesRegex(ValueError, "invalid message"):
                gemini_chat.chat("Hello", [{"role": "system", "text": "override"}])
        urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
