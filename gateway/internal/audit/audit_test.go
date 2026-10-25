package audit

import (
	"context"
	"path/filepath"
	"testing"
)

func openTestStore(t *testing.T) *Store {
	t.Helper()
	dbPath := filepath.Join(t.TempDir(), "audit.db")
	s, err := Open(dbPath)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	t.Cleanup(func() { s.Close() })
	return s
}

func TestWriteAndFind(t *testing.T) {
	s := openTestStore(t)
	ctx := context.Background()

	if err := s.Write(ctx, Entry{
		UserID:        "alice",
		ToolName:      "finanxe_get_snapshot",
		Tier:          "read-only",
		Args:          map[string]any{"user_id": "alice"},
		Status:        StatusExecuted,
		ResultSummary: "ok",
	}); err != nil {
		t.Fatalf("Write: %v", err)
	}

	entries, err := s.Find(ctx, Query{UserID: "alice"})
	if err != nil {
		t.Fatalf("Find: %v", err)
	}
	if len(entries) != 1 {
		t.Fatalf("expected 1 entry, got %d", len(entries))
	}
	if entries[0].ToolName != "finanxe_get_snapshot" || entries[0].Status != StatusExecuted {
		t.Fatalf("unexpected entry: %+v", entries[0])
	}
}

func TestFindFiltersByToolAndStatus(t *testing.T) {
	s := openTestStore(t)
	ctx := context.Background()

	s.Write(ctx, Entry{UserID: "bob", ToolName: "twin_chat", Tier: "read-only", Status: StatusExecuted})
	s.Write(ctx, Entry{UserID: "bob", ToolName: "finanxe_set_debt_funding", Tier: "confirm-first", Status: StatusPending, PendingID: "p1"})
	s.Write(ctx, Entry{UserID: "bob", ToolName: "finanxe_set_debt_funding", Tier: "confirm-first", Status: StatusExecuted, PendingID: "p1"})

	pending, err := s.Find(ctx, Query{ToolName: "finanxe_set_debt_funding", Status: StatusPending})
	if err != nil {
		t.Fatalf("Find: %v", err)
	}
	if len(pending) != 1 || pending[0].PendingID != "p1" {
		t.Fatalf("expected 1 pending entry linked by pending id, got %+v", pending)
	}

	executed, err := s.Find(ctx, Query{ToolName: "finanxe_set_debt_funding", Status: StatusExecuted})
	if err != nil {
		t.Fatalf("Find: %v", err)
	}
	if len(executed) != 1 || executed[0].PendingID != "p1" {
		t.Fatalf("expected 1 executed entry linked by the same pending id, got %+v", executed)
	}
}

func TestEntriesSurviveReopen(t *testing.T) {
	dbPath := filepath.Join(t.TempDir(), "audit.db")
	s, err := Open(dbPath)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	ctx := context.Background()
	if err := s.Write(ctx, Entry{UserID: "carol", ToolName: "twin_chat", Tier: "read-only", Status: StatusExecuted}); err != nil {
		t.Fatalf("Write: %v", err)
	}
	if err := s.Close(); err != nil {
		t.Fatalf("Close: %v", err)
	}

	s2, err := Open(dbPath)
	if err != nil {
		t.Fatalf("reopen: %v", err)
	}
	defer s2.Close()
	entries, err := s2.Find(ctx, Query{UserID: "carol"})
	if err != nil {
		t.Fatalf("Find after reopen: %v", err)
	}
	if len(entries) != 1 {
		t.Fatalf("expected entry to survive reopen, got %d entries", len(entries))
	}
}

func TestRedactedArgsAreWhatGetsStored(t *testing.T) {
	// audit.Store trusts its caller to redact before calling Write — this
	// test documents that contract: whatever is in Args is what's stored,
	// verbatim, so callers (the gateway dispatch layer) must redact first.
	s := openTestStore(t)
	ctx := context.Background()
	s.Write(ctx, Entry{
		UserID:   "dave",
		ToolName: "finanxe_set_debt_funding",
		Tier:     "confirm-first",
		Args:     map[string]any{"account_text": "[REDACTED]"},
		Status:   StatusPending,
	})
	entries, _ := s.Find(ctx, Query{UserID: "dave"})
	if entries[0].Args["account_text"] != "[REDACTED]" {
		t.Fatalf("expected pre-redacted value to be stored as-is, got %v", entries[0].Args["account_text"])
	}
}
