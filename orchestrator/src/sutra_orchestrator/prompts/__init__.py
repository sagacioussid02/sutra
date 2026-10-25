"""Prompt files shipped with the package."""

from importlib.resources import files


def load_prompt(name: str) -> str:
    return files(__package__).joinpath(name).read_text(encoding="utf-8")
