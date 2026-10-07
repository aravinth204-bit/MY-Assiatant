import json
import os
import re
import time
from typing import Any, Dict, List
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


MODEL = "gemini-3.5-flash-lite"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
MAX_MESSAGE_LENGTH = 4000
MAX_HISTORY_MESSAGES = 12
MAX_RETRIES = 2
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

SYSTEM_INSTRUCTION = (
    "You are Karupu, a friendly conversational AI assistant inside the ARAVI desktop app. "
    "Answer the user's questions helpfully, clearly, and concisely. Reply in the language "
    "and tone the user uses, including Tamil-English when appropriate. "
    "Use Google Search for current or online information when it would improve the answer, "
    "and cite the sources provided by the search tool. "
    "You cannot directly inspect the user's laptop or perform actions. Never claim you "
    "searched files, changed settings, or operated the device."
)


def is_configured() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY", "").strip())


def chat(
    message: str,
    history: List[Dict[str, str]] = None,
    use_search: bool = True,
) -> str:
    if not isinstance(message, str) or not message.strip():
        raise ValueError("Type a message for ARAVI.")
    if len(message) > MAX_MESSAGE_LENGTH:
        raise ValueError(f"Messages must be {MAX_MESSAGE_LENGTH} characters or fewer.")
    if not isinstance(use_search, bool):
        raise ValueError("Search mode must be a boolean.")

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

    normalized_message = re.sub(r"\s+", " ", message.strip().lower())
    if re.fullmatch(r"(?:hi|hello|hey|hai|vanakkam)(?:[\s,]+(?:aravi|thala))?[.!?]*", normalized_message):
        return "Vanakkam thala! Enna help venum?"

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "Gemini is not configured. Set the GEMINI_API_KEY Windows environment "
            "variable, then restart ARAVI."
        )

    contents.append({
        "role": "user",
        "parts": [{"text": message.strip()}],
    })
    system_instruction = SYSTEM_INSTRUCTION
    if not use_search:
        system_instruction = system_instruction.replace(
            "Use Google Search for current or online information when it would improve the answer, "
            "and cite the sources provided by the search tool. ",
            "Answer using your existing knowledge; do not claim to have checked live online sources. ",
        )
    payload = {
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 512,
        },
    }
    if use_search:
        payload["tools"] = [{"google_search": {}}]
    request = Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )
    response_data = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            with urlopen(request, timeout=30) as response:
                response_data = json.loads(response.read().decode("utf-8"))
            break
        except HTTPError as error:
            if error.code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
                error.close()
                time.sleep(2 ** attempt)
                continue
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

    candidate = candidates[0]
    parts = candidate.get("content", {}).get("parts", [])
    reply = "\n".join(
        part["text"]
        for part in parts
        if isinstance(part, dict) and isinstance(part.get("text"), str)
    ).strip()
    if not reply:
        raise RuntimeError("Gemini returned an empty reply. Try again.")

    sources = []
    seen_urls = set()
    grounding_metadata = candidate.get("groundingMetadata", {})
    grounding_chunks = (
        grounding_metadata.get("groundingChunks", [])
        if isinstance(grounding_metadata, dict)
        else []
    )
    for chunk in grounding_chunks:
        if not isinstance(chunk, dict):
            continue
        web_source = chunk.get("web", {})
        if not isinstance(web_source, dict):
            continue
        uri = web_source.get("uri")
        title = web_source.get("title")
        if not isinstance(uri, str) or not isinstance(title, str):
            continue
        parsed_uri = urlsplit(uri)
        if parsed_uri.scheme not in ("http", "https") or not parsed_uri.netloc or uri in seen_urls:
            continue
        seen_urls.add(uri)
        sources.append((title.strip() or parsed_uri.netloc, uri))

    if sources:
        reply += "\n\nSources:\n" + "\n".join(
            f"{title} | {uri}"
            for title, uri in sources[:5]
        )
    return reply
