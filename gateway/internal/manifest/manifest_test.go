package manifest

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func validManifestJSON() string {
	return `{
		"sutra_manifest_version": 1,
		"project": {"name": "finanxe", "description": "Personal finance tracker."},
		"tools": [
			{
				"name": "list_debts",
				"description": "List debts.",
				"tier_hint": "read-only",
				"method": "GET",
				"path": "/api/debts",
				"args": [{"name": "user_id", "type": "string", "required": false, "secret": false, "in": "query"}],
				"generic_callable": true
			}
		]
	}`
}

func TestFetch_ParsesWellFormedManifest(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte(validManifestJSON()))
	}))
	defer ts.Close()

	m, err := Fetch(context.Background(), ts.Client(), ts.URL+WellKnownPath)
	if err != nil {
		t.Fatalf("Fetch: %v", err)
	}
	if m.Project.Name != "finanxe" || len(m.Tools) != 1 || m.Tools[0].Name != "list_debts" {
		t.Fatalf("unexpected manifest: %+v", m)
	}
}

func TestFetch_NonOKStatus_ReturnsError(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer ts.Close()

	if _, err := Fetch(context.Background(), ts.Client(), ts.URL+WellKnownPath); err == nil {
		t.Fatal("expected an error for a 404 response")
	}
}

func TestFetch_MalformedJSON_ReturnsError(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("not json"))
	}))
	defer ts.Close()

	if _, err := Fetch(context.Background(), ts.Client(), ts.URL+WellKnownPath); err == nil {
		t.Fatal("expected an error for malformed JSON")
	}
}

func TestFetch_Unreachable_ReturnsError(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {}))
	url := ts.URL
	ts.Close()

	if _, err := Fetch(context.Background(), http.DefaultClient, url+WellKnownPath); err == nil {
		t.Fatal("expected an error when the manifest endpoint is unreachable")
	}
}

func TestValidate_WellFormedManifest_NoError(t *testing.T) {
	m := &Manifest{
		Version: 1,
		Project: Project{Name: "finanxe"},
		Tools: []Tool{
			{Name: "list_debts", Description: "List debts.", Method: "GET", Path: "/api/debts", GenericCallable: true},
			{Name: "set_debt_funding", Description: "Set funding.", Method: "POST", Path: "/api/debt/funding", GenericCallable: false, GenericCallableReason: "needs fuzzy matching"},
		},
	}
	if err := m.Validate(); err != nil {
		t.Fatalf("Validate: unexpected error: %v", err)
	}
}

func TestValidate_CollectsEveryProblem(t *testing.T) {
	m := &Manifest{
		Version: 2, // wrong
		Project: Project{Name: ""},
		Tools: []Tool{
			{Name: "", Description: "", Method: "DELETE", Path: "", GenericCallable: false}, // missing reason too
			{Name: "dup", Method: "GET", Path: "/x", Description: "d", GenericCallable: true},
			{Name: "dup", Method: "GET", Path: "/y", Description: "d", GenericCallable: true}, // duplicate name
			{
				Name: "bad-arg", Description: "d", Method: "GET", Path: "/z", GenericCallable: true,
				Args: []Arg{{Name: "", Type: "wat", In: "nowhere"}},
			},
		},
	}
	err := m.Validate()
	if err == nil {
		t.Fatal("expected Validate to report problems")
	}
	msg := err.Error()
	for _, want := range []string{
		"unsupported sutra_manifest_version",
		"project.name is required",
		"name is required",
		"method must be GET or POST",
		"path is required",
		"generic_callable_reason is required",
		"duplicate tool name",
		"unrecognized type",
		"unrecognized in",
	} {
		if !strings.Contains(msg, want) {
			t.Errorf("expected error to mention %q, got:\n%s", want, msg)
		}
	}
}

func TestHash_StableAndSensitiveToChanges(t *testing.T) {
	a := Tool{Name: "list_debts", Description: "List debts.", Method: "GET", Path: "/api/debts", GenericCallable: true}
	b := Tool{Name: "list_debts", Description: "List debts.", Method: "GET", Path: "/api/debts", GenericCallable: true}
	if a.Hash() != b.Hash() {
		t.Fatal("expected identical tool definitions to hash the same")
	}

	c := b
	c.Path = "/api/debts/v2"
	if a.Hash() == c.Hash() {
		t.Fatal("expected a changed field to change the hash")
	}
}
