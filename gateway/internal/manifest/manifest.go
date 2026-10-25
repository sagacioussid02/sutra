// Package manifest is the plain data layer for the Sutra Agent Manifest —
// the small, framework-agnostic document (see gateway/docs/agent-manifest.md)
// any backend project can serve at GET /.well-known/sutra-agent.json to
// describe its own tools. This package only fetches, parses, and validates
// that document; it knows nothing about SQLite, the tool registry, or
// human approval — those live in internal/discovery and
// internal/genericadapter, which build on top of this package the same
// way adapters build on internal/registry's plain in-memory catalog.
package manifest

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
)

// WellKnownPath is the conventional path a project serves its manifest at.
const WellKnownPath = "/.well-known/sutra-agent.json"

// ArgType is a manifest argument's declared type.
type ArgType string

const (
	ArgString  ArgType = "string"
	ArgNumber  ArgType = "number"
	ArgBoolean ArgType = "boolean"
)

func (t ArgType) valid() bool {
	switch t {
	case ArgString, ArgNumber, ArgBoolean:
		return true
	default:
		return false
	}
}

// ArgLocation is where a manifest argument travels in the HTTP request.
type ArgLocation string

const (
	ArgQuery ArgLocation = "query"
	ArgBody  ArgLocation = "body"
)

func (l ArgLocation) valid() bool {
	switch l {
	case ArgQuery, ArgBody:
		return true
	default:
		return false
	}
}

// Arg is one tool argument, as declared by the manifest.
type Arg struct {
	Name     string      `json:"name"`
	Type     ArgType     `json:"type"`
	Required bool        `json:"required"`
	Secret   bool        `json:"secret"`
	In       ArgLocation `json:"in"`
}

// Tool is one tool a project's manifest declares.
type Tool struct {
	Name                  string `json:"name"`
	Description           string `json:"description"`
	TierHint              string `json:"tier_hint"`
	Method                string `json:"method"`
	Path                  string `json:"path"`
	Args                  []Arg  `json:"args"`
	GenericCallable       bool   `json:"generic_callable"`
	GenericCallableReason string `json:"generic_callable_reason,omitempty"`
}

// Project is a manifest's self-description.
type Project struct {
	Name        string `json:"name"`
	Description string `json:"description"`
}

// Manifest is a full Sutra Agent Manifest document.
type Manifest struct {
	Version int     `json:"sutra_manifest_version"`
	Project Project `json:"project"`
	Tools   []Tool  `json:"tools"`
}

// Fetch retrieves and parses the manifest at url. Any outcome other than
// a 200 with a well-formed JSON body — connection failure, timeout,
// non-200 status, malformed JSON — is returned as a wrapped, descriptive
// error; Fetch never panics on untrusted remote input.
func Fetch(ctx context.Context, client *http.Client, url string) (*Manifest, error) {
	if client == nil {
		client = http.DefaultClient
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("manifest: building request for %s: %w", url, err)
	}

	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("manifest: fetching %s: %w", url, err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("manifest: reading response from %s: %w", url, err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("manifest: %s returned %d: %s", url, resp.StatusCode, truncate(body, 300))
	}

	var m Manifest
	if err := json.Unmarshal(body, &m); err != nil {
		return nil, fmt.Errorf("manifest: decoding %s: %w", url, err)
	}
	return &m, nil
}

func truncate(b []byte, n int) string {
	if len(b) <= n {
		return string(b)
	}
	return string(b[:n]) + "...(truncated)"
}

// Validate checks m's structural well-formedness: required fields are
// present, method/type/in values are recognized, and tool names are
// unique. It collects every problem found rather than stopping at the
// first, since a human is about to review this manifest and benefits from
// seeing the whole picture at once.
func (m *Manifest) Validate() error {
	var problems []string

	if m.Version != 1 {
		problems = append(problems, fmt.Sprintf("unsupported sutra_manifest_version %d (expected 1)", m.Version))
	}
	if strings.TrimSpace(m.Project.Name) == "" {
		problems = append(problems, "project.name is required")
	}

	seen := make(map[string]struct{}, len(m.Tools))
	for i, t := range m.Tools {
		label := fmt.Sprintf("tools[%d]", i)
		if t.Name != "" {
			label = fmt.Sprintf("tools[%d] (%q)", i, t.Name)
		}

		if strings.TrimSpace(t.Name) == "" {
			problems = append(problems, label+": name is required")
		} else if _, dup := seen[t.Name]; dup {
			problems = append(problems, label+": duplicate tool name")
		} else {
			seen[t.Name] = struct{}{}
		}

		if strings.TrimSpace(t.Description) == "" {
			problems = append(problems, label+": description is required")
		}
		if t.Method != http.MethodGet && t.Method != http.MethodPost {
			problems = append(problems, label+fmt.Sprintf(": method must be GET or POST, got %q", t.Method))
		}
		if strings.TrimSpace(t.Path) == "" {
			problems = append(problems, label+": path is required")
		}
		if t.GenericCallable && t.GenericCallableReason != "" {
			problems = append(problems, label+": generic_callable_reason is only meaningful when generic_callable is false")
		}
		if !t.GenericCallable && strings.TrimSpace(t.GenericCallableReason) == "" {
			problems = append(problems, label+": generic_callable_reason is required when generic_callable is false")
		}

		for j, a := range t.Args {
			argLabel := fmt.Sprintf("%s.args[%d]", label, j)
			if strings.TrimSpace(a.Name) == "" {
				problems = append(problems, argLabel+": name is required")
			}
			if !a.Type.valid() {
				problems = append(problems, argLabel+fmt.Sprintf(": unrecognized type %q", a.Type))
			}
			if !a.In.valid() {
				problems = append(problems, argLabel+fmt.Sprintf(": unrecognized in %q (must be query or body)", a.In))
			}
		}
	}

	if len(problems) == 0 {
		return nil
	}
	return fmt.Errorf("manifest: %d problem(s) found:\n  - %s", len(problems), strings.Join(problems, "\n  - "))
}

// Hash returns a stable content hash of t's full definition — description,
// tier hint, method, path, args, and generic-callable flag — used by
// internal/discovery to detect a tool's manifest entry changing since it
// was last approved. Two Tool values with the same fields (regardless of
// map/slice allocation) always hash the same, since json.Marshal on a
// struct with fixed field order is already stable.
func (t Tool) Hash() string {
	// Args order is part of the tool's identity as declared — a project
	// reordering its own arg list is a real (if unusual) definition
	// change, and re-approval is a cheap, safe response to it.
	b, err := json.Marshal(t)
	if err != nil {
		// Tool contains only JSON-marshalable primitive fields; this
		// cannot fail in practice. Fall back to a hash of the tool name
		// alone rather than panicking on unexpected input.
		b = []byte(t.Name)
	}
	sum := sha256.Sum256(b)
	return hex.EncodeToString(sum[:])
}
