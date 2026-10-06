import json
import os
from typing import Any, Dict, List
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


MODEL = "gemini-2.5-flash"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
MAX_MESSAGE_LENGTH = 4000
MAX_HISTORY_MESSAGES = 12

SYSTEM_INSTRUCTION = (
    "You are ARAVI, a friendly laptop assistant. Reply in the language and tone "
    "the user uses, including Tamil-English when appropriate. Be concise and useful. "
    "You cannot inspect the user's laptop or perform actions. Never claim you searched "
    "files, changed settings, or operated the device; ARAVI handles those only through "
    "its separate local commands."
)


def is_configured() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY", "").strip())


def chat(message: str, history: List[Dict[str, str]] = None) -> str:
    if not isinstance(message, str) or not message.strip():
        raise ValueError("Type a message for ARAVI.")
    if len(message) > MAX_MESSAGE_LENGTH:
        raise ValueError(f"Messages must be {MAX_MESSAGE_LENGTH} characters or fewer.")

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "Gemini is not configured. Set the GEMINI_API_KEY Windows environment "
            "variable, then restart ARAVI."
        )

    if history is None:
        history = []
    if not isinstance(history, list):
        raise ValueError("Chat history must be a list of messages.")

    contents = []
    for item in history[-MAX_HISTORY_MESSAGES:]:
        if not isinstance(item, dict) or item.get("role") not in ("user", "model"):
            raise ValueError("Chat history contains an invalid message.")
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Chat history contains an empty message.")
        if len(text) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"Messages must be {MAX_MESSAGE_LENGTH} characters or fewer.")
        contents.append({
            "role": item["role"],
            "parts": [{"text": text}],
        })

    contents.append({
        "role": "user",
        "parts": [{"text": message.strip()}],
    })
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 512,
        },
    }
    request = Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=30) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        try:
            error_data = json.loads(error.read().decode("utf-8"))
            message_text = error_data.get("error", {}).get("message")
        except (json.JSONDecodeError, AttributeError):
            message_text = None
        detail = f": {message_text}" if message_text else ""
        raise RuntimeError(f"Gemini API returned HTTP {error.code}{detail}") from None
    except URLError:
        raise RuntimeError("Could not connect to Google Gemini. Check your internet connection.") from None
    except TimeoutError:
        raise RuntimeError("Google Gemini timed out. Try again in a moment.") from None
    except json.JSONDecodeError as error:
        raise RuntimeError("Gemini returned an invalid response.") from error

    if not isinstance(response_data, dict):
        raise RuntimeError("Gemini returned an invalid response.")
    candidates = response_data.get("candidates", [])
    if not candidates:
        raise RuntimeError("Gemini did not return a reply. Try rephrasing your message.")

    parts = candidates[0].get("content", {}).get("parts", [])
    reply = "\n".join(
        part["text"]
        for part in parts
        if isinstance(part, dict) and isinstance(part.get("text"), str)
    ).strip()
    if not reply:
        raise RuntimeError("Gemini returned an empty reply. Try again.")
    return reply
