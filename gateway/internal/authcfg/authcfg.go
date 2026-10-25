// Package authcfg loads the gateway's static, gitignored token
// configuration: which bearer tokens exist, which user id each belongs
// to, and which tools that user may call. It also adapts that
// configuration into the shape the official MCP Go SDK's
// auth.RequireBearerToken middleware expects, so authentication is
// enforced by SDK code, not a hand-rolled equivalent.
package authcfg

import (
	"context"
	"fmt"
	"net/http"
	"os"

	sdkauth "github.com/modelcontextprotocol/go-sdk/auth"
	"gopkg.in/yaml.v3"
)

// GatewayConfirmTool is the name of the built-in tool every authenticated
// user may call regardless of their AllowedTools list, since it is how a
// user confirms their own pending confirm-first calls.
const GatewayConfirmTool = "gateway_confirm"

// User is one trusted person's static configuration.
type User struct {
	ID           string   `yaml:"id"`
	Token        string   `yaml:"token"`
	AllowedTools []string `yaml:"allowed_tools"`
}

// Config is the full loaded token configuration.
type Config struct {
	Users []User `yaml:"users"`

	byToken map[string]*User
	allowed map[string]map[string]struct{} // user id -> allowed tool set
}

// Load reads and parses the YAML token config at path.
func Load(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("authcfg: reading %s: %w", path, err)
	}
	var c Config
	if err := yaml.Unmarshal(data, &c); err != nil {
		return nil, fmt.Errorf("authcfg: parsing %s: %w", path, err)
	}
	c.index()
	if len(c.byToken) == 0 {
		return nil, fmt.Errorf("authcfg: %s defines no users", path)
	}
	return &c, nil
}

func (c *Config) index() {
	c.byToken = make(map[string]*User, len(c.Users))
	c.allowed = make(map[string]map[string]struct{}, len(c.Users))
	for i := range c.Users {
		u := &c.Users[i]
		c.byToken[u.Token] = u
		set := make(map[string]struct{}, len(u.AllowedTools))
		for _, t := range u.AllowedTools {
			set[t] = struct{}{}
		}
		c.allowed[u.ID] = set
	}
}

// UserAllowed reports whether userID may call toolName. gateway_confirm is
// always allowed for any known user id, since it only ever acts on that
// same user's own pending confirmations (enforced by internal/confirm).
func (c *Config) UserAllowed(userID, toolName string) bool {
	if toolName == GatewayConfirmTool {
		_, known := c.allowed[userID]
		return known
	}
	set, ok := c.allowed[userID]
	if !ok {
		return false
	}
	_, ok = set[toolName]
	return ok
}

// Verifier returns an sdkauth.TokenVerifier backed by this config, for use
// with auth.RequireBearerToken. Unknown tokens return sdkauth.ErrInvalidToken,
// per that function's documented contract.
func (c *Config) Verifier() sdkauth.TokenVerifier {
	return func(ctx context.Context, token string, req *http.Request) (*sdkauth.TokenInfo, error) {
		u, ok := c.byToken[token]
		if !ok {
			return nil, sdkauth.ErrInvalidToken
		}
		return &sdkauth.TokenInfo{UserID: u.ID}, nil
	}
}
