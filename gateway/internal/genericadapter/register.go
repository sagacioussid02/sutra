package genericadapter

import (
	"github.com/siddharthshankar/sutra/gateway/internal/discovery"
	"github.com/siddharthshankar/sutra/gateway/internal/manifest"
	"github.com/siddharthshankar/sutra/gateway/internal/registry"
)

// RegisterApproved registers a working tool for every entry in tools that
// is both currently approved (found in approvals, for sourceName, with a
// manifest hash matching tool.Hash() — a stale approval from before the
// tool's definition changed is treated as not currently approved) and
// generically callable. Everything else is counted as skipped, never an
// error: a tool that was never approved is simply not registered; a tool
// approved but not generic_callable still needs a hand-written adapter; a
// registration failure (most commonly a name collision with an
// already-registered hand-written tool) is logged-worthy but must never
// abort gateway startup or the rest of this batch.
func RegisterApproved(reg *registry.Registry, sourceName string, client *Client, tools []manifest.Tool, approvals []discovery.Approval) (registered, skipped int) {
	approvedByTool := make(map[string]discovery.Approval, len(approvals))
	for _, a := range approvals {
		if a.SourceName != sourceName || a.Status != discovery.StatusApproved {
			continue
		}
		approvedByTool[a.ToolName] = a
	}

	for _, tool := range tools {
		approval, ok := approvedByTool[tool.Name]
		if !ok {
			continue
		}
		if !tool.GenericCallable {
			skipped++
			continue
		}
		if approval.ManifestHash != tool.Hash() {
			skipped++
			continue
		}

		def, err := BuildDefinition(client, sourceName, tool, approval.Tier)
		if err != nil {
			skipped++
			continue
		}
		if err := reg.Register(def); err != nil {
			skipped++
			continue
		}
		registered++
	}
	return registered, skipped
}
