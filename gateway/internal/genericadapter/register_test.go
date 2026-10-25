package genericadapter

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/siddharthshankar/sutra/gateway/internal/discovery"
	"github.com/siddharthshankar/sutra/gateway/internal/manifest"
	"github.com/siddharthshankar/sutra/gateway/internal/registry"
)

func TestRegisterApproved_RegistersApprovedGenericTool(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {}))
	defer ts.Close()
	client := NewClient(Config{BaseURL: ts.URL, HTTPClient: ts.Client()})

	tool := getTool()
	reg := registry.New()
	approvals := []discovery.Approval{
		{SourceName: "finanxe", ToolName: tool.Name, ManifestHash: tool.Hash(), Status: discovery.StatusApproved, Tier: registry.TierReadOnly},
	}

	registered, skipped := RegisterApproved(reg, "finanxe", client, []manifest.Tool{tool}, approvals)
	if registered != 1 || skipped != 0 {
		t.Fatalf("registered=%d skipped=%d, want 1/0", registered, skipped)
	}
	if _, ok := reg.Lookup("finanxe_list_debts"); !ok {
		t.Fatal("expected finanxe_list_debts to be registered")
	}
}

func TestRegisterApproved_SkipsUnapprovedTool(t *testing.T) {
	client := NewClient(Config{BaseURL: "http://127.0.0.1:0"})
	reg := registry.New()

	registered, skipped := RegisterApproved(reg, "finanxe", client, []manifest.Tool{getTool()}, nil)
	if registered != 0 {
		t.Fatalf("expected 0 registered for an unapproved tool, got %d", registered)
	}
	_ = skipped // an unapproved tool is neither registered nor counted as skipped — it was simply never reviewed
	if _, ok := reg.Lookup("finanxe_list_debts"); ok {
		t.Fatal("expected finanxe_list_debts not to be registered")
	}
}

func TestRegisterApproved_SkipsNonGenericCallableTool(t *testing.T) {
	client := NewClient(Config{BaseURL: "http://127.0.0.1:0"})
	reg := registry.New()

	tool := manifest.Tool{Name: "set_debt_funding", Description: "d", Method: http.MethodPost, Path: "/api/debt/funding", GenericCallable: false}
	approvals := []discovery.Approval{
		{SourceName: "finanxe", ToolName: tool.Name, ManifestHash: tool.Hash(), Status: discovery.StatusApproved, Tier: registry.TierConfirmFirst},
	}

	registered, skipped := RegisterApproved(reg, "finanxe", client, []manifest.Tool{tool}, approvals)
	if registered != 0 || skipped != 1 {
		t.Fatalf("registered=%d skipped=%d, want 0/1", registered, skipped)
	}
	if _, ok := reg.Lookup("finanxe_set_debt_funding"); ok {
		t.Fatal("expected a non-generic-callable tool not to be registered even when approved")
	}
}

func TestRegisterApproved_SkipsStaleApproval(t *testing.T) {
	client := NewClient(Config{BaseURL: "http://127.0.0.1:0"})
	reg := registry.New()

	tool := getTool()
	approvals := []discovery.Approval{
		{SourceName: "finanxe", ToolName: tool.Name, ManifestHash: "stale-hash-from-before-a-change", Status: discovery.StatusApproved, Tier: registry.TierReadOnly},
	}

	registered, skipped := RegisterApproved(reg, "finanxe", client, []manifest.Tool{tool}, approvals)
	if registered != 0 || skipped != 1 {
		t.Fatalf("registered=%d skipped=%d, want 0/1", registered, skipped)
	}
}

func TestRegisterApproved_NameCollisionIsNonFatal(t *testing.T) {
	client := NewClient(Config{BaseURL: "http://127.0.0.1:0"})
	reg := registry.New()
	// Simulate a hand-written adapter already having registered this name.
	reg.MustRegister(&registry.Definition{
		Name: "finanxe_list_debts", Tier: registry.TierReadOnly,
		Handler: func(ctx context.Context, userID string, args map[string]any) (any, error) { return nil, nil },
	})

	tool := getTool()
	approvals := []discovery.Approval{
		{SourceName: "finanxe", ToolName: tool.Name, ManifestHash: tool.Hash(), Status: discovery.StatusApproved, Tier: registry.TierReadOnly},
	}

	registered, skipped := RegisterApproved(reg, "finanxe", client, []manifest.Tool{tool}, approvals)
	if registered != 0 || skipped != 1 {
		t.Fatalf("registered=%d skipped=%d, want 0/1 (name collision should be skipped, not fatal)", registered, skipped)
	}
}

func TestRegisterApproved_IgnoresApprovalsFromOtherSources(t *testing.T) {
	client := NewClient(Config{BaseURL: "http://127.0.0.1:0"})
	reg := registry.New()

	tool := getTool()
	approvals := []discovery.Approval{
		{SourceName: "trading", ToolName: tool.Name, ManifestHash: tool.Hash(), Status: discovery.StatusApproved, Tier: registry.TierReadOnly},
	}

	registered, _ := RegisterApproved(reg, "finanxe", client, []manifest.Tool{tool}, approvals)
	if registered != 0 {
		t.Fatalf("expected an approval for a different source not to apply, registered=%d", registered)
	}
}
