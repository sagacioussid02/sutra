"""Turn untrusted findings into a short dated note. Tools are off, so nothing in them can act."""

from __future__ import annotations

import re
from datetime import datetime

from ..agents.types import Findings
from ..model import ModelClient
from ..prompts import load_prompt

SUMMARY_CHARS = 380
_URL = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)


def clean(text: str) -> str:
    text = _URL.sub("", text)
    return " ".join(text.replace("*", " ").replace("#", " ").split())


async def summarize(model: ModelClient, brief: str, findings: Findings, today: datetime) -> str:
    """The dated summary, or "" when the findings held nothing useful."""
    state = "partial (stopped early)" if findings.partial else "complete"
    block = f'<untrusted_findings research="{state}">\n{findings.text}\n</untrusted_findings>'
    response = await model.complete(
        system=load_prompt("idle_summary.md"),
        messages=[{"role": "user", "content": [{"type": "text", "text": f"Task: {brief}\n\n{block}"}]}],
        tools=[],
        allow_tools=False,
    )
    text = clean(response.text)
    if not text or text.upper().startswith("NONE"):
        return ""
    prefix = f"As of {today:%B} {today.day}, {today.year}: "
    return _fit(prefix + text)


def _fit(text: str, limit: int = SUMMARY_CHARS) -> str:
    """Cut to the limit at a sentence end (or, failing that, a word end) so nothing is spoken half-finished."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    if end >= limit // 2:
        return cut[: end + 1]
    return cut[: cut.rfind(" ")].rstrip(" ,;:") + "."

