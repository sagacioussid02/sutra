package twin

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/siddharthshankar/sutra/gateway/internal/registry"
)

func newTestClient(t *testing.T, handler http.HandlerFunc) (*Client, *httptest.Server) {
	t.Helper()
	ts := httptest.NewServer(handler)
	t.Cleanup(ts.Close)
	return NewClient(Config{BaseURL: ts.URL, HTTPClient: ts.Client()}), ts
}

func TestChat_ReturnsReply(t *testing.T) {
	client, _ := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/chat" || r.Method != http.MethodPost {
			t.Fatalf("unexpected request: %s %s", r.Method, r.URL.Path)
		}
		var req chatRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			t.Fatalf("decoding request: %v", err)
		}
		if req.SessionID == "" {
			t.Fatalf("expected a derived session_id, got empty")
		}
		json.NewEncoder(w).Encode(ChatResult{Response: "hello back", SessionID: req.SessionID})
	})

	result, err := client.Chat(context.Background(), "alice", "twin-1", "hi")
	if err != nil {
		t.Fatalf("Chat: %v", err)
	}
	if result.Response != "hello back" {
		t.Fatalf("Response = %q, want %q", result.Response, "hello back")
	}
}

func TestChat_SameUserSameTwin_ReusesSessionID(t *testing.T) {
	var seen []string
	client, _ := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		var req chatRequest
		json.NewDecoder(r.Body).Decode(&req)
		seen = append(seen, req.SessionID)
		json.NewEncoder(w).Encode(ChatResult{Response: "ok", SessionID: req.SessionID})
	})

	if _, err := client.Chat(context.Background(), "alice", "twin-1", "first"); err != nil {
		t.Fatalf("Chat (1): %v", err)
	}
	if _, err := client.Chat(context.Background(), "alice", "twin-1", "second"); err != nil {
		t.Fatalf("Chat (2): %v", err)
	}

	if len(seen) != 2 || seen[0] != seen[1] {
		t.Fatalf("expected the same session_id across calls, got %v", seen)
	}

	// A different twin id for the same user must derive a different session.
	if _, err := client.Chat(context.Background(), "alice", "twin-2", "third"); err != nil {
		t.Fatalf("Chat (3): %v", err)
	}
	if seen[2] == seen[0] {
		t.Fatalf("expected a different session_id for a different twin id")
	}
}

func TestChat_UnknownTwinID_ReturnsToolError(t *testing.T) {
	client, _ := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
		json.NewEncoder(w).Encode(map[string]string{"detail": "Twin 'nope' not found"})
	})

	_, err := client.Chat(context.Background(), "alice", "nope", "hi")
	if err == nil {
		t.Fatal("expected an error for an unknown twin id, got nil")
	}
}

func TestChat_ServerError_ReturnsToolError(t *testing.T) {
	client, _ := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		w.Write([]byte("boom"))
	})

	_, err := client.Chat(context.Background(), "alice", "twin-1", "hi")
	if err == nil {
		t.Fatal("expected an error for a 5xx response, got nil")
	}
}

func TestListPublicPersonas_ReturnsList(t *testing.T) {
	client, _ := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/public-personas" || r.Method != http.MethodGet {
			t.Fatalf("unexpected request: %s %s", r.Method, r.URL.Path)
		}
		json.NewEncoder(w).Encode(PublicPersonasResult{
			Personas: []PersonaSummary{{TwinID: "t1", Name: "Test Persona"}},
		})
	})

	result, err := client.ListPublicPersonas(context.Background())
	if err != nil {
		t.Fatalf("ListPublicPersonas: %v", err)
	}
	if len(result.Personas) != 1 || result.Personas[0].Name != "Test Persona" {
		t.Fatalf("unexpected personas: %+v", result.Personas)
	}
}

func TestRegister_AddsBothReadOnlyTools(t *testing.T) {
	client, _ := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]any{})
	})

	reg := registry.New()
	if err := Register(reg, client); err != nil {
		t.Fatalf("Register: %v", err)
	}

	for _, name := range []string{"twin_chat", "twin_list_public_personas"} {
		def, ok := reg.Lookup(name)
		if !ok {
			t.Fatalf("expected %q to be registered", name)
		}
		if def.Tier != registry.TierReadOnly {
			t.Fatalf("%q tier = %q, want %q", name, def.Tier, registry.TierReadOnly)
		}
	}
}

func TestTwinChatHandler_MissingArgs(t *testing.T) {
	client, _ := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		t.Fatal("handler should not call twin's API when args are missing")
	})

	reg := registry.New()
	if err := Register(reg, client); err != nil {
		t.Fatalf("Register: %v", err)
	}
	def, _ := reg.Lookup("twin_chat")

	if _, err := def.Handler(context.Background(), "alice", map[string]any{"message": "hi"}); err == nil {
		t.Fatal("expected an error when twin_id is missing")
	}
	if _, err := def.Handler(context.Background(), "alice", map[string]any{"twin_id": "t1"}); err == nil {
		t.Fatal("expected an error when message is missing")
	}
}

func TestTwinListPublicPersonasHandler(t *testing.T) {
	client, _ := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(PublicPersonasResult{Personas: []PersonaSummary{{TwinID: "t1"}}})
	})

	reg := registry.New()
	if err := Register(reg, client); err != nil {
		t.Fatalf("Register: %v", err)
	}
	def, _ := reg.Lookup("twin_list_public_personas")

	result, err := def.Handler(context.Background(), "alice", map[string]any{})
	if err != nil {
		t.Fatalf("Handler: %v", err)
	}
	personas, ok := result.(*PublicPersonasResult)
	if !ok || len(personas.Personas) != 1 {
		t.Fatalf("unexpected result: %+v", result)
	}
}
