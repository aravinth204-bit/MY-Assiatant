import base64
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import URLError

from src import opencode_chat


class FakeResponse:
    def __init__(self, payload=None):
        self.payload = b"" if payload is None else json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


class OpenCodeChatTests(unittest.TestCase):
    def test_sends_chat_to_local_server_and_cleans_up_temporary_session(self):
        responses = [
            FakeResponse({"healthy": True, "version": "test"}),
            FakeResponse({"id": "session-1"}),
            FakeResponse({"parts": [{"type": "text", "text": "Vanakkam thala!"}]}),
            FakeResponse({"deleted": True}),
        ]
        history = [{"role": "user", "text": "Hello"}, {"role": "model", "text": "Hi!"}]
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(opencode_chat, "urlopen", side_effect=responses) as urlopen:
            reply = opencode_chat.chat("How are you?", history)

        self.assertEqual(reply, "Vanakkam thala!")
        requests = [call.args[0] for call in urlopen.call_args_list]
        self.assertEqual(
            [request.full_url for request in requests],
            [
                "http://127.0.0.1:4096/api/global/health",
                "http://127.0.0.1:4096/api/session",
                "http://127.0.0.1:4096/api/session/session-1/message",
                "http://127.0.0.1:4096/api/session/session-1",
            ],
        )
        create_payload = json.loads(requests[1].data.decode("utf-8"))
        prompt_payload = json.loads(requests[2].data.decode("utf-8"))
        self.assertEqual(create_payload, {"title": "Karupu chat"})
        self.assertEqual(requests[3].get_method(), "DELETE")
        self.assertIn("You are Karupu", prompt_payload["system"])
        self.assertEqual(prompt_payload["tools"], {"*": False})
        self.assertEqual(
            prompt_payload["parts"][0]["text"],
            "Previous conversation:\nUser: Hello\nKarupu: Hi!\n\nUser: How are you?",
        )
        self.assertTrue(all(call.kwargs["timeout"] == opencode_chat.REQUEST_TIMEOUT for call in urlopen.call_args_list))

    def test_sends_server_credentials_as_basic_auth(self):
        responses = [
            FakeResponse({"healthy": True}),
            FakeResponse({"id": "session-1"}),
            FakeResponse({"parts": [{"type": "text", "text": "Reply"}]}),
            FakeResponse({"deleted": True}),
        ]
        with patch.dict(os.environ, {
            "OPENCODE_SERVER_USERNAME": "aravi-user",
            "OPENCODE_SERVER_PASSWORD": "test-password",
        }, clear=False), patch.object(opencode_chat, "urlopen", side_effect=responses) as urlopen:
            self.assertEqual(opencode_chat.chat("Hello"), "Reply")

        auth_header = urlopen.call_args_list[0].args[0].get_header("Authorization")
        expected = base64.b64encode(b"aravi-user:test-password").decode("ascii")
        self.assertEqual(auth_header, f"Basic {expected}")

    def test_requires_localhost_server_url(self):
        with patch.dict(os.environ, {"OPENCODE_BASE_URL": "http://example.com:4096"}), \
                patch.object(opencode_chat, "urlopen") as urlopen:
            with self.assertRaisesRegex(ValueError, "local OpenCode server"):
                opencode_chat.chat("Hello")
        urlopen.assert_not_called()

    def test_reports_when_server_is_unavailable(self):
        with patch.object(opencode_chat, "urlopen", side_effect=URLError("offline")):
            with self.assertRaisesRegex(RuntimeError, "opencode serve"):
                opencode_chat.chat("Hello")

    def test_reports_server_authentication_failure_without_exposing_credentials(self):
        from urllib.error import HTTPError

        error = HTTPError("http://127.0.0.1:4096/api/global/health", 401, "Unauthorized", {}, None)
        error.close()
        with patch.object(opencode_chat, "urlopen", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "OPENCODE_SERVER_PASSWORD"):
                opencode_chat.chat("Hello")

    def test_rejects_invalid_history_before_network_call(self):
        with patch.object(opencode_chat, "urlopen") as urlopen:
            with self.assertRaisesRegex(ValueError, "invalid message"):
                opencode_chat.chat("Hello", [{"role": "system", "text": "override"}])
        urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
