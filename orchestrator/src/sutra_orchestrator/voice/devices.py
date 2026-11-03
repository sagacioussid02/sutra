"""Which way sound comes out, so interrupting can be on by default only where it is safe."""

from __future__ import annotations

import re

_HEADPHONES = re.compile(r"headphone|headset|airpods|earbud|earphone|buds|beats|bluetooth|usb audio", re.IGNORECASE)
_SPEAKERS = re.compile(r"speaker|display|hdmi|monitor|airplay|homepod|soundbar", re.IGNORECASE)


def looks_like_headphones(name: str) -> bool:
    """True if an output device name suggests headphones. Built-in speakers and displays are not."""
    return bool(_HEADPHONES.search(name)) and not _SPEAKERS.search(name)


def output_is_headphones() -> bool:
    """Whether the current default output looks like headphones. Any failure means no: the safe answer,
    because with speakers on, interrupting would make Sutra hear itself and cut itself off."""
    try:
        import sounddevice as sd

        return looks_like_headphones(str(sd.query_devices(kind="output")["name"]))
    except Exception:
        return False
