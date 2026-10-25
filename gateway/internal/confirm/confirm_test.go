package confirm

import (
	"context"
	"errors"
	"path/filepath"
	"testing"
	"time"
)

func openTestStore(t *testing.T, ttl time.Duration) *Store {
	t.Helper()
	s, err := Open(filepath.Join(t.TempDir(), "confirm.db"), ttl)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	t.Cleanup(func() { s.Close() })
	return s
}

func TestCreateThenClaimSucceeds(t *testing.T) {
	s := openTestStore(t, time.Minute)
	ctx := context.Background()

	pending, err := s.Create(ctx, "alice", "finanxe_set_debt_funding", map[string]any{"debt_name": "visa"}, "Redirect funding for visa")
	if err != nil {
		t.Fatalf("Create: %v", err)
	}

	record, err := s.Claim(ctx, pending.ID, "alice")
	if err != nil {
		t.Fatalf("Claim: %v", err)
	}
	if record.ToolName != "finanxe_set_debt_funding" || record.Args["debt_name"] != "visa" {
		t.Fatalf("unexpected claimed record: %+v", record)
	}
}

func TestClaimByDifferentUserIsForbidden(t *testing.T) {
	s := openTestStore(t, time.Minute)
	ctx := context.Background()

	pending, _ := s.Create(ctx, "alice", "finanxe_create_goal", map[string]any{}, "desc")
	_, err := s.Claim(ctx, pending.ID, "mallory")
	if !errors.Is(err, ErrForbidden) {
		t.Fatalf("expected ErrForbidden, got %v", err)
	}
}

func TestClaimTwiceFailsSecondTime(t *testing.T) {
	s := openTestStore(t, time.Minute)
	ctx := context.Background()

	pending, _ := s.Create(ctx, "alice", "finanxe_add_calendar_event", map[string]any{}, "desc")
	if _, err := s.Claim(ctx, pending.ID, "alice"); err != nil {
		t.Fatalf("first Claim: %v", err)
	}
	_, err := s.Claim(ctx, pending.ID, "alice")
	if !errors.Is(err, ErrAlreadyUsed) {
		t.Fatalf("expected ErrAlreadyUsed on second claim, got %v", err)
	}
}

func TestClaimAfterExpiryFails(t *testing.T) {
	s := openTestStore(t, 10*time.Millisecond)
	ctx := context.Background()

	pending, _ := s.Create(ctx, "alice", "finanxe_set_debt_funding", map[string]any{}, "desc")
	time.Sleep(50 * time.Millisecond)

	_, err := s.Claim(ctx, pending.ID, "alice")
	if !errors.Is(err, ErrExpired) {
		t.Fatalf("expected ErrExpired, got %v", err)
	}
}

func TestClaimUnknownIDFails(t *testing.T) {
	s := openTestStore(t, time.Minute)
	_, err := s.Claim(context.Background(), "does-not-exist", "alice")
	if !errors.Is(err, ErrNotFound) {
		t.Fatalf("expected ErrNotFound, got %v", err)
	}
}

func TestConcurrentClaimsOnlyOneSucceeds(t *testing.T) {
	s := openTestStore(t, time.Minute)
	ctx := context.Background()
	pending, _ := s.Create(ctx, "alice", "finanxe_set_debt_funding", map[string]any{}, "desc")

	const n = 10
	results := make(chan error, n)
	for i := 0; i < n; i++ {
		go func() {
			_, err := s.Claim(ctx, pending.ID, "alice")
			results <- err
		}()
	}

	successes := 0
	for i := 0; i < n; i++ {
		if err := <-results; err == nil {
			successes++
		} else if !errors.Is(err, ErrAlreadyUsed) {
			t.Fatalf("unexpected error from concurrent claim: %v", err)
		}
	}
	if successes != 1 {
		t.Fatalf("expected exactly 1 successful claim under race, got %d", successes)
	}
}
