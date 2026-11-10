package genericadapter

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestCall_SendsConfiguredHeaders_GETAndPOST(t *testing.T) {
	var got []string
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		got = append(got, r.Header.Get("X-Project-Token"))
		if r.Method == http.MethodPost && r.Header.Get("Content-Type") != "application/json" {
			t.Errorf("auth header must not displace Content-Type, got %q", r.Header.Get("Content-Type"))
		}
		w.Write([]byte(`{}`))
	}))
	t.Cleanup(ts.Close)

	client := NewClient(Config{BaseURL: ts.URL, HTTPClient: ts.Client(), Headers: map[string]string{"X-Project-Token": "abc"}})
	if _, err := client.call(context.Background(), getTool(), map[string]any{}); err != nil {
		t.Fatal(err)
	}
	if _, err := client.call(context.Background(), postTool(), map[string]any{"title": "t", "date": "2026-11-20"}); err != nil {
		t.Fatal(err)
	}
	if len(got) != 2 || got[0] != "abc" || got[1] != "abc" {
		t.Fatalf("header not sent on every call: %v", got)
	}
}

func TestCall_ErrorDoesNotLeakHeaderValue(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "nope", http.StatusUnauthorized)
	}))
	t.Cleanup(ts.Close)

	client := NewClient(Config{BaseURL: ts.URL, HTTPClient: ts.Client(), Headers: map[string]string{"X-Project-Token": "very-secret"}})
	_, err := client.call(context.Background(), getTool(), map[string]any{})
	if err == nil || strings.Contains(err.Error(), "very-secret") {
		t.Fatalf("want a 401 error without the token, got %v", err)
	}
}

func TestNewClient_CopiesHeaders(t *testing.T) {
	h := map[string]string{"X-Project-Token": "abc"}
	client := NewClient(Config{BaseURL: "http://127.0.0.1:1", Headers: h})
	h["X-Project-Token"] = "changed"
	if client.headers["X-Project-Token"] != "abc" {
		t.Fatal("client shares the caller's map")
	}
}
