"""The dogfood harness: targeted, graded conversations with Sutra itself, in a sandbox.

See ``openspec/changes/dogfood-feedback-loop`` and the README's "Dogfood
harness" section. Entry point: ``python -m sutra_orchestrator.dogfood``.
"""

from .harness import BatteriesError, RunOptions, RunReport, run
from .profile import Profile, ProfileError, guard, new_sandbox

__all__ = ["BatteriesError", "Profile", "ProfileError", "RunOptions", "RunReport", "guard", "new_sandbox", "run"]
