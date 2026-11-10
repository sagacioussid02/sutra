package finanxe

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// finanxeLike mimics finanxe's local_auth: every /api/* route except
// /api/health needs the X-Finanxe-Token header.
func finanxeLike(token string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get(TokenHeader) != token {
			w.WriteHeader(http.StatusUnauthorized)
			json.NewEncoder(w).Encode(map[string]string{"error": "Missing or invalid API token"})
			return
		}
		json.NewEncoder(w).Encode(map[string]any{"ok": true})
	}
}

func TestGetAndPost_SendTokenHeader(t *testing.T) {
	ts := httptest.NewServer(finanxeLike("tok-123"))
	t.Cleanup(ts.Close)
	client := NewClient(Config{BaseURL: ts.URL, HTTPClient: ts.Client(), APIToken: " tok-123\n"})

	if _, err := client.get(context.Background(), "/api/snapshot"); err != nil {
		t.Fatalf("get with token: %v", err)
	}
	if _, err := client.postJSON(context.Background(), "/api/goals/add", map[string]any{}); err != nil {
		t.Fatalf("post with token: %v", err)
	}
}

func TestNoToken_SurfacesFinanxe401_WithoutLeakingToken(t *testing.T) {
	ts := httptest.NewServer(finanxeLike("tok-123"))
	t.Cleanup(ts.Close)
	client := NewClient(Config{BaseURL: ts.URL, HTTPClient: ts.Client(), APIToken: "wrong-token"})

	_, err := client.get(context.Background(), "/api/snapshot")
	if err == nil || !strings.Contains(err.Error(), "401") {
		t.Fatalf("expected a 401 error, got %v", err)
	}
	if strings.Contains(err.Error(), "wrong-token") {
		t.Fatalf("error leaks the token: %v", err)
	}
}

func TestNoTokenConfigured_SendsNoHeader(t *testing.T) {
	var sawHeader bool
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, sawHeader = r.Header[http.CanonicalHeaderKey(TokenHeader)]
		json.NewEncoder(w).Encode(map[string]any{})
	}))
	t.Cleanup(ts.Close)
	client := NewClient(Config{BaseURL: ts.URL, HTTPClient: ts.Client()})
	if _, err := client.get(context.Background(), "/api/snapshot"); err != nil {
		t.Fatal(err)
	}
	if sawHeader {
		t.Fatal("sent an empty token header")
	}
}
