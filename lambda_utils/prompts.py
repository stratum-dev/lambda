"""Prompt loading and Jinja2 template rendering.

User-role messages (``2-user.md``) may contain ``{{ }}`` Jinja2 variables.
They are pre-compiled into :class:`jinja2.Template` objects at load time and
rendered with keyword arguments at call time.
"""

from __future__ import annotations

import copy
from pathlib import Path

from jinja2 import Environment, StrictUndefined, Template

# ---------------------------------------------------------------------------
# Jinja2 environment (module-level, reusable)
# ---------------------------------------------------------------------------

_env = Environment(undefined=StrictUndefined)

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def load_prompt_messages(prompt_dir: Path) -> list[dict]:
    """Load conversation prompt files from *prompt_dir*.

    Scans for ``*.md`` files whose names match ``<order>-<role>.md``,
    e.g. ``0-system.md``, ``1-assistant.md``, ``2-user.md``.
    Files are sorted by *order* (numeric prefix) so you can define an
    arbitrary multi-turn conversation — any number of turns, any role
    sequence, including consecutive same-role messages.

    User-role content may contain ``{{ }}`` Jinja2 markers and is stored
    as a pre-compiled :class:`~jinja2.Template` instead of a plain string.

    Returns a list of ``{"role": str, "content": str | Template}`` dicts.
    Files that don't match the naming convention are silently skipped.
    """
    import re

    messages: list[dict] = []
    pattern = re.compile(r"^(\d+)-(system|assistant|user)\.md$")

    entries: list[tuple[int, str, Path]] = []
    for fpath in prompt_dir.glob("*.md"):
        m = pattern.match(fpath.name)
        if not m:
            continue
        order = int(m.group(1))
        role = m.group(2)
        entries.append((order, role, fpath))

    entries.sort(key=lambda e: e[0])

    for _, role, fpath in entries:
        text = fpath.read_text(encoding="utf-8")
        if role == "user":
            messages.append({"role": role, "content": _env.from_string(text)})
        else:
            messages.append({"role": role, "content": text})
    return messages


def render_messages(messages: list[dict], **kwargs: str) -> list[dict]:
    """Return a deep copy of *messages* with Jinja2 user templates rendered.

    Each keyword argument is available as a ``{{ name }}`` variable in the
    Jinja2 templates.  Only user-role messages are rendered; system and
    assistant messages pass through unchanged.

    Example::

        msgs = render_messages(
            base,
            cpg=cpg_str,
            context=context_str,
        )
    """
    result: list[dict] = []
    for msg in messages:
        content = msg["content"]
        if msg["role"] == "user" and isinstance(content, Template):
            result.append({"role": msg["role"], "content": content.render(**kwargs)})
        else:
            result.append(copy.deepcopy(msg))
    return result


# Backward-compatible alias
inject_placeholders = render_messages
