"""LLM interaction helpers — calling, retrying, and JSON parsing."""

from __future__ import annotations

import json
import re
import time

from lambda_utils.config import get_llm_client, MODEL, RETRY_DELAY


def call_llm(
    messages: list[dict],
    max_tokens: int = 4096,
    temperature: float = 0.0,
    use_json_format: bool = True,
) -> str:
    """Send *messages* to the configured LLM and return the text response.

    Tries with ``response_format={"type": "json_object"}`` first; falls back
    to no ``response_format`` on exception (some providers don't support it).
    """
    client = get_llm_client()
    kwargs: dict = dict(
        model=MODEL,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    if use_json_format:
        kwargs["response_format"] = {"type": "json_object"}

    try:
        response = client.chat.completions.create(**kwargs)
    except Exception:
        kwargs.pop("response_format", None)
        response = client.chat.completions.create(**kwargs)

    return response.choices[0].message.content


def call_llm_with_retry(
    messages: list[dict],
    max_tokens: int = 4096,
    temperature: float = 0.0,
    use_json_format: bool = True,
) -> str:
    """Call the LLM, retrying indefinitely until success.

    Keeps retrying on any failure (network error, empty response, etc.) with
    ``RETRY_DELAY`` seconds backoff between attempts.  Only returns a valid
    non-empty response — never gives up.
    """
    while True:
        try:
            response_text = call_llm(
                messages,
                max_tokens=max_tokens,
                temperature=temperature,
                use_json_format=use_json_format,
            )
            if not response_text or not response_text.strip():
                raise ValueError("LLM returned empty response")
            return response_text
        except Exception:
            time.sleep(RETRY_DELAY)


def extract_json(text: str) -> dict:
    """Robust JSON extraction from an LLM response.

    Tries, in order:

    1. Parse *text* directly.
    2. Extract from a `` ```json ``` `` fenced code block.
    3. Extract from a `` ``` ``` `` (no-annotation) code block.
    4. Find the outermost ``{...}`` via bracket matching.

    Raises :exc:`ValueError` if all strategies fail.
    """
    text = text.strip()
    if not text:
        raise ValueError("Empty LLM response — nothing to parse")

    # 1 – direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2 – ```json … ```
    m = re.search(r"```json\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # 3 – ``` … ```
    m = re.search(r"```\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # 4 – bracket matching: find first '{' and its matching '}'
    start = text.find("{")
    if start >= 0:
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break

    raise ValueError(f"Failed to extract JSON from LLM response:\n{text[:800]}")
