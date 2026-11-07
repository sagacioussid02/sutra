## 1. Resolution

- [ ] 1.1 Define the token→user mapping configuration (format, location outside the repo, owner-only permissions) and an example file with placeholder tokens only
- [ ] 1.2 Implement resolution in the gateway auth path: token → user id into request context; log the mapping (user ids only) at startup
- [ ] 1.3 Tests: mapped token resolves to its user; unmapped token resolves to no user; mapping file with duplicate tokens fails startup with a clear error

## 2. Finanxe adapter

- [ ] 2.1 Change finanxe adapter call sites to take the user id from request context; remove identity defaults from the adapter
- [ ] 2.2 Keep `--finanxe-user-id` only as a configured fallback for one designated legacy token, audit-logged as fallback on every use; identity error (not fallback) for any other unmapped caller
- [ ] 2.3 Tests: two callers with different mappings reach finanxe under two different user ids; an unmapped caller gets an identity error and finanxe is never called; fallback fires only for the designated token and is audited

## 3. Twin audit

- [ ] 3.1 Inspect the twin adapter for a shared-identity collapse; apply the same mapping if it has a per-user upstream identity
- [ ] 3.2 If twin tools are caller-independent, record the exemption explicitly in the tool registry with a reason

## 4. Audit and drift

- [ ] 4.1 Add the effective user id and fallback flag to every audit entry
- [ ] 4.2 Add a startup warning when a token's gateway user and its orchestrator memory-database user visibly disagree
- [ ] 4.3 Tests: a confirm-first finanxe call's audit entry shows the effective user; the drift warning fires on a deliberately mismatched test configuration

## 5. Migration and docs

- [ ] 5.1 Ship the initial mapping with exactly one entry (owner token → `demo_user`) and verify the owner's existing flows are unchanged
- [ ] 5.2 README section: how identity resolution works, how to add a person, the fallback and its removal, and the fail-closed rule
- [ ] 5.3 Document any new configuration in `orchestrator/.env.example` / gateway docs per the repo's completeness guard
- [ ] 5.4 After one full usage cycle with no fallback audit entries, remove the `--finanxe-user-id` flag and the fallback path (separate small step, listed here so it is not forgotten)
