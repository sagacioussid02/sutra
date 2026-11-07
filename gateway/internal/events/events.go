// Package events is the gateway's front door for inbound events: typed
// envelopes from registered producers, validated against a per-kind schema
// and forwarded to the orchestrator's event log. Event payloads are data,
// never instructions — the envelope has no field for a confirmation, an
// approval, or a tier change.
package events

import (
	"crypto/rand"
	_ "embed"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"sort"
	"time"
)

// MaxPayloadBytes bounds the serialized payload of any event.
const MaxPayloadBytes = 1024

//go:embed kinds.json
var kindsJSON []byte

// Field is one declared payload field. Every field is a short string.
type Field struct {
	Required bool     `json:"required"`
	Max      int      `json:"max"`
	Enum     []string `json:"enum"`
}

// Kind declares one event kind: its payload schema and expiry rules.
type Kind struct {
	DefaultExpiryMinutes int              `json:"default_expiry_minutes"`
	Fields               map[string]Field `json:"fields"`
}

// Registry is the set of declared kinds.
type Registry map[string]Kind

// LoadRegistry parses the embedded kind registry.
func LoadRegistry() (Registry, error) {
	var r Registry
	if err := json.Unmarshal(kindsJSON, &r); err != nil {
		return nil, fmt.Errorf("events: parsing kinds.json: %w", err)
	}
	return r, nil
}

// Names returns the declared kind names, sorted.
func (r Registry) Names() []string {
	out := make([]string, 0, len(r))
	for k := range r {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

// Envelope is what the gateway forwards to the orchestrator.
type Envelope struct {
	ID             string            `json:"id"`
	Source         string            `json:"source"`
	Kind           string            `json:"kind"`
	OccurredAt     time.Time         `json:"occurred_at"`
	ReceivedAt     time.Time         `json:"received_at"`
	UserID         string            `json:"user_id"`
	Payload        map[string]string `json:"payload"`
	IdempotencyKey string            `json:"idempotency_key,omitempty"`
	ExpiresAt      time.Time         `json:"expires_at"`
}

// Submission is what a producer posts. The producer cannot set the id, the
// source, the user, or the receive time: the gateway derives those.
type Submission struct {
	Kind           string            `json:"kind"`
	OccurredAt     *time.Time        `json:"occurred_at"`
	Payload        map[string]string `json:"payload"`
	IdempotencyKey string            `json:"idempotency_key"`
	ExpiresInMin   int               `json:"expires_in_minutes"`
}

// ValidatePayload checks a payload against the kind's schema and bound.
func (k Kind) ValidatePayload(p map[string]string) error {
	size := 0
	for name, value := range p {
		f, ok := k.Fields[name]
		if !ok {
			return fmt.Errorf("unknown payload field %q", name)
		}
		if f.Max > 0 && len([]rune(value)) > f.Max {
			return fmt.Errorf("payload field %q is longer than %d characters", name, f.Max)
		}
		if len(f.Enum) > 0 && !contains(f.Enum, value) {
			return fmt.Errorf("payload field %q must be one of %v", name, f.Enum)
		}
		size += len(name) + len(value)
	}
	if size > MaxPayloadBytes {
		return fmt.Errorf("payload is larger than %d bytes", MaxPayloadBytes)
	}
	for name, f := range k.Fields {
		if f.Required && p[name] == "" {
			return fmt.Errorf("payload field %q is required", name)
		}
	}
	return nil
}

func contains(list []string, s string) bool {
	for _, v := range list {
		if v == s {
			return true
		}
	}
	return false
}

// Build validates a submission and turns it into an envelope. The caller has
// already checked that the producer may emit sub.Kind.
func (r Registry) Build(producerID, owner string, sub Submission, now time.Time) (Envelope, error) {
	kind, ok := r[sub.Kind]
	if !ok {
		return Envelope{}, fmt.Errorf("unknown event kind %q", sub.Kind)
	}
	if err := kind.ValidatePayload(sub.Payload); err != nil {
		return Envelope{}, err
	}
	if len(sub.IdempotencyKey) > 80 {
		return Envelope{}, fmt.Errorf("idempotency_key is longer than 80 characters")
	}
	minutes := kind.DefaultExpiryMinutes
	if sub.ExpiresInMin > 0 && sub.ExpiresInMin < minutes {
		minutes = sub.ExpiresInMin // a producer may shorten the expiry, never extend it
	}
	occurred := now
	if sub.OccurredAt != nil && !sub.OccurredAt.After(now) {
		occurred = sub.OccurredAt.UTC()
	}
	id, err := newID()
	if err != nil {
		return Envelope{}, err
	}
	return Envelope{
		ID: id, Source: producerID, Kind: sub.Kind, OccurredAt: occurred, ReceivedAt: now.UTC(),
		UserID: owner, Payload: sub.Payload, IdempotencyKey: sub.IdempotencyKey,
		ExpiresAt: now.UTC().Add(time.Duration(minutes) * time.Minute),
	}, nil
}

func newID() (string, error) {
	b := make([]byte, 12)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	return hex.EncodeToString(b), nil
}
