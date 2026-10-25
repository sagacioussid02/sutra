package discovery

import (
	"context"
	"path/filepath"
	"testing"

	"github.com/siddharthshankar/sutra/gateway/internal/registry"
)

func newTestStore(t *testing.T) *Store {
	t.Helper()
	s, err := Open(filepath.Join(t.TempDir(), "discovery.db"))
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	t.Cleanup(func() { s.Close() })
	return s
}

func TestRecordAndGet(t *testing.T) {
	s := newTestStore(t)
	ctx := context.Background()

	err := s.Record(ctx, Approval{
		SourceName: "finanxe", ToolName: "list_debts", ManifestHash: "h1",
		Status: StatusApproved, Tier: registry.TierReadOnly, DecidedBy: "sid",
	})
	if err != nil {
		t.Fatalf("Record: %v", err)
	}

	got, found, err := s.Get(ctx, "finanxe", "list_debts")
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	if !found {
		t.Fatal("expected a record to be found")
	}
	if got.Status != StatusApproved || got.Tier != registry.TierReadOnly || got.ManifestHash != "h1" {
		t.Fatalf("unexpected approval: %+v", got)
	}
}

func TestGet_NotFound(t *testing.T) {
	s := newTestStore(t)
	_, found, err := s.Get(context.Background(), "finanxe", "nonexistent")
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	if found {
		t.Fatal("expected no record to be found")
	}
}

func TestRecord_OverwritesPriorDecision(t *testing.T) {
	s := newTestStore(t)
	ctx := context.Background()

	if err := s.Record(ctx, Approval{SourceName: "finanxe", ToolName: "x", ManifestHash: "h1", Status: StatusRejected, DecidedBy: "sid"}); err != nil {
		t.Fatalf("Record (1): %v", err)
	}
	if err := s.Record(ctx, Approval{SourceName: "finanxe", ToolName: "x", ManifestHash: "h1", Status: StatusApproved, Tier: registry.TierConfirmFirst, DecidedBy: "sid"}); err != nil {
		t.Fatalf("Record (2): %v", err)
	}

	got, found, err := s.Get(ctx, "finanxe", "x")
	if err != nil || !found {
		t.Fatalf("Get: found=%v err=%v", found, err)
	}
	if got.Status != StatusApproved || got.Tier != registry.TierConfirmFirst {
		t.Fatalf("expected the later decision to win, got %+v", got)
	}
}

func TestApproved_OnlyReturnsApprovedRecords(t *testing.T) {
	s := newTestStore(t)
	ctx := context.Background()

	s.Record(ctx, Approval{SourceName: "finanxe", ToolName: "a", ManifestHash: "h1", Status: StatusApproved, Tier: registry.TierReadOnly, DecidedBy: "sid"})
	s.Record(ctx, Approval{SourceName: "finanxe", ToolName: "b", ManifestHash: "h1", Status: StatusRejected, DecidedBy: "sid"})
	s.Record(ctx, Approval{SourceName: "trading", ToolName: "c", ManifestHash: "h1", Status: StatusApproved, Tier: registry.TierConfirmFirst, DecidedBy: "sid"})

	approved, err := s.Approved(ctx)
	if err != nil {
		t.Fatalf("Approved: %v", err)
	}
	if len(approved) != 2 {
		t.Fatalf("expected 2 approved records, got %d: %+v", len(approved), approved)
	}
	for _, a := range approved {
		if a.Status != StatusApproved {
			t.Fatalf("Approved returned a non-approved record: %+v", a)
		}
	}
}
