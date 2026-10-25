package authcfg

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"testing"

	sdkauth "github.com/modelcontextprotocol/go-sdk/auth"
)

func writeConfig(t *testing.T, yaml string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "tokens.yaml")
	if err := os.WriteFile(path, []byte(yaml), 0o600); err != nil {
		t.Fatal(err)
	}
	return path
}

const sampleConfig = `
users:
  - id: sid
    token: sid-token-abc
    allowed_tools:
      - twin_chat
      - finanxe_get_snapshot
`

func TestLoadAndVerify(t *testing.T) {
	cfg, err := Load(writeConfig(t, sampleConfig))
	if err != nil {
		t.Fatalf("Load: %v", err)
	}

	info, err := cfg.Verifier()(context.Background(), "sid-token-abc", nil)
	if err != nil {
		t.Fatalf("Verifier: %v", err)
	}
	if info.UserID != "sid" {
		t.Fatalf("expected user id 'sid', got %q", info.UserID)
	}
}

func TestVerifyUnknownTokenIsInvalid(t *testing.T) {
	cfg, _ := Load(writeConfig(t, sampleConfig))
	_, err := cfg.Verifier()(context.Background(), "not-a-real-token", nil)
	if !errors.Is(err, sdkauth.ErrInvalidToken) {
		t.Fatalf("expected sdkauth.ErrInvalidToken, got %v", err)
	}
}

func TestUserAllowedRespectsPerUserToolList(t *testing.T) {
	cfg, _ := Load(writeConfig(t, sampleConfig))
	if !cfg.UserAllowed("sid", "twin_chat") {
		t.Fatal("expected sid to be allowed to call twin_chat")
	}
	if cfg.UserAllowed("sid", "finanxe_set_debt_funding") {
		t.Fatal("expected sid NOT to be allowed to call a tool outside their allowed_tools list")
	}
	if cfg.UserAllowed("unknown-user", "twin_chat") {
		t.Fatal("expected an unknown user id to be allowed nothing")
	}
}

func TestGatewayConfirmAlwaysAllowedForKnownUser(t *testing.T) {
	cfg, _ := Load(writeConfig(t, sampleConfig))
	if !cfg.UserAllowed("sid", GatewayConfirmTool) {
		t.Fatal("expected gateway_confirm to be allowed for any known user even though it's not in allowed_tools")
	}
	if cfg.UserAllowed("nobody", GatewayConfirmTool) {
		t.Fatal("expected gateway_confirm to be denied for an unknown user id")
	}
}

func TestLoadRejectsEmptyConfig(t *testing.T) {
	_, err := Load(writeConfig(t, "users: []\n"))
	if err == nil {
		t.Fatal("expected an error loading a config that defines no users")
	}
}
