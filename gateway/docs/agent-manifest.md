# The Sutra Agent Manifest

A small, framework-agnostic way for any of your projects to describe its
own tools to sutra, so onboarding a new project doesn't require reading its
source by hand. This document is the spec, plus the runbook for actually
onboarding a project once it serves one.

Nothing described here ever makes sutra call your project automatically.
Fetching and parsing a manifest is read-only against the manifest endpoint
itself; every tool it describes still needs an explicit human approval
(via `sutra-discover`) before it can ever be registered as callable — see
[README.md](../README.md) and `openspec/changes/agent-discovery/design.md`
for the full reasoning.

## The convention

Serve a JSON document at:

```
GET /.well-known/sutra-agent.json
```

No auth is required to fetch it — it isn't a secret, and trust is
established by the human approval step, not by the manifest endpoint
itself. A static file is enough; a route that computes the list
dynamically from your actual handlers is better (it can't drift out of
sync with your real API).

## Shape (v1)

```json
{
  "sutra_manifest_version": 1,
  "project": {
    "name": "finanxe",
    "description": "Personal finance tracker: debts, goals, calendar."
  },
  "tools": [
    {
      "name": "list_debts",
      "description": "List the user's debts and funding accounts.",
      "tier_hint": "read-only",
      "method": "GET",
      "path": "/api/debts",
      "args": [
        {"name": "user_id", "type": "string", "required": false, "secret": false, "in": "query"}
      ],
      "generic_callable": true
    },
    {
      "name": "set_debt_funding",
      "description": "Redirect which account a debt is paid from, by debt name and account description.",
      "tier_hint": "confirm-first",
      "method": "POST",
      "path": "/api/debt/funding",
      "args": [
        {"name": "id", "type": "string", "required": true, "secret": false, "in": "body"},
        {"name": "funding_account", "type": "string", "required": true, "secret": false, "in": "body"}
      ],
      "generic_callable": false,
      "generic_callable_reason": "requires fuzzy name-resolution logic that can't be expressed as a plain HTTP call"
    }
  ]
}
```

### Top level

| Field | Meaning |
|---|---|
| `sutra_manifest_version` | Always `1` for this spec. |
| `project.name` | Short, stable identifier (e.g. `finanxe`). Used as the tool name prefix once registered (`finanxe_list_debts`). |
| `project.description` | One line, human-readable. |
| `tools` | Array of tool definitions, below. |

### Each tool

| Field | Meaning |
|---|---|
| `name` | Unique within this project (e.g. `list_debts`, not `finanxe_list_debts` — the prefix is added by sutra). |
| `description` | What it does, in plain language — this is what a human sees during approval, and what an MCP client sees once it's live. |
| `tier_hint` | One of `read-only` / `confirm-first` / `never-by-voice`. **A suggestion only.** The human approving this tool in sutra always types the real tier explicitly — this field is never trusted automatically, precisely because it's written by the project being discovered, not by the gateway's operator. |
| `method` | `GET` or `POST` (matching what your endpoint actually accepts). |
| `path` | A literal path, e.g. `/api/debts`. No `{param}` interpolation in v1 — put anything variable in the query string or JSON body instead. |
| `args` | Array of argument definitions, below. |
| `generic_callable` | `true` if this tool is a plain HTTP call sutra's generic adapter can make on its own once approved. `false` if it needs real logic (name resolution, multi-step orchestration, anything beyond "call this URL with these args") — sutra will still let a human discover, review, and approve/tier a `false` tool, but it stays uncallable until someone writes a small hand-written adapter for it (see `gateway/internal/twin/twin.go` or `gateway/internal/finanxe/finanxe.go` for the shape that takes). |
| `generic_callable_reason` | Required when `generic_callable` is `false` — a short note on why, shown to the approver. |

### Each arg

| Field | Meaning |
|---|---|
| `name` | The argument's key, exactly as your endpoint expects it. |
| `type` | `string`, `number`, or `boolean`. |
| `required` | Whether the call fails without it. |
| `secret` | `true` if this value should be redacted before it's written to sutra's audit log (e.g. a raw credential — though in practice, most projects should avoid ever needing this by keeping real secrets server-side, the way finanxe never surfaces Plaid tokens through the gateway at all). |
| `in` | `query` (GET query string) or `body` (JSON POST body). |

## Implementing this in your project

**FastAPI** (twin, or anything similar):

```python
@app.get("/.well-known/sutra-agent.json")
def sutra_manifest():
    return {
        "sutra_manifest_version": 1,
        "project": {"name": "twin", "description": "Persona chat platform."},
        "tools": [
            {
                "name": "chat",
                "description": "Chat with a twin persona by id.",
                "tier_hint": "read-only",
                "method": "POST",
                "path": "/chat",
                "args": [
                    {"name": "twin_id", "type": "string", "required": True, "secret": False, "in": "body"},
                    {"name": "message", "type": "string", "required": True, "secret": False, "in": "body"},
                ],
                "generic_callable": True,
            },
        ],
    }
```

**stdlib `http.server`** (finanxe, or anything similar) — one more branch
next to your existing routes:

```python
elif path == '/.well-known/sutra-agent.json':
    self._send_json(200, SUTRA_MANIFEST)  # a module-level dict, same shape as above
```

Anything that can serve a static JSON file works too — a manifest doesn't
have to be computed.

## Onboarding a project end to end

1. **On the project**: add the route or static file above.
2. **On the sutra side**, add the project to `gateway/discovery-sources.yaml`
   (copy `discovery-sources.example.yaml`):
   ```yaml
   sources:
     - name: my-project
       manifest_url: http://127.0.0.1:PORT/.well-known/sutra-agent.json
       base_url: http://127.0.0.1:PORT
   ```
3. Run discovery: `go run ./cmd/sutra-discover -sources discovery-sources.yaml`
4. Review each tool it shows you. Type the tier you actually want — don't
   just accept the hint. `reject` anything that shouldn't be reachable
   through the gateway at all; `skip` to decide later.
5. For anything marked `generic_callable: false`, write a small
   hand-written adapter (same shape as `internal/twin` or
   `internal/finanxe`) — approval alone doesn't make those callable.
6. Add the new tool names to the relevant user's `allowed_tools` in
   `tokens.yaml` — this is unchanged from today; `authcfg` still gates
   every call regardless of how a tool got registered.
7. Restart `cmd/gateway`. Its startup log line
   (`<source>: registered N discovered tools (M skipped)`) confirms
   what went live.

If a tool's manifest definition changes later (a renamed arg, a different
path, a different description), the gateway will stop registering it at
the next restart until you re-run `sutra-discover` and re-approve it — it
never silently keeps the old behavior or silently adopts the new one
unreviewed.

See `docs/examples/finanxe.sutra-agent.json` for a complete worked
example covering both a generic-callable tool and a bespoke one.
