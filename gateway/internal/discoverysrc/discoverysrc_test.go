package discoverysrc

import (
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
