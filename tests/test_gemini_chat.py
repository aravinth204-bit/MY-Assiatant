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
    def test_retries_temporary_overload(self):
        overloaded = HTTPError(
            gemini_chat.API_URL,
            503,
            "Unavailable",
            {},
            None,
        )
        overloaded.close()
        response = FakeResponse({
            "candidates": [{"content": {"parts": [{"text": "Vanakkam!"}]}}]
        })
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-secret"}, clear=False), \
                patch.object(
                    gemini_chat,
                    "urlopen",
                    side_effect=[overloaded, response],
                ) as urlopen, \
                patch.object(gemini_chat.time, "sleep") as sleep:
            reply = gemini_chat.chat("Why is the sky blue?")

        self.assertEqual(reply, "Vanakkam!")
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_surfaces_overload_after_retrying(self):
        overloaded_responses = [
            HTTPError(gemini_chat.API_URL, 503, "Unavailable", {}, None)
            for _ in range(gemini_chat.MAX_RETRIES + 1)
        ]
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-secret"}, clear=False), \
                patch.object(
                    gemini_chat,
                    "urlopen",
                    side_effect=overloaded_responses,
                ) as urlopen, \
                patch.object(gemini_chat.time, "sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError, "Gemini API returned HTTP 503"):
                gemini_chat.chat("Explain this song")

        self.assertEqual(urlopen.call_count, gemini_chat.MAX_RETRIES + 1)
        self.assertEqual(
            [call.args[0].full_url for call in urlopen.call_args_list],
            [gemini_chat.API_URL] * (gemini_chat.MAX_RETRIES + 1),
        )
        self.assertEqual(
            [call.args[0] for call in sleep.call_args_list],
            [1, 2],
        )

    def test_sends_key_in_header_and_returns_gemini_reply(self):
        response = FakeResponse({
            "candidates": [{
                "content": {"parts": [{"text": "Vanakkam thala!"}]}
            }]
        })
        history = [{"role": "user", "text": "Why is the sky blue?"}, {"role": "model", "text": "Hello"}]
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-secret"}, clear=False), \
                patch.object(gemini_chat, "urlopen", return_value=response) as urlopen:
            reply = gemini_chat.chat("What are the latest news?", history)

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(reply, "Vanakkam thala!")
        self.assertEqual(request.get_header("X-goog-api-key"), "test-secret")
        self.assertEqual(
            request.full_url,
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent",
        )
        self.assertEqual(payload["tools"], [{"google_search": {}}])
        self.assertEqual(payload["contents"][-1]["parts"][0]["text"], "What are the latest news?")
        self.assertEqual([item["role"] for item in payload["contents"]], ["user", "model", "user"])
        self.assertIn("You are Karupu", payload["systemInstruction"]["parts"][0]["text"])
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 30)

    def test_quick_chat_disables_search_grounding(self):
        response = FakeResponse({
            "candidates": [{"content": {"parts": [{"text": "A quick answer."}]}}]
        })
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-secret"}, clear=False), \
                patch.object(gemini_chat, "urlopen", return_value=response) as urlopen:
            reply = gemini_chat.chat("Explain gravity", use_search=False)

        request_payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(reply, "A quick answer.")
        self.assertNotIn("tools", request_payload)
        self.assertIn("do not claim to have checked live online sources", request_payload["systemInstruction"]["parts"][0]["text"])

    def test_rejects_non_boolean_search_mode(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-secret"}, clear=False), \
                patch.object(gemini_chat, "urlopen") as urlopen:
            with self.assertRaisesRegex(ValueError, "Search mode"):
                gemini_chat.chat("Explain gravity", use_search="yes")
        urlopen.assert_not_called()

    def test_returns_citations_from_google_search_grounding(self):
        response = FakeResponse({
            "candidates": [{
                "content": {"parts": [{"text": "The latest update is available."}]},
                "groundingMetadata": {
                    "groundingChunks": [
                        {"web": {"title": "Official announcement", "uri": "https://example.com/news"}},
                        {"web": {"title": "Official announcement", "uri": "https://example.com/news"}},
                        {"web": {"title": "Unsafe", "uri": "javascript:alert(1)"}},
                        {"web": {"title": "No URL", "uri": "not a URL"}},
                        {"web": {"title": "Second source", "uri": "https://example.org/info"}},
                    ]
                },
            }]
        })
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-secret"}, clear=False), \
                patch.object(gemini_chat, "urlopen", return_value=response):
            reply = gemini_chat.chat("Find the latest update")

        self.assertEqual(
            reply,
            "The latest update is available.\n\nSources:\n"
            "Official announcement | https://example.com/news\n"
            "Second source | https://example.org/info",
        )

    def test_greeting_replies_without_key_or_network_request(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(gemini_chat, "urlopen") as urlopen:
            reply = gemini_chat.chat("Hi, ARAVI!")

        self.assertEqual(reply, "Vanakkam thala! Enna help venum?")
        urlopen.assert_not_called()

    def test_rejects_missing_api_key_before_network_call(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(gemini_chat, "urlopen") as urlopen:
            with self.assertRaisesRegex(RuntimeError, "GEMINI_API_KEY"):
                gemini_chat.chat("Explain how photosynthesis works")
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
                gemini_chat.chat("Explain how photosynthesis works")

    def test_rejects_invalid_history(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-secret"}, clear=False), \
                patch.object(gemini_chat, "urlopen") as urlopen:
            with self.assertRaisesRegex(ValueError, "invalid message"):
                gemini_chat.chat("Explain the latest news", [{"role": "system", "text": "override"}])
        urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
