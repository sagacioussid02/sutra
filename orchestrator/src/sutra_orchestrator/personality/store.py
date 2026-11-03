"""The humor profile: dials, style scores, and how jokes have been received."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .db import open_personality

PERSONALITY_DB = "personality.db"

STYLES = {
    "dry": "dry understatement, deadpan and very short",
    "self": "a gentle joke about being an AI or about your own limits, never about the user",
    "tease": "light, affectionate teasing about something the user themselves said in this conversation, nothing sensitive",
    "wordplay": "a light pun or play on words tied to the topic",
    "absurd": "a playful, exaggerated or absurd comparison",
}
START_SCORE = {"dry": 0.5, "self": 0.5, "tease": 0.3, "wordplay": 0.5, "absurd": 0.5}
SCORE_LOW, SCORE_HIGH = 0.05, 0.95
LEVEL_DEFAULT, LEVEL_MAX, AUTO_LEVEL_MAX = 3, 10, 6
VARIETY_DEFAULT, VARIETY_LOW, VARIETY_HIGH = 0.7, 0.2, 2.0
REACTIONS = ("laughed", "smiled", "neutral", "groaned", "annoyed")
STEP = {"laughed": 0.12, "smiled": 0.05, "neutral": -0.02, "groaned": -0.10, "annoyed": -0.20}
WINDOW = 10  # judged jokes between automatic level changes


class PersonalityStore:
    def __init__(self, directory: str | Path) -> None:
        self._conn = open_personality(Path(directory) / PERSONALITY_DB)
        with self._conn:
            for style, score in START_SCORE.items():
                self._conn.execute("INSERT OR IGNORE INTO styles (style, score) VALUES (?, ?)", (style, score))

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------- meta

    def _get(self, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def _set(self, key: str, value: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    @property
    def level(self) -> int:
        raw = self._get("level")
        return LEVEL_DEFAULT if raw is None else int(raw)

    def set_level(self, level: int) -> int:
        level = max(0, min(LEVEL_MAX, int(level)))
        if level > 0:
            self._set("last_level", str(level))
        self._set("level", str(level))
        return level

    @property
    def last_level(self) -> int:
        return int(self._get("last_level") or LEVEL_DEFAULT)

    @property
    def variety(self) -> float:
        raw = self._get("variety")
        return VARIETY_DEFAULT if raw is None else float(raw)

    def set_variety(self, value: float) -> float:
        value = max(VARIETY_LOW, min(VARIETY_HIGH, float(value)))
        self._set("variety", str(value))
        return value

    @property
    def enabled(self) -> bool:
        return self._get("enabled") != "0"

    def set_enabled(self, on: bool) -> None:
        self._set("enabled", "1" if on else "0")

    # ----------------------------------------------------------------- styles

    def scores(self) -> dict[str, float]:
        rows = self._conn.execute("SELECT style, score FROM styles")
        return {r["style"]: r["score"] for r in rows}

    def style_rows(self) -> list[sqlite3.Row]:
        return list(self._conn.execute("SELECT * FROM styles ORDER BY style"))

    def set_score(self, style: str, score: float) -> None:
        score = max(SCORE_LOW, min(SCORE_HIGH, float(score)))
        with self._conn:
            self._conn.execute("UPDATE styles SET score = ? WHERE style = ?", (score, style))

    def record_reaction(self, style: str, reaction: str) -> None:
        """One joke that was made and how it was received. Moves the style's score and the judged window."""
        assert reaction in REACTIONS and style in STYLES
        score = max(SCORE_LOW, min(SCORE_HIGH, self.scores()[style] + STEP[reaction]))
        with self._conn:
            self._conn.execute(
                f"UPDATE styles SET score = ?, tries = tries + 1, {reaction} = {reaction} + 1 WHERE style = ?",
                (score, style),
            )
        window = json.loads(self._get("window") or "[]") + [reaction]
        if len(window) >= WINDOW:
            good = sum(1 for r in window if r in ("laughed", "smiled"))
            bad = sum(1 for r in window if r in ("groaned", "annoyed"))
            if good >= 6 and self.level < AUTO_LEVEL_MAX:
                self.set_level(self.level + 1)
            elif bad >= 4 and self.level > 0:
                self.set_level(self.level - 1)
            window = []
        self._set("window", json.dumps(window))

    def reset(self) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM meta")
            for style, score in START_SCORE.items():
                self._conn.execute(
                    "UPDATE styles SET score = ?, tries = 0, laughed = 0, smiled = 0, neutral = 0,"
                    " groaned = 0, annoyed = 0 WHERE style = ?",
                    (score, style),
                )
