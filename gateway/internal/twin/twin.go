// Package twin adapts twin's existing deployed HTTP API (/chat,
// /public-personas) into read-only tools for the gateway's registry. It
// calls twin over HTTPS — twin runs on AWS Lambda, not locally — and never
// modifies twin itself.
//
// twin's /chat endpoint accepts anonymous, session-based calls (no Clerk
// JWT required); this adapter always calls it anonymously and derives its
// own stable session id per (gateway user, twin id) pair so repeated calls
// from the same gateway user continue the same twin-side conversation.
package twin

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/siddharthshankar/sutra/gateway/internal/registry"
)

const defaultTimeout = 15 * time.Second

// Config configures a Client.
type Config struct {
	// BaseURL is twin's deployed API base URL (e.g.
	// https://2u95puvzsd.execute-api.us-east-2.amazonaws.com), no trailing
	// slash required.
	BaseURL string
	// SessionSecret, if set, HMAC-derives session ids so they are
	// unguessable even if the gateway user id and twin id are both known.
	// If empty, session ids fall back to a plain SHA-256 derivation (fine
	// for Phase 1's local, trusted-user scope, per twin's own dev fallback
	// for the same trade-off).
	SessionSecret string
	// HTTPClient overrides the default client (used by tests to point at
	// an httptest.Server, and to set a shorter timeout).
	HTTPClient *http.Client
}

// Client calls twin's deployed HTTP API.
type Client struct {
	baseURL       string
	sessionSecret string
	httpClient    *http.Client
}

// NewClient builds a Client from cfg.
func NewClient(cfg Config) *Client {
	httpClient := cfg.HTTPClient
	if httpClient == nil {
		httpClient = &http.Client{Timeout: defaultTimeout}
	}
	return &Client{
		baseURL:       strings.TrimRight(cfg.BaseURL, "/"),
		sessionSecret: cfg.SessionSecret,
		httpClient:    httpClient,
	}
}

// deriveSessionID returns a stable, opaque session id for a (gateway user,
// twin) pair. It is independent of twin's own _derive_session_id, which
// requires an authenticated chatter_id the gateway does not have — this
// only needs to be stable across calls from the same gateway user, not
// match twin's internal scheme.
func (c *Client) deriveSessionID(gatewayUserID, twinID string) string {
	input := gatewayUserID + ":" + twinID
	if c.sessionSecret != "" {
		mac := hmac.New(sha256.New, []byte(c.sessionSecret))
		mac.Write([]byte(input))
		return hex.EncodeToString(mac.Sum(nil))
	}
	sum := sha256.Sum256([]byte(input))
	return hex.EncodeToString(sum[:])
}

type chatRequest struct {
	Message   string `json:"message"`
	SessionID string `json:"session_id,omitempty"`
	TwinID    string `json:"twin_id,omitempty"`
}

// ChatResult is twin_chat's tool result.
type ChatResult struct {
	Response  string `json:"response"`
	SessionID string `json:"session_id"`
}

// Chat calls twin's /chat endpoint anonymously, using a session id derived
// from gatewayUserID and twinID so repeated calls continue the same
// conversation.
func (c *Client) Chat(ctx context.Context, gatewayUserID, twinID, message string) (*ChatResult, error) {
	sessionID := c.deriveSessionID(gatewayUserID, twinID)
	body, err := json.Marshal(chatRequest{Message: message, SessionID: sessionID, TwinID: twinID})
	if err != nil {
		return nil, fmt.Errorf("twin: encoding chat request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/chat", bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("twin: building chat request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("twin: calling /chat: %w", err)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("twin: reading /chat response: %w", err)
	}

	if resp.StatusCode == http.StatusNotFound {
		return nil, fmt.Errorf("twin: twin %q not found", twinID)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("twin: /chat returned %d: %s", resp.StatusCode, truncate(respBody, 300))
	}

	var out ChatResult
	if err := json.Unmarshal(respBody, &out); err != nil {
		return nil, fmt.Errorf("twin: decoding /chat response: %w", err)
	}
	return &out, nil
}

// PersonaSummary mirrors twin's _public_persona_summary shape.
type PersonaSummary struct {
	TwinID             string `json:"twin_id"`
	PersonaID          string `json:"persona_id"`
	Name               string `json:"name"`
	Title              string `json:"title"`
	Tagline            string `json:"tagline"`
	Era                string `json:"era"`
	ImageURL           string `json:"image_url"`
	PersonalitySummary string `json:"personality_summary"`
	ChatURL            string `json:"chat_url"`
}

// PublicPersonasResult is twin_list_public_personas's tool result.
type PublicPersonasResult struct {
	Personas []PersonaSummary `json:"personas"`
}

// ListPublicPersonas calls twin's /public-personas endpoint.
func (c *Client) ListPublicPersonas(ctx context.Context) (*PublicPersonasResult, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+"/public-personas", nil)
	if err != nil {
		return nil, fmt.Errorf("twin: building /public-personas request: %w", err)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("twin: calling /public-personas: %w", err)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("twin: reading /public-personas response: %w", err)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("twin: /public-personas returned %d: %s", resp.StatusCode, truncate(respBody, 300))
	}

	var out PublicPersonasResult
	if err := json.Unmarshal(respBody, &out); err != nil {
		return nil, fmt.Errorf("twin: decoding /public-personas response: %w", err)
	}
	return &out, nil
}

func truncate(b []byte, n int) string {
	if len(b) <= n {
		return string(b)
	}
	return string(b[:n]) + "...(truncated)"
}

// Register adds twin_chat and twin_list_public_personas to reg as
// read-only tools backed by client.
func Register(reg *registry.Registry, client *Client) error {
	if err := reg.Register(&registry.Definition{
		Name: "twin_chat",
		Description: "Chat with a twin persona by id. Repeated calls from the " +
			"same gateway user against the same twin continue the same conversation.",
		Tier: registry.TierReadOnly,
		Handler: func(ctx context.Context, userID string, args map[string]any) (any, error) {
			twinID, _ := args["twin_id"].(string)
			message, _ := args["message"].(string)
			if twinID == "" {
				return nil, fmt.Errorf("twin_chat: twin_id is required")
			}
			if message == "" {
				return nil, fmt.Errorf("twin_chat: message is required")
			}
			return client.Chat(ctx, userID, twinID, message)
		},
	}); err != nil {
		return err
	}

	return reg.Register(&registry.Definition{
		Name:        "twin_list_public_personas",
		Description: "List twin's available public personas.",
		Tier:        registry.TierReadOnly,
		Handler: func(ctx context.Context, _ string, _ map[string]any) (any, error) {
			return client.ListPublicPersonas(ctx)
		},
	})
}
