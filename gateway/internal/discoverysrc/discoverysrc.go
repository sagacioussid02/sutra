// Package discoverysrc loads the gitignored discovery-sources.yaml config:
// the list of backend projects sutra knows how to fetch a Sutra Agent
// Manifest from. Unlike internal/authcfg's tokens.yaml, a missing sources
// file is not an error — discovery is an optional capability, not required
// to run the gateway.
package discoverysrc

import (
	"errors"
	"fmt"
	"net/http"
	"os"
	"strings"

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
	// AuthHeader, when set, is the name of a header sent on every tool
	// call to this source (e.g. "X-Finanxe-Token"). Its value is never
	// written in this file: it is read at startup from the environment
	// variable named by AuthEnv. The manifest itself is still fetched
	// without it — manifests are public by design.
	AuthHeader string `yaml:"auth_header"`
	// AuthEnv names the environment variable holding AuthHeader's value.
	// Required when AuthHeader is set.
	AuthEnv string `yaml:"auth_env"`
}

// ErrAuthEnvUnset is returned by AuthHeaders when a source declares an auth
// header but its environment variable is empty. Callers should skip the
// source rather than call it without credentials.
var ErrAuthEnvUnset = errors.New("auth environment variable is empty")

// AuthHeaders returns the headers to send on every tool call to s: nil when
// s declares no auth header, or a single header whose value comes from the
// environment (looked up with getenv, normally os.Getenv).
func (s Source) AuthHeaders(getenv func(string) string) (map[string]string, error) {
	if s.AuthHeader == "" {
		return nil, nil
	}
	v := strings.TrimSpace(getenv(s.AuthEnv))
	if v == "" {
		return nil, fmt.Errorf("discoverysrc: %s: %w: %s", s.Name, ErrAuthEnvUnset, s.AuthEnv)
	}
	return map[string]string{s.AuthHeader: v}, nil
}

// reservedHeaders may never be overridden by a source's auth header: the
// gateway sets them itself, or overriding them would change what the call
// means rather than who it's from.
var reservedHeaders = map[string]bool{
	"Host":              true,
	"Content-Type":      true,
	"Content-Length":    true,
	"Transfer-Encoding": true,
	"Connection":        true,
	"Cookie":            true,
}

func (s Source) validate() error {
	if s.AuthHeader == "" && s.AuthEnv == "" {
		return nil
	}
	if s.AuthHeader == "" || s.AuthEnv == "" {
		return fmt.Errorf("source %q: auth_header and auth_env must be set together", s.Name)
	}
	if !validHeaderName(s.AuthHeader) {
		return fmt.Errorf("source %q: auth_header %q is not a valid header name", s.Name, s.AuthHeader)
	}
	if reservedHeaders[http.CanonicalHeaderKey(s.AuthHeader)] {
		return fmt.Errorf("source %q: auth_header %q is reserved", s.Name, s.AuthHeader)
	}
	return nil
}

func validHeaderName(name string) bool {
	if name == "" {
		return false
	}
	for _, r := range name {
		switch {
		case r >= 'a' && r <= 'z', r >= 'A' && r <= 'Z', r >= '0' && r <= '9', r == '-':
		default:
			return false
		}
	}
	return true
}

// Config is the full loaded sources configuration.
type Config struct {
	Sources []Source `yaml:"sources"`
}

// Load reads and parses the YAML sources config at path. A missing file
// returns an empty Config, not an error. A source with a malformed auth
// setting is an error, so a typo can't silently send calls unauthenticated.
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
	for _, s := range c.Sources {
		if err := s.validate(); err != nil {
			return nil, fmt.Errorf("discoverysrc: %s: %w", path, err)
		}
	}
	return &c, nil
}
