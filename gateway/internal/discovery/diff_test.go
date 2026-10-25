package discovery

import (
	"context"
	"testing"

	"github.com/siddharthshankar/sutra/gateway/internal/manifest"
	"github.com/siddharthshankar/sutra/gateway/internal/registry"
)

func testManifest() *manifest.Manifest {
	return &manifest.Manifest{
		Version: 1,
		Project: manifest.Project{Name: "finanxe"},
		Tools: []manifest.Tool{
			{Name: "list_debts", Description: "List debts.", Method: "GET", Path: "/api/debts", GenericCallable: true},
		},
	}
}

func TestDiff_NewTool(t *testing.T) {
	s := newTestStore(t)
	reviews, err := Diff(context.Background(), s, testManifest())
	if err != nil {
		t.Fatalf("Diff: %v", err)
	}
	if len(reviews) != 1 || reviews[0].Kind != ChangeNew {
		t.Fatalf("expected a single ChangeNew review, got %+v", reviews)
	}
}

func TestDiff_UnchangedApprovedTool(t *testing.T) {
	s := newTestStore(t)
	ctx := context.Background()
	m := testManifest()
	hash := m.Tools[0].Hash()

	if err := s.Record(ctx, Approval{SourceName: "finanxe", ToolName: "list_debts", ManifestHash: hash, Status: StatusApproved, Tier: registry.TierReadOnly, DecidedBy: "sid"}); err != nil {
		t.Fatalf("Record: %v", err)
	}

	reviews, err := Diff(ctx, s, m)
	if err != nil {
		t.Fatalf("Diff: %v", err)
	}
	if len(reviews) != 1 || reviews[0].Kind != ChangeUnchanged {
		t.Fatalf("expected a single ChangeUnchanged review, got %+v", reviews)
	}
}

func TestDiff_ChangedDefinitionInvalidatesApproval(t *testing.T) {
	s := newTestStore(t)
	ctx := context.Background()

	if err := s.Record(ctx, Approval{SourceName: "finanxe", ToolName: "list_debts", ManifestHash: "stale-hash", Status: StatusApproved, Tier: registry.TierReadOnly, DecidedBy: "sid"}); err != nil {
		t.Fatalf("Record: %v", err)
	}

	reviews, err := Diff(ctx, s, testManifest())
	if err != nil {
		t.Fatalf("Diff: %v", err)
	}
	if len(reviews) != 1 || reviews[0].Kind != ChangeChanged {
		t.Fatalf("expected a single ChangeChanged review, got %+v", reviews)
	}
	if reviews[0].Prior == nil || reviews[0].Prior.ManifestHash != "stale-hash" {
		t.Fatalf("expected Prior to carry the stale approval, got %+v", reviews[0].Prior)
	}
}

func TestDiff_RejectedToolIsResurfaced(t *testing.T) {
	s := newTestStore(t)
	ctx := context.Background()
	m := testManifest()
	hash := m.Tools[0].Hash()

	if err := s.Record(ctx, Approval{SourceName: "finanxe", ToolName: "list_debts", ManifestHash: hash, Status: StatusRejected, DecidedBy: "sid"}); err != nil {
		t.Fatalf("Record: %v", err)
	}

	reviews, err := Diff(ctx, s, m)
	if err != nil {
		t.Fatalf("Diff: %v", err)
	}
	if len(reviews) != 1 || reviews[0].Kind != ChangeRejectedAgain {
		t.Fatalf("expected a single ChangeRejectedAgain review, got %+v", reviews)
	}
}
