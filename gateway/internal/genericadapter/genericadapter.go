// Package genericadapter turns an approved, generically callable
// manifest.Tool into a working registry.Definition — the auto-wiring path
// for straightforward REST-shaped tools discovered via internal/manifest
// and approved via internal/discovery, requiring no hand-written Go code
// per tool. It deliberately mirrors internal/finanxe's get/postJSON error
// handling and internal/finanxe/mutate.go's arg-coercion discipline, since
// this package exists to generalize exactly that pattern rather than
// invent a new one.
package genericadapter

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/siddharthshankar/sutra/gateway/internal/manifest"
	"github.com/siddharthshankar/sutra/gateway/internal/registry"
)

const defaultTimeout = 15 * time.Second

// Config configures a Client.
type Config struct {
	// BaseURL is the discovered project's base URL (its manifest tool
	// paths are relative to this), e.g. http://127.0.0.1:8002.
	BaseURL string
	// HTTPClient overrides the default client (used by tests to point at
	// an httptest.Server).
	HTTPClient *http.Client
}

// Client calls a discovered project's plain HTTP API.
type Client struct {
	baseURL    string
	httpClient *http.Client
}

// NewClient builds a Client from cfg.
func NewClient(cfg Config) *Client {
	httpClient := cfg.HTTPClient
	if httpClient == nil {
		httpClient = &http.Client{Timeout: defaultTimeout}
	}
	return &Client{baseURL: strings.TrimRight(cfg.BaseURL, "/"), httpClient: httpClient}
}

// call issues tool.Method to tool.Path, splitting args by each declared
// Arg.In: query-string for "query" (mirroring internal/finanxe's get),
// JSON body for "body" (mirroring internal/finanxe's postJSON). Every
// required arg must be present; unrecognized arg values are rejected
// rather than silently dropped. Any outcome other than a 2xx — a missing
// required arg, connection failure, timeout, non-2xx status — is returned
// as a wrapped, tool-level error. call never panics on untrusted MCP
// client input.
func (c *Client) call(ctx context.Context, tool manifest.Tool, args map[string]any) ([]byte, error) {
	query := url.Values{}
	body := map[string]any{}

	for _, argDef := range tool.Args {
		v, present := args[argDef.Name]
		if !present {
			if argDef.Required {
				return nil, fmt.Errorf("genericadapter: %s: missing required argument %q", tool.Name, argDef.Name)
			}
			continue
		}
		if err := checkType(argDef, v); err != nil {
			return nil, fmt.Errorf("genericadapter: %s: %w", tool.Name, err)
		}
		switch argDef.In {
		case manifest.ArgQuery:
			query.Set(argDef.Name, fmt.Sprintf("%v", v))
		case manifest.ArgBody:
			body[argDef.Name] = v
		}
	}

	target := c.baseURL + tool.Path
	var reqBody io.Reader
	if tool.Method == http.MethodPost {
		encoded, err := json.Marshal(body)
		if err != nil {
			return nil, fmt.Errorf("genericadapter: %s: encoding request body: %w", tool.Name, err)
		}
		reqBody = bytes.NewReader(encoded)
	} else if q := query.Encode(); q != "" {
		target += "?" + q
	}

	req, err := http.NewRequestWithContext(ctx, tool.Method, target, reqBody)
	if err != nil {
		return nil, fmt.Errorf("genericadapter: %s: building request: %w", tool.Name, err)
	}
	if tool.Method == http.MethodPost {
		req.Header.Set("Content-Type", "application/json")
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("genericadapter: %s: calling %s %s (is it reachable at %s?): %w", tool.Name, tool.Method, tool.Path, c.baseURL, err)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("genericadapter: %s: reading response: %w", tool.Name, err)
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("genericadapter: %s: %s %s returned %d: %s", tool.Name, tool.Method, tool.Path, resp.StatusCode, truncate(respBody, 300))
	}
	return respBody, nil
}

func checkType(argDef manifest.Arg, v any) error {
	switch argDef.Type {
	case manifest.ArgString:
		if _, ok := v.(string); !ok {
			return fmt.Errorf("argument %q must be a string", argDef.Name)
		}
	case manifest.ArgNumber:
		if _, ok := v.(float64); !ok {
			return fmt.Errorf("argument %q must be a number", argDef.Name)
		}
	case manifest.ArgBoolean:
		if _, ok := v.(bool); !ok {
			return fmt.Errorf("argument %q must be a boolean", argDef.Name)
		}
	}
	return nil
}

func truncate(b []byte, n int) string {
	if len(b) <= n {
		return string(b)
	}
	return string(b[:n]) + "...(truncated)"
}

// BuildDefinition builds a *registry.Definition for tool, backed by
// client, under the given sourceName. The registered tool name is
// "<sourceName>_<tool.Name>", matching the naming convention the
// hand-written twin/finanxe adapters already use, so a generically-wired
// tool is indistinguishable to an MCP client from a hand-written one.
//
// tier is the human-assigned tier from the tool's approval record —
// tool.TierHint is never used here; the caller (internal/genericadapter's
// RegisterApproved, driven by discovery.Approval) is responsible for
// passing the approved tier, not the manifest's own suggestion.
func BuildDefinition(client *Client, sourceName string, tool manifest.Tool, tier registry.Tier) (*registry.Definition, error) {
	if !tier.Valid() {
		return nil, fmt.Errorf("genericadapter: %s_%s: invalid tier %q", sourceName, tool.Name, tier)
	}

	var secretArgs []string
	for _, a := range tool.Args {
		if a.Secret {
			secretArgs = append(secretArgs, a.Name)
		}
	}

	def := &registry.Definition{
		Name:        sourceName + "_" + tool.Name,
		Description: tool.Description,
		Tier:        tier,
		SecretArgs:  secretArgs,
		Handler: func(ctx context.Context, _ string, args map[string]any) (any, error) {
			body, err := client.call(ctx, tool, args)
			if err != nil {
				return nil, err
			}
			var result any
			if err := json.Unmarshal(body, &result); err != nil {
				// A non-JSON success response is unusual but not
				// necessarily wrong (some endpoints may return plain
				// text); surface it as-is rather than failing the call.
				return string(body), nil
			}
			return result, nil
		},
	}
	if tier == registry.TierConfirmFirst {
		def.Describe = func(args map[string]any) string {
			return describeGeneric(tool, args)
		}
	}
	return def, nil
}

// describeGeneric renders a human-readable description of a pending
// confirm-first call from the tool's own description plus its argument
// values — no per-tool hand-written describer needed, unlike
// internal/finanxe/mutate.go's bespoke describeX functions, which remain
// hand-written because that package's tools are hand-registered, not
// generically discovered.
func describeGeneric(tool manifest.Tool, args map[string]any) string {
	if len(args) == 0 {
		return tool.Description
	}
	parts := make([]string, 0, len(args))
	for _, argDef := range tool.Args {
		if v, ok := args[argDef.Name]; ok {
			parts = append(parts, fmt.Sprintf("%s=%v", argDef.Name, v))
		}
	}
	return fmt.Sprintf("%s (%s)", tool.Description, strings.Join(parts, ", "))
}
