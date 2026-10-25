// Package discoverysrc loads the gitignored discovery-sources.yaml config:
// the list of backend projects sutra knows how to fetch a Sutra Agent
// Manifest from. Unlike internal/authcfg's tokens.yaml, a missing sources
// file is not an error — discovery is an optional capability, not required
// to run the gateway.
package discoverysrc

import (
	"errors"
	"fmt"
	"os"

	"gopkg.in/yaml.v3"
)

// Source is one backend project sutra can discover tools from.
type Source struct {
	// Name identifies the project and becomes the registered tool name
	// prefix (e.g. "finanxe" -> "finanxe_list_debts").
	Name string `yaml:"name"`
	// ManifestURL is where the project's Sutra Agent Manifest is served.
	ManifestURL string `yaml:"manifest_url"`
	// BaseURL is what an approved, generically-callable tool from this
	// source is actually called against.
	BaseURL string `yaml:"base_url"`
}

// Config is the full loaded sources configuration.
type Config struct {
	Sources []Source `yaml:"sources"`
}

// Load reads and parses the YAML sources config at path. A missing file
// returns an empty Config, not an error.
func Load(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return &Config{}, nil
		}
		return nil, fmt.Errorf("discoverysrc: reading %s: %w", path, err)
	}
	var c Config
	if err := yaml.Unmarshal(data, &c); err != nil {
		return nil, fmt.Errorf("discoverysrc: parsing %s: %w", path, err)
	}
	return &c, nil
}
