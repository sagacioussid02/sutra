## Context

`ephemeral-agents` already gives Sutra a bounded worker with an allowlist of tools, harness-enforced budgets, and results that come back as untrusted findings. This change reuses that shape for a different product: instead of a research answer, a code proposal.

The risk is different in kind. A research run can at worst return misleading text. A code-drafting run produces something that, once merged, runs with the user's authority, and running its tests already executes it. Two lines have to hold: nothing Sutra writes reaches the running system without a human reading it, and nothing it writes can weaken the checks that keep it in bounds.

## Goals / Non-Goals

**Goals:**
- Let Sutra extend itself without extending its own trust: draft, test, propose; a human decides.
- A drafter that physically cannot touch the safety layer, even if told to by injected content.
- Generated code never runs unconfined, including its tests.
- A proposal the user can read in a minute: summary, files, test outcome, diff.

**Non-Goals:**
- Auto-merge, auto-deploy, pushing to a remote, or editing the running checkout.
- Drafting for other projects, or changing dependencies automatically.
- A guarantee that a draft is correct or safe. Review is the control; the tests are evidence, not proof.

## Decisions

### A worktree off `main`, never the running checkout
Each run creates `git worktree add <dir>/<id> -b sutra/patch-<id> main`. The running process keeps importing from its own checkout; nothing the drafter writes can be imported by it. Discarding a draft removes the worktree and the branch.

*Alternative considered:* a copy of the tree in a temp directory. Rejected: a worktree gives the user ordinary git review (`git diff main...sutra/patch-<id>`) and a merge they already understand.

### The drafter has three tools, all path-confined
`read_file`, `write_file` and `run_tests`, each taking worktree-relative paths. Paths are resolved and must stay inside the worktree (no `..`, no symlinks out), and a write must also clear the protected-path list. There is no shell tool, no git tool, no gateway access and no network tool.

### The protected-path list is code, and checked twice
The list is a constant in the patches package (not configuration, not editable at runtime) covering: the safety, auth and confirmation modules and the classifier; the orchestrator's tool-gate code; the gateway's auth, tier, confirm, audit and registry packages and token files; every `.env*`; hooks and `.claude/`; and the patches package itself. A write to a protected path is refused immediately, and when the run ends the full `git diff --name-status main` is checked against the list again, including renames and deletions. A patch that fails either check is rejected whole, not trimmed.

*Why twice:* the first check keeps the drafter honest in the moment; the second catches anything the per-write check missed (a rename, a mode change, a generated file).

### Tests run under an OS sandbox or not at all
`run_tests` executes the project's test command through `sandbox-exec` (macOS) or `bwrap` (Linux), with no network, writes limited to the worktree, a scrubbed environment (no keys, no `.env`), and a timeout. If neither is present, `run_tests` reports "no sandbox available" and the proposal is marked drafted-not-tested. It does not fall back to running unconfined.

*Why:* running a test suite is running arbitrary code as the user. A sandbox is the only thing that makes "tests passed" safe to produce.

### Results are untrusted proposals through the ask-first path
The finished run reports a summary the drafter wrote, which is treated as untrusted text exactly like research findings: the spoken announcement is composed in a step with tools disabled. The announcement says that a draft exists and what it claims to do, and offers to read the summary. Nothing in it is applied. `/patches show <id>` prints the file list, test outcome and diff stat; the user opens the diff in their own tools.

### Budgets and a switch
Reuse the `ephemeral-agents` budget machinery: tool calls, output tokens, wall-clock, and a daily cap on runs. `SUTRA_PATCHES` is off by default. With it off the `propose_capability` tool is not offered and `/patches` reports that it is off.

## Risks / Trade-offs

- [A draft smuggles a change into protected code] → per-write check plus whole-diff check; rejected whole on any hit; the list is a code constant with a test that it covers the safety modules.
- [Injected text in the request or a file steers the drafter] → the drafter's reach is the worktree and a sandbox; it cannot approve, merge, push, or reach the gateway; the user reads before anything runs in Sutra.
- [Tests run hostile code] → OS sandbox with no network and a scrubbed environment; no sandbox means no test run.
- [The user merges without reading] → the proposal says in plain words what it changed, the diff stat is shown, and Sutra never merges for them. This is the residual risk; it is the user's decision by design.
- [Cost] → small default budgets and a daily cap; every run records its spend.
- [Worktrees pile up] → drafts are listed and discardable, and old undiscarded ones are reported by `/patches`.

## Migration Plan

Off by default and additive. Enabling it needs `SUTRA_PATCHES=on`, a git checkout, and, for tests, `sandbox-exec` or `bwrap`. Rolling back is turning the switch off and removing leftover worktrees and `sutra/patch-*` branches, which `/patches discard all` does.

## Open Questions

- Should the drafter be allowed to add new Python dependencies to `pyproject.toml`? This change says no (a dependency change is flagged as protected). Revisit if useful drafts keep needing one.
- Should a proposal be openable as a pull request when `gh` is authenticated? Out of scope here; a merge the user does by hand is the control.
