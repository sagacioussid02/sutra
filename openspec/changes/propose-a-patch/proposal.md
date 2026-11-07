## Why

Sutra's tools and agents cover what has been built so far. A request that fits none of them ("track my gym streak", "check the bus times") today ends at "I can't do that". The next step is not a bigger prompt but a missing capability, and the person best placed to decide whether Sutra should have it is the user.

An assistant that rewrites its own running code is the wrong answer. The confirmation gate, the safety modes and adaptive authentication are exactly the code that must not be editable by the thing they restrict. So this change adds a safer shape: Sutra may *draft* the missing capability on a git branch, test it where it cannot hurt anything, and hand the user a proposal. The user reviews and merges, or throws it away. Nothing Sutra writes runs in Sutra until a human has read it.

## What Changes

- **A `propose_capability` local tool.** When nothing fits, the assistant offers: "I can't do that yet. Want me to draft a way to? You'd review it before anything changes." The user's yes starts a patch run through the same ask-first and background-job path that `ephemeral-agents` uses.
- **Drafting happens in an isolated git worktree**, created fresh from `main`, outside the running checkout. The drafter is a bounded agent (budgets enforced by the harness) whose only tools are reading and writing files inside that worktree and running the tests there. It has no gateway tools, no memory, no network beyond its model.
- **A protected-path list, enforced in code.** The drafter cannot create, change, rename or delete anything under the safety layer: the confirmation gate, safety modes, adaptive auth, the classifier, the gateway's auth/tier/confirm/audit/registry code, token and `.env` files, hooks and this feature's own code. Every write is checked as it happens, and the finished diff is checked again; a patch touching a protected path is rejected whole.
- **Tests run only under an OS sandbox** (no network, writes limited to the worktree, scrubbed environment, timeout). Where no sandbox is available the run stops at "drafted, not tested" and says so; generated code is never run unconfined.
- **The result is a proposal on a branch**, `sutra/patch-<id>`: a summary, the file list, the test outcome, and the diff stat. Sutra never merges, pushes, deploys, or installs anything. Approval is a human act: the user reads the diff and merges it themselves, or discards it with `/patches discard`.
- **A `/patches` control** to list, show, and discard drafts, with budgets and a `SUTRA_PATCHES` switch, off by default.
- Out of scope, deliberately: editing the running checkout, auto-merge, auto-deploy, pushing to a remote, changing the protected paths at runtime, and drafting changes to other projects (twin, finanxe, minions).

## Capabilities

### New Capabilities
- `propose-a-patch`: draft a missing capability on an isolated branch under hard path and execution limits, and present it to the user as an untrusted proposal; never apply it.

### Modified Capabilities
(none; it reuses `ephemeral-agents` budgets and `voice-background-tasks` jobs without changing their requirements)

## Impact

- New package `orchestrator/src/sutra_orchestrator/patches/` and a local `patches.db` (private, gitignored), following the `agents` package layout.
- Git worktrees under a configurable directory outside the checkout; branches named `sutra/patch-<id>` in the local repository only.
- A sandbox runner for tests (`sandbox-exec` on macOS, `bwrap` on Linux/Pi); no new Python dependency.
- `Orchestrator` gains one local tool, `propose_capability`, which is a local run behind a yes, exactly like `delegate_research`.
- New settings: `SUTRA_PATCHES`, `SUTRA_PATCHES_DIR`, `SUTRA_PATCHES_MODEL`, per-run and daily budgets. Cost is real; defaults are small.
- No gateway, twin, finanxe or minions changes. Depends on `ephemeral-agents` (budgets, jobs), `assistant-memory`, and the safety layer from `activation-safe-mode`.
