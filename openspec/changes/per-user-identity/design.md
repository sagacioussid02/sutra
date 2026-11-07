## Context

The gateway authenticates callers with per-user bearer tokens, and the
audit log records caller identity on every call (`gateway-core`). But
identity stops at the gateway door: the finanxe adapter substitutes one
configured user id — `--finanxe-user-id`, default `demo_user` — for
every caller, because finanxe's own demo data was seeded under that id
and it is where the owner's real data lives (see the comment at
`gateway/cmd/gateway/main.go:47`).

Project constraints shape the fix: the audience is the user plus a few
trusted people, auth stays simple bearer tokens, and existing projects
(finanxe, twin) are not modified to fit the gateway — adapters call them
as they are. Finanxe already accepts a user id per call; it is the
gateway that throws the caller's away.

## Goals / Non-Goals

**Goals:**
- A caller's data is the caller's: reads and confirm-first writes reach
  finanxe under the user id that caller maps to.
- Fail closed. No mapping, no data — never another user's.
- The effective user is visible in the audit log for every call.
- Migration that moves no data and breaks no existing setup.

**Non-Goals:**
- Making finanxe or twin multi-user. If finanxe cannot serve a second
  user's data, that user simply has no finanxe mapping yet; the gateway
  mapping is ready for when it can.
- Replacing bearer tokens with a fuller auth system.
- A user-management interface. The mapping is an operator-edited file.
- Unifying the gateway mapping with the orchestrator's per-token memory
  databases in code. They are two views of the same operator decision;
  this change adds a startup warning when they disagree for a token it
  can see, and documents the rest.

## Decisions

### Mapping lives in gateway configuration, resolved per request
A small configuration file (or config section) lists token → user id.
Resolution happens in the same middleware that authenticates, and the
resolved id is carried in the request context to adapters. The file is
loaded at startup; changes need a restart, which is acceptable at this
scale and keeps resolution off the hot path of a database.

*Why not finanxe's own user concept:* finanxe has no real multi-user
support today (the flag's help text says so). Waiting for it would leave
the collapse in place; the mapping lets the gateway be correct first.

### `demo_user` becomes one user's explicit mapping
The owner's token maps to `demo_user` in the shipped example
configuration, because that is where the owner's data is. Nothing about
the data changes; what changes is that reaching it now requires being
the caller mapped to it. The old flag is removed once the mapping is
proven; during transition it serves only as the fallback below.

### Fallback is explicit, singular, and loud
If the operator configures a fallback user for legacy clients, it applies
to at most one designated legacy token, and every use writes an audit
entry marked as fallback. There is no fallback for an unknown token:
unknown or unmapped tokens authenticate (if the token itself is valid
for non-data tools) but any adapter call needing a user id fails with an
identity error.

*Alternative considered:* keep `demo_user` as the default for any
unmapped caller, for convenience. Rejected outright: that is the bug
being fixed, kept.

### Adapters receive identity; they do not decide it
The finanxe adapter's methods take the user id from request context. No
adapter reads configuration for identity, and no adapter may substitute
a default. The twin adapter is audited for the same pattern as part of
this change; if twin has no per-user upstream identity, its tools are
documented as caller-independent (they are read-only persona tools) and
explicitly exempted in the registry, rather than silently shared.

### Audit gains `effective_user`
Every audit entry records token identity (existing), the resolved user
id, and whether the fallback fired. A weekly eyeball of fallback entries
is the migration's done-condition: when they stop, the flag goes.

## Risks / Trade-offs

- [Misconfigured mapping points a caller at the wrong user's data] →
  the example configuration maps only the owner's token; startup logs
  the full mapping (user ids, never tokens) so the operator sees it;
  tests cover two callers reaching two different finanxe ids.
- [A legitimate caller breaks when the flag is removed] → the fallback
  path and its audit trail exist precisely to find these before removal.
- [Gateway and orchestrator mappings drift apart] → startup warning when
  a token's memory database user and gateway user visibly disagree, and
  the README instructs one mapping decision recorded in one place.
- [Mapping file leaks tokens] → the file is treated as a secret: outside
  the repo, owner-only permissions, and the committed example contains
  placeholders only — guarded by the same example-completeness test
  discipline as `.env.example`.

## Migration Plan

1. Ship resolution with the mapping file containing exactly one entry:
   the owner's token → `demo_user`. Behaviour for the owner is unchanged.
2. Run with the legacy fallback enabled; watch fallback audit entries
   for one full usage cycle.
3. Remove the `--finanxe-user-id` flag and the fallback; unmapped
   callers fail closed from then on.

Rollback is restoring the previous gateway binary/config; no data moves
at any step.

## Open Questions

- When a second person is actually onboarded, does finanxe gain real
  per-user data, or does that person simply not get finanxe tools? The
  gateway side works either way; the product answer is the owner's.
- Should token→user resolution be shared with the orchestrator as one
  file both read? Leaning yes eventually; this change keeps them
  separate with a drift warning, to avoid coupling the two processes'
  configuration before it is needed.
