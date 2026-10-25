package finanxe

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/siddharthshankar/sutra/gateway/internal/registry"
)

func newTestClient(t *testing.T, handler http.HandlerFunc) *Client {
	t.Helper()
	ts := httptest.NewServer(handler)
	t.Cleanup(ts.Close)
	return NewClient(Config{BaseURL: ts.URL, HTTPClient: ts.Client()})
}

func TestGetSnapshot_ReturnsData(t *testing.T) {
	client := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/snapshot" {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		if got := r.URL.Query().Get("user_id"); got != DefaultUserID {
			t.Fatalf("user_id = %q, want %q", got, DefaultUserID)
		}
		json.NewEncoder(w).Encode(Snapshot{CashPosition: 1234.5, NetAvailable: 200})
	})

	result, err := client.GetSnapshot(context.Background())
	if err != nil {
		t.Fatalf("GetSnapshot: %v", err)
	}
	if result.CashPosition != 1234.5 {
		t.Fatalf("CashPosition = %v, want 1234.5", result.CashPosition)
	}
}

func TestListDebts_ReturnsData(t *testing.T) {
	client := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/debts" {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		json.NewEncoder(w).Encode(DebtsResult{
			Debts:          []map[string]any{{"id": "d1", "name": "Card"}},
			AccountOptions: []map[string]any{{"id": "a1"}},
		})
	})

	result, err := client.ListDebts(context.Background())
	if err != nil {
		t.Fatalf("ListDebts: %v", err)
	}
	if len(result.Debts) != 1 || result.Debts[0]["name"] != "Card" {
		t.Fatalf("unexpected debts: %+v", result.Debts)
	}
}

func TestGetCalendar_ReturnsData(t *testing.T) {
	client := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/calendar" {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		json.NewEncoder(w).Encode(map[string]any{"events": []any{map[string]any{"title": "Rent due"}}})
	})

	result, err := client.GetCalendar(context.Background())
	if err != nil {
		t.Fatalf("GetCalendar: %v", err)
	}
	events, ok := result["events"].([]any)
	if !ok || len(events) != 1 {
		t.Fatalf("unexpected calendar result: %+v", result)
	}
}

func TestListGoals_ReturnsData(t *testing.T) {
	client := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/goals" {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		json.NewEncoder(w).Encode(GoalsResult{Goals: []map[string]any{{"id": "g1"}}})
	})

	result, err := client.ListGoals(context.Background())
	if err != nil {
		t.Fatalf("ListGoals: %v", err)
	}
	if len(result.Goals) != 1 {
		t.Fatalf("unexpected goals: %+v", result.Goals)
	}
}

func TestUsesConfiguredUserID(t *testing.T) {
	var gotUserID string
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotUserID = r.URL.Query().Get("user_id")
		json.NewEncoder(w).Encode(Snapshot{})
	}))
	t.Cleanup(ts.Close)
	client := NewClient(Config{BaseURL: ts.URL, UserID: "sid-real-user", HTTPClient: ts.Client()})

	if _, err := client.GetSnapshot(context.Background()); err != nil {
		t.Fatalf("GetSnapshot: %v", err)
	}
	if gotUserID != "sid-real-user" {
		t.Fatalf("user_id = %q, want %q", gotUserID, "sid-real-user")
	}
}

func TestFinanxeUnreachable_ReturnsToolError(t *testing.T) {
	// Point at a closed port instead of a live server to simulate finanxe
	// not running.
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {}))
	url := ts.URL
	ts.Close() // closed immediately: nothing is listening at this URL anymore

	client := NewClient(Config{BaseURL: url})
	if _, err := client.GetSnapshot(context.Background()); err == nil {
		t.Fatal("expected an error when finanxe is unreachable, got nil")
	}
	if _, err := client.ListDebts(context.Background()); err == nil {
		t.Fatal("expected an error when finanxe is unreachable, got nil")
	}
	if _, err := client.GetCalendar(context.Background()); err == nil {
		t.Fatal("expected an error when finanxe is unreachable, got nil")
	}
	if _, err := client.ListGoals(context.Background()); err == nil {
		t.Fatal("expected an error when finanxe is unreachable, got nil")
	}
}

func TestNonOKStatus_ReturnsToolError(t *testing.T) {
	client := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		w.Write([]byte("boom"))
	})
	if _, err := client.GetSnapshot(context.Background()); err == nil {
		t.Fatal("expected an error for a 5xx response, got nil")
	}
}

func TestRegister_AddsAllFourReadOnlyToolsWithNoSecretArgs(t *testing.T) {
	client := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]any{})
	})

	reg := registry.New()
	if err := Register(reg, client); err != nil {
		t.Fatalf("Register: %v", err)
	}

	names := []string{"finanxe_get_snapshot", "finanxe_list_debts", "finanxe_get_calendar", "finanxe_list_goals"}
	for _, name := range names {
		def, ok := reg.Lookup(name)
		if !ok {
			t.Fatalf("expected %q to be registered", name)
		}
		if def.Tier != registry.TierReadOnly {
			t.Fatalf("%q tier = %q, want %q", name, def.Tier, registry.TierReadOnly)
		}
		if len(def.SecretArgs) != 0 {
			t.Fatalf("%q SecretArgs = %v, want empty", name, def.SecretArgs)
		}
	}
}
