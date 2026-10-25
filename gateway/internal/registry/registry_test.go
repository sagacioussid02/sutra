package registry

import (
	"context"
	"testing"
)

func readOnlyHandler(ctx context.Context, userID string, args map[string]any) (any, error) {
	return "ok", nil
}

func TestRegisterRequiresValidTier(t *testing.T) {
	r := New()
	err := r.Register(&Definition{Name: "no-tier", Handler: readOnlyHandler})
	if err == nil {
		t.Fatal("expected an error registering a tool with no tier, got nil")
	}

	err = r.Register(&Definition{Name: "bad-tier", Tier: Tier("made-up"), Handler: readOnlyHandler})
	if err == nil {
		t.Fatal("expected an error registering a tool with an unrecognized tier, got nil")
	}
}

func TestRegisterConfirmFirstRequiresDescribe(t *testing.T) {
	r := New()
	err := r.Register(&Definition{
		Name:    "mutate",
		Tier:    TierConfirmFirst,
		Handler: readOnlyHandler,
	})
	if err == nil {
		t.Fatal("expected an error registering a confirm-first tool with no Describe func, got nil")
	}
}

func TestRegisterReadOnlyRequiresHandler(t *testing.T) {
	r := New()
	err := r.Register(&Definition{Name: "no-handler", Tier: TierReadOnly})
	if err == nil {
		t.Fatal("expected an error registering a read-only tool with no Handler, got nil")
	}
}

func TestRegisterNeverByVoiceDoesNotRequireHandler(t *testing.T) {
	r := New()
	if err := r.Register(&Definition{Name: "secret", Tier: TierNeverByVoice}); err != nil {
		t.Fatalf("unexpected error registering a never-by-voice tool with no handler: %v", err)
	}
}

func TestRegisterDuplicateNameFails(t *testing.T) {
	r := New()
	def := &Definition{Name: "dup", Tier: TierReadOnly, Handler: readOnlyHandler}
	if err := r.Register(def); err != nil {
		t.Fatalf("first registration failed: %v", err)
	}
	if err := r.Register(def); err == nil {
		t.Fatal("expected an error on duplicate registration, got nil")
	}
}

func TestCallableExcludesNeverByVoice(t *testing.T) {
	r := New()
	r.MustRegister(&Definition{Name: "public", Tier: TierReadOnly, Handler: readOnlyHandler})
	r.MustRegister(&Definition{Name: "secret", Tier: TierNeverByVoice})

	callable := r.Callable()
	if len(callable) != 1 || callable[0].Name != "public" {
		t.Fatalf("expected only the read-only tool in Callable(), got %+v", callable)
	}

	// The never-by-voice tool is still reachable via Lookup (it exists in
	// the registry for future use) — it is the gateway's dispatch layer,
	// not the registry, that must refuse to call it. See internal/gateway.
	if _, ok := r.Lookup("secret"); !ok {
		t.Fatal("expected never-by-voice tool to still be present via Lookup")
	}
}

func TestRedactMasksOnlyDeclaredSecrets(t *testing.T) {
	args := map[string]any{
		"debt_name": "visa",
		"api_key":   "sk-live-12345",
	}
	redacted := Redact(args, []string{"api_key"})
	if redacted["debt_name"] != "visa" {
		t.Fatalf("expected non-secret arg untouched, got %v", redacted["debt_name"])
	}
	if redacted["api_key"] != RedactionMarker {
		t.Fatalf("expected secret arg redacted, got %v", redacted["api_key"])
	}
	// original map must not be mutated
	if args["api_key"] != "sk-live-12345" {
		t.Fatal("Redact must not mutate its input map")
	}
}
