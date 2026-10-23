"""Prompt loading.

Prompts live in versioned markdown files beside this module and are never
inlined in Python, per CLAUDE.md — the version in the filename is what gets
logged with every call, so a caption can always be traced to the exact text
that produced it.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

PROMPT_DIR = Path(__file__).parent


@lru_cache
def load_prompt(prompt_id: str) -> str:
    """Read `<prompt_id>.md`. Cached: prompts do not change at runtime."""
    path = PROMPT_DIR / f"{prompt_id}.md"
    if not path.is_file():
        available = sorted(p.stem for p in PROMPT_DIR.glob("*.md"))
        raise FileNotFoundError(f"unknown prompt {prompt_id!r}; have {available}")
    return path.read_text(encoding="utf-8")


def render_prompt(prompt_id: str, **values: object) -> str:
    """Load a prompt and substitute `{placeholders}`.

    str.format is wrong here — prompts contain literal braces in their JSON
    examples — so placeholders are replaced one at a time.
    """
    text = load_prompt(prompt_id)
    for key, value in values.items():
        text = text.replace("{" + key + "}", str(value))
    return text
