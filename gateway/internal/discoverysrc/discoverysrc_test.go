package discoverysrc

import (
	"errors"
	"os"
	"path/filepath"
	"testing"
)

func TestLoad_ParsesSources(t *testing.T) {
	path := filepath.Join(t.TempDir(), "discovery-sources.yaml")
	err := os.WriteFile(path, []byte(`
sources:
  - name: finanxe
    manifest_url: http://127.0.0.1:8002/.well-known/sutra-agent.json
    base_url: http://127.0.0.1:8002
`), 0o600)
	if err != nil {
		t.Fatal(err)
	}

	c, err := Load(path)
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if len(c.Sources) != 1 || c.Sources[0].Name != "finanxe" {
		t.Fatalf("unexpected sources: %+v", c.Sources)
	}
}

func TestLoad_MissingFile_ReturnsEmptyConfigNoError(t *testing.T) {
	c, err := Load(filepath.Join(t.TempDir(), "does-not-exist.yaml"))
	if err != nil {
		t.Fatalf("Load: unexpected error for a missing file: %v", err)
	}
	if len(c.Sources) != 0 {
		t.Fatalf("expected an empty Config, got %+v", c)
	}
}

func writeSources(t *testing.T, body string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "discovery-sources.yaml")
	if err := os.WriteFile(path, []byte(body), 0o600); err != nil {
		t.Fatal(err)
	}
	return path
}

func TestLoad_ParsesAuthHeader(t *testing.T) {
	c, err := Load(writeSources(t, `
sources:
  - name: finanxe
    manifest_url: http://127.0.0.1:8002/.well-known/sutra-agent.json
    base_url: http://127.0.0.1:8002
    auth_header: X-Finanxe-Token
    auth_env: FINANXE_API_TOKEN
`))
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	s := c.Sources[0]
	if s.AuthHeader != "X-Finanxe-Token" || s.AuthEnv != "FINANXE_API_TOKEN" {
		t.Fatalf("auth not parsed: %+v", s)
	}
}

func TestLoad_RejectsHalfConfiguredAuth(t *testing.T) {
	for name, body := range map[string]string{
		"header only": "sources:\n  - name: a\n    auth_header: X-Token\n",
		"env only":    "sources:\n  - name: a\n    auth_env: A_TOKEN\n",
		"bad name":    "sources:\n  - name: a\n    auth_header: \"X Token\"\n    auth_env: A_TOKEN\n",
		"reserved":    "sources:\n  - name: a\n    auth_header: host\n    auth_env: A_TOKEN\n",
	} {
		t.Run(name, func(t *testing.T) {
			if _, err := Load(writeSources(t, body)); err == nil {
				t.Fatal("expected an error")
			}
		})
	}
}

func TestAuthHeaders(t *testing.T) {
	env := map[string]string{"SET_TOKEN": " s3cret \n"}
	getenv := func(k string) string { return env[k] }

	none, err := Source{Name: "plain"}.AuthHeaders(getenv)
	if err != nil || none != nil {
		t.Fatalf("no auth: got %v, %v", none, err)
	}

	h, err := Source{Name: "a", AuthHeader: "X-Token", AuthEnv: "SET_TOKEN"}.AuthHeaders(getenv)
	if err != nil {
		t.Fatalf("AuthHeaders: %v", err)
	}
	if h["X-Token"] != "s3cret" {
		t.Fatalf("got %v", h)
	}

	_, err = Source{Name: "b", AuthHeader: "X-Token", AuthEnv: "UNSET_TOKEN"}.AuthHeaders(getenv)
	if !errors.Is(err, ErrAuthEnvUnset) {
		t.Fatalf("expected ErrAuthEnvUnset, got %v", err)
	}
}
