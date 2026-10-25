// Package registry holds the gateway's tool catalog: every tool the
// gateway can dispatch, tagged with a mandatory tier and, for
// confirm-first tools, a human-readable description builder.
//
// The registry itself does not know about MCP, HTTP, or SQLite — it is
// deliberately a plain in-memory catalog so it can be unit tested and so
// project adapters (twin, finanxe, ...) depend on nothing but this package
// and Go's standard library types.
package registry

import (
	"context"
	"fmt"
	"sync"
)

// Tier controls how a registered tool may be reached.
type Tier string

const (
	// TierReadOnly tools execute immediately on an authorized call.
	TierReadOnly Tier = "read-only"
	// TierConfirmFirst tools create a pending confirmation on the initial
	// call; they only execute once explicitly confirmed.
	TierConfirmFirst Tier = "confirm-first"
	// TierNeverByVoice tools are never exposed as a callable MCP tool in
	// Phase 1. They may still be registered (so the choice to add them
	// later is deliberate, not an oversight) but are excluded from the
	// tool list the gateway builds for clients.
	TierNeverByVoice Tier = "never-by-voice"
)

// Valid reports whether t is one of the recognized tiers.
func (t Tier) Valid() bool {
	switch t {
	case TierReadOnly, TierConfirmFirst, TierNeverByVoice:
		return true
	default:
		return false
	}
}

// Handler is a tool's business logic. It receives the resolved gateway
// user id (never a raw token) and the tool's arguments, and returns a
// JSON-marshalable result.
//
// For a TierReadOnly tool, Handler runs on every authorized call.
// For a TierConfirmFirst tool, Handler only runs when the pending
// confirmation it created is later confirmed — never on the initial call.
type Handler func(ctx context.Context, userID string, args map[string]any) (any, error)

// DescribeFunc renders a human-readable description of what a
// confirm-first tool call would do, built from its arguments alone
// (the underlying Handler is not invoked to produce this description).
type DescribeFunc func(args map[string]any) string

// Definition is one tool's full registration.
type Definition struct {
	// Name is the MCP tool name and must be unique across the registry.
	Name string
	// Description is shown to MCP clients listing tools.
	Description string
	// Tier is mandatory and validated at registration time.
	Tier Tier
	// SecretArgs lists argument names whose values must be redacted
	// before they are written to the audit log. May be nil/empty.
	SecretArgs []string
	// Handler is the tool's business logic. Required for TierReadOnly and
	// TierConfirmFirst; ignored (but still safe to leave nil) for
	// TierNeverByVoice, since such tools are never dispatched in Phase 1.
	Handler Handler
	// Describe is required for TierConfirmFirst tools; it produces the
	// text shown alongside a pending confirmation's id.
	Describe DescribeFunc
}

// SecretArgSet returns SecretArgs as a lookup set.
func (d *Definition) SecretArgSet() map[string]struct{} {
	set := make(map[string]struct{}, len(d.SecretArgs))
	for _, name := range d.SecretArgs {
		set[name] = struct{}{}
	}
	return set
}

// Registry is a thread-safe catalog of tool definitions.
type Registry struct {
	mu   sync.RWMutex
	defs map[string]*Definition
}

// New returns an empty registry.
func New() *Registry {
	return &Registry{defs: make(map[string]*Definition)}
}

// Register validates and adds def to the registry. It returns an error
// (rather than panicking) so callers — typically adapter package init or
// main() — can fail startup loudly with a clear message identifying the
// offending tool, per the requirement that a tool cannot be registered
// without a valid tier.
func (r *Registry) Register(def *Definition) error {
	if def == nil {
		return fmt.Errorf("registry: nil definition")
	}
	if def.Name == "" {
		return fmt.Errorf("registry: tool has no name")
	}
	if !def.Tier.Valid() {
		return fmt.Errorf("registry: tool %q: invalid or missing tier %q", def.Name, def.Tier)
	}
	if def.Tier != TierNeverByVoice && def.Handler == nil {
		return fmt.Errorf("registry: tool %q: tier %q requires a Handler", def.Name, def.Tier)
	}
	if def.Tier == TierConfirmFirst && def.Describe == nil {
		return fmt.Errorf("registry: tool %q: tier %q requires a Describe function", def.Name, def.Tier)
	}

	r.mu.Lock()
	defer r.mu.Unlock()
	if _, exists := r.defs[def.Name]; exists {
		return fmt.Errorf("registry: tool %q already registered", def.Name)
	}
	r.defs[def.Name] = def
	return nil
}

// MustRegister calls Register and panics on error. Intended for use in
// package init() blocks in adapter packages, where a bad registration is
// a programming error that should fail fast at startup.
func (r *Registry) MustRegister(def *Definition) {
	if err := r.Register(def); err != nil {
		panic(err)
	}
}

// Lookup returns the definition for name, if registered.
func (r *Registry) Lookup(name string) (*Definition, bool) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	d, ok := r.defs[name]
	return d, ok
}

// Callable returns every registered definition except TierNeverByVoice
// ones — this is the set the gateway exposes as MCP tools.
func (r *Registry) Callable() []*Definition {
	r.mu.RLock()
	defer r.mu.RUnlock()
	out := make([]*Definition, 0, len(r.defs))
	for _, d := range r.defs {
		if d.Tier == TierNeverByVoice {
			continue
		}
		out = append(out, d)
	}
	return out
}
