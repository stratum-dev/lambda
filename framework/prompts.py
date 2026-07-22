"""Prompt loading and placeholder injection.

The placeholder constants below match the ``{{ }}`` markers found in the
markdown prompt templates under ``./prompts/``.
"""

import copy
from pathlib import Path

# ---------------------------------------------------------------------------
# Placeholder constants — must match the literal strings in the .md templates
# ---------------------------------------------------------------------------

PH_CPG = "{{ 程序属性图在这里注入 }}"
PH_CONTEXT = "{{ 漏洞先验上下文在这里注入 }}"
PH_KNOWLEDGE = "{{ 漏洞知识在这里注入 }}"

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def load_prompt_messages(prompt_dir: Path) -> list[dict]:
    """Load the conversation prompt files from *prompt_dir*.

    Reads ``0-system.md`` → ``role: system``,
    ``1-assistant.md`` → ``role: assistant``,
    ``2-user.md`` → ``role: user`` (may contain ``{{ }}`` placeholders).

    Returns a list of ``{"role": str, "content": str}`` dicts.  Files that
    don't exist are silently skipped.
    """
    messages: list[dict] = []
    for name, role in [
        ("0-system.md", "system"),
        ("1-assistant.md", "assistant"),
        ("2-user.md", "user"),
    ]:
        fpath = prompt_dir / name
        if fpath.exists():
            messages.append(
                {"role": role, "content": fpath.read_text(encoding="utf-8")}
            )
    return messages


def inject_placeholders(messages: list[dict], **kwargs: str) -> list[dict]:
    """Return a deep copy of *messages* with placeholders replaced.

    Placeholder replacement only happens in user-role messages.
    Each keyword argument's **key** is the literal placeholder string
    (including ``{{ }}``) and its **value** is the replacement text.

    Example::

        msgs = inject_placeholders(
            base,
            **{PH_CPG: cpg_str, PH_CONTEXT: context_str},
        )
    """
    result = copy.deepcopy(messages)
    for msg in result:
        if msg["role"] == "user":
            for placeholder, value in kwargs.items():
                msg["content"] = msg["content"].replace(placeholder, value)
    return result
