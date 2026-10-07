import json
import os
import base64
from typing import Dict, List
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.logger import get_logger


DEFAULT_BASE_URL = "http://127.0.0.1:4096"
MAX_MESSAGE_LENGTH = 4000
MAX_HISTORY_MESSAGES = 12
REQUEST_TIMEOUT = 180
SYSTEM_INSTRUCTION = (
    "You are Karupu, a friendly conversational AI assistant inside the ARAVI desktop app. "
    "Answer the user's questions helpfully, clearly, and concisely. Reply in the language "
    "and tone the user uses, including Tamil-English when appropriate. You are answering "
    "chat questions only: do not inspect or modify files, run commands, browse the web, "
    "or claim to have performed actions."
)

logger = get_logger("opencode_chat")


def _base_url() -> str:
    base_url = os.environ.get("OPENCODE_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/")
    if base_url not in ("http://127.0.0.1:4096", "http://localhost:4096"):
        raise ValueError("OPENCODE_BASE_URL must be the local OpenCode server at http://127.0.0.1:4096.")
    return base_url


def _request(base_url: str, path: str, method: str = "GET", payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    password = os.environ.get("OPENCODE_SERVER_PASSWORD", "")
    if password:
        username = os.environ.get("OPENCODE_SERVER_USERNAME", "opencode")
        credentials = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {credentials}"
    request = Request(
        f"{base_url}/api{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            raw_response = response.read()
    except HTTPError as error:
        if error.code in (401, 403):
            raise RuntimeError(
                "OpenCode rejected the server login. Set OPENCODE_SERVER_PASSWORD "
                "and, if needed, OPENCODE_SERVER_USERNAME for ARAVI, then restart both apps."
            ) from None
        try:
            error_data = json.loads(error.read().decode("utf-8"))
            message = error_data.get("message") or error_data.get("error")
        except (json.JSONDecodeError, AttributeError, UnicodeDecodeError):
            message = None
        detail = f": {message}" if isinstance(message, str) and message else ""
        raise RuntimeError(f"OpenCode returned HTTP {error.code}{detail}") from None
    except (URLError, TimeoutError):
        raise RuntimeError(
            "OpenCode is not running. Open a terminal and start it with "
            "'opencode serve --hostname 127.0.0.1 --port 4096', then try again."
        ) from None

    if not raw_response:
        return None
    try:
        return json.loads(raw_response.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RuntimeError("OpenCode returned an invalid response.") from error


def _conversation_prompt(message: str, history: List[Dict[str, str]]) -> str:
    previous_messages = []
    for item in history[-MAX_HISTORY_MESSAGES:]:
        if not isinstance(item, dict) or item.get("role") not in ("user", "model"):
            raise ValueError("Chat history contains an invalid message.")
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Chat history contains an empty message.")
        if len(text) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"Messages must be {MAX_MESSAGE_LENGTH} characters or fewer.")
        speaker = "User" if item["role"] == "user" else "Karupu"
        previous_messages.append(f"{speaker}: {text}")

    if not previous_messages:
        return message.strip()
    transcript = "\n".join(previous_messages)
    return f"Previous conversation:\n{transcript}\n\nUser: {message.strip()}"


def chat(message: str, history: List[Dict[str, str]] = None) -> str:
    if not isinstance(message, str) or not message.strip():
        raise ValueError("Type a message for Karupu.")
    if len(message) > MAX_MESSAGE_LENGTH:
        raise ValueError(f"Messages must be {MAX_MESSAGE_LENGTH} characters or fewer.")
    if history is None:
        history = []
    if not isinstance(history, list):
        raise ValueError("Chat history must be a list of messages.")

    prompt = _conversation_prompt(message, history)
    base_url = _base_url()
    _request(base_url, "/global/health")
    session = _request(
        base_url,
        "/session",
        method="POST",
        payload={"title": "Karupu chat"},
    )
    session_id = session.get("id") if isinstance(session, dict) else None
    if not isinstance(session_id, str) or not session_id:
        raise RuntimeError("OpenCode did not return a valid chat session.")

    try:
        result = _request(
            base_url,
            f"/session/{session_id}/message",
            method="POST",
            payload={
                "system": SYSTEM_INSTRUCTION,
                "tools": {"*": False},
                "parts": [{
                    "type": "text",
                    "text": prompt,
                }],
            },
        )
    finally:
        try:
            _request(base_url, f"/session/{session_id}", method="DELETE")
        except (RuntimeError, ValueError) as error:
            logger.error("Could not remove temporary OpenCode chat session: %s", error)

    parts = result.get("parts", []) if isinstance(result, dict) else []
    reply = "\n".join(
        part["text"]
        for part in parts
        if isinstance(part, dict)
        and part.get("type") == "text"
        and isinstance(part.get("text"), str)
    ).strip()
    if not reply:
        raise RuntimeError("OpenCode did not return a chat reply.")
    return reply
