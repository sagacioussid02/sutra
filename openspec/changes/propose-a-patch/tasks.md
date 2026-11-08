## 1. Types, store and safety constants

- [x] 1.1 Define the run and draft types and the `patches.db` store (owner-only, versioned), following the `agents` package layout
- [x] 1.2 Define the protected-path list as a code constant and the matcher (globs, renames, deletions); add a test that it covers the safety, auth, confirmation, classifier and gateway-auth modules by name
- [x] 1.3 Tests: every protected path is refused; paths outside the worktree, `..` and symlink escapes are refused; ordinary paths are allowed

## 2. Worktree and file tools

- [x] 2.1 Create and remove worktrees and `sutra/patch-<id>` branches from `main` with git, never touching the running checkout
- [x] 2.2 Implement `read_file` and `write_file` confined to the worktree and checked against the protected list on every write
- [x] 2.3 Implement the end-of-run diff check (`git diff --name-status main`) rejecting the whole patch on any protected path, including renames and deletions
- [x] 2.4 Tests: a draft in a temporary git repository leaves the main checkout unchanged; a rename into a protected path rejects the patch

## 3. Sandboxed tests

- [x] 3.1 Implement `run_tests` through `sandbox-exec` (macOS) or `bwrap` (Linux) with no network, writes limited to the worktree, a scrubbed environment and a timeout
- [x] 3.2 When no sandbox exists, return "no sandbox available" and mark the draft untested; never fall back to an unconfined run
- [x] 3.3 Tests: the sandboxed process cannot reach the network or write outside the worktree; the environment holds no keys; a missing sandbox yields drafted-not-tested

## 4. The drafting run

- [x] 4.1 Reuse the `ephemeral-agents` budget machinery for tool calls, output tokens, wall-clock and the daily cap, with a drafting prompt that states the task and the limits
- [x] 4.2 Offer only `read_file`, `write_file` and `run_tests`; no shell, git, gateway, memory or network tool
- [x] 4.3 Record each run (task, status, spend, files, test outcome, branch) and mark a limit-ended run partial
- [x] 4.4 Tests: limits end the run as partial; the daily cap blocks a new run; a tool name the model invents is refused

## 5. Orchestrator and control

- [x] 5.1 Add the `propose_capability` local tool behind the user's yes, as a background job like `delegate_research`; announce the result with tools disabled
- [ ] 5.2 Add `/patches`: list, show, discard, discard all; add the `SUTRA_PATCHES*` settings (off by default) and document them in `orchestrator/.env.example`
- [x] 5.3 Tests: no worktree is created on a decline; injected text in a summary changes nothing; the tool is absent when the switch is off

## 6. Docs and verification

- [x] 6.1 README section: what a patch run can and cannot touch, how to review and merge a draft, and the sandbox requirement
- [ ] 6.2 Manual check with a real key on a throwaway repository: a small request becomes a reviewable branch, a protected-path attempt is refused, and the main checkout is untouched
