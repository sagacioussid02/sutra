package genericadapter

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/siddharthshankar/sutra/gateway/internal/manifest"
	"github.com/siddharthshankar/sutra/gateway/internal/registry"
)

func newTestClient(t *testing.T, handler http.HandlerFunc) *Client {
	t.Helper()
	ts := httptest.NewServer(handler)
	t.Cleanup(ts.Close)
	return NewClient(Config{BaseURL: ts.URL, HTTPClient: ts.Client()})
}

func getTool() manifest.Tool {
	return manifest.Tool{
		Name: "list_debts", Description: "List debts.", Method: http.MethodGet, Path: "/api/debts",
		Args:            []manifest.Arg{{Name: "user_id", Type: manifest.ArgString, In: manifest.ArgQuery}},
		GenericCallable: true,
	}
}

func postTool() manifest.Tool {
	return manifest.Tool{
		Name: "add_event", Description: "Add a calendar event.", Method: http.MethodPost, Path: "/api/calendar/event",
		Args: []manifest.Arg{
			{Name: "title", Type: manifest.ArgString, Required: true, In: manifest.ArgBody},
			{Name: "date", Type: manifest.ArgString, Required: true, In: manifest.ArgBody},
		},
		GenericCallable: true,
	}
}

func TestCall_GET_RoutesArgsToQueryString(t *testing.T) {
	var gotQuery string
	client := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/debts" || r.Method != http.MethodGet {
			t.Fatalf("unexpected request: %s %s", r.Method, r.URL.Path)
		}
		gotQuery = r.URL.Query().Get("user_id")
		json.NewEncoder(w).Encode(map[string]any{"debts": []any{}})
	})

	body, err := client.call(context.Background(), getTool(), map[string]any{"user_id": "sid"})
	if err != nil {
		t.Fatalf("call: %v", err)
	}
	if gotQuery != "sid" {
		t.Fatalf("expected user_id=sid in query string, got %q", gotQuery)
	}
	if len(body) == 0 {
		t.Fatal("expected a non-empty response body")
	}
}

func TestCall_POST_RoutesArgsToJSONBody(t *testing.T) {
	var gotBody map[string]any
	client := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/calendar/event" || r.Method != http.MethodPost {
			t.Fatalf("unexpected request: %s %s", r.Method, r.URL.Path)
		}
		json.NewDecoder(r.Body).Decode(&gotBody)
		json.NewEncoder(w).Encode(map[string]any{"status": "created"})
	})

	_, err := client.call(context.Background(), postTool(), map[string]any{"title": "Rent", "date": "2027-01-01"})
	if err != nil {
		t.Fatalf("call: %v", err)
	}
	if gotBody["title"] != "Rent" || gotBody["date"] != "2027-01-01" {
		t.Fatalf("unexpected request body: %v", gotBody)
	}
}

func TestCall_MissingRequiredArg_ReturnsError(t *testing.T) {
	client := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		t.Fatal("handler should not be called when a required arg is missing")
	})

	_, err := client.call(context.Background(), postTool(), map[string]any{"title": "Rent"})
	if err == nil {
		t.Fatal("expected an error for a missing required argument")
	}
}

func TestCall_WrongArgType_ReturnsError(t *testing.T) {
	client := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		t.Fatal("handler should not be called when an arg has the wrong type")
	})

	_, err := client.call(context.Background(), postTool(), map[string]any{"title": 12345, "date": "2027-01-01"})
	if err == nil {
		t.Fatal("expected an error for a wrongly-typed argument")
	}
}

func TestCall_NonOKStatus_ReturnsError(t *testing.T) {
	client := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		w.Write([]byte("boom"))
	})
	if _, err := client.call(context.Background(), getTool(), nil); err == nil {
		t.Fatal("expected an error for a 5xx response")
	}
}

func TestCall_Unreachable_ReturnsError(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {}))
	url := ts.URL
	ts.Close()
	client := NewClient(Config{BaseURL: url})

	if _, err := client.call(context.Background(), getTool(), nil); err == nil {
		t.Fatal("expected an error when the backend is unreachable")
	}
}

func TestBuildDefinition_ReadOnly_NoDescribeFunc(t *testing.T) {
	client := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]any{"ok": true})
	})

	def, err := BuildDefinition(client, "finanxe", getTool(), registry.TierReadOnly)
	if err != nil {
		t.Fatalf("BuildDefinition: %v", err)
	}
	if def.Name != "finanxe_list_debts" {
		t.Fatalf("Name = %q, want finanxe_list_debts", def.Name)
	}
	if def.Describe != nil {
		t.Fatal("expected no Describe func for a read-only tool")
	}
}

func TestBuildDefinition_ConfirmFirst_HasDescribeFunc(t *testing.T) {
	client := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {})
	def, err := BuildDefinition(client, "finanxe", postTool(), registry.TierConfirmFirst)
	if err != nil {
		t.Fatalf("BuildDefinition: %v", err)
	}
	if def.Describe == nil {
		t.Fatal("expected a Describe func for a confirm-first tool")
	}
	desc := def.Describe(map[string]any{"title": "Rent", "date": "2027-01-01"})
	if desc == "" {
		t.Fatal("expected a non-empty description")
	}
}

func TestBuildDefinition_SecretArgsPassedThrough(t *testing.T) {
	tool := manifest.Tool{
		Name: "with_secret", Description: "d", Method: http.MethodPost, Path: "/x",
		Args:            []manifest.Arg{{Name: "api_key", Type: manifest.ArgString, Secret: true, In: manifest.ArgBody}},
		GenericCallable: true,
	}
	client := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {})
	def, err := BuildDefinition(client, "src", tool, registry.TierReadOnly)
	if err != nil {
		t.Fatalf("BuildDefinition: %v", err)
	}
	if len(def.SecretArgs) != 1 || def.SecretArgs[0] != "api_key" {
		t.Fatalf("SecretArgs = %v, want [api_key]", def.SecretArgs)
	}
}

func TestBuildDefinition_InvalidTier_ReturnsError(t *testing.T) {
	client := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {})
	if _, err := BuildDefinition(client, "finanxe", getTool(), registry.Tier("bogus")); err == nil {
		t.Fatal("expected an error for an invalid tier")
	}
}

func TestHandler_ExecutesCallAndReturnsResult(t *testing.T) {
	client := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]any{"debts": []any{map[string]any{"id": "d1"}}})
	})
	def, err := BuildDefinition(client, "finanxe", getTool(), registry.TierReadOnly)
	if err != nil {
		t.Fatalf("BuildDefinition: %v", err)
	}

	result, err := def.Handler(context.Background(), "sid", map[string]any{"user_id": "sid"})
	if err != nil {
		t.Fatalf("Handler: %v", err)
	}
	m, ok := result.(map[string]any)
	if !ok {
		t.Fatalf("unexpected result type: %T", result)
	}
	if _, ok := m["debts"]; !ok {
		t.Fatalf("expected a debts field in the result: %v", m)
	}
}
