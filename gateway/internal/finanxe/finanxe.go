// Package finanxe adapts finanxe's existing local HTTP API
// (127.0.0.1:8002) into tools for the gateway's registry: read-only tools
// (finanxe.go, mcp-tools-finanxe-readonly) and confirm-first mutating tools
// (mutate.go, mcp-tools-finanxe-confirm). It calls finanxe's already-running
// stdlib http.server process and never modifies finanxe's own code.
//
// finanxe has no auth of its own and no real multi-user support today —
// every endpoint takes a user_id parameter that defaults to "default_user"
// — so this adapter maps every gateway-authorized caller to one configured
// finanxe user id (see design.md's mcp-tools-finanxe-readonly decision)
// rather than inventing multi-user support finanxe doesn't have.
//
// This package intentionally never calls any /api/plaid/* route, at any
// tier — Plaid routes are never exposed as a gateway tool in Phase 1.
package finanxe

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/siddharthshankar/sutra/gateway/internal/registry"
)

const defaultTimeout = 10 * time.Second

// DefaultUserID is the finanxe user id every gateway caller maps to when
// none is configured, matching finanxe's own "default_user" fallback.
const DefaultUserID = "default_user"

// Config configures a Client.
type Config struct {
	// BaseURL is finanxe's local API base URL, normally
	// http://127.0.0.1:8002.
	BaseURL string
	// UserID is the finanxe user id every gateway caller is mapped to.
	// Defaults to DefaultUserID if empty.
	UserID string
	// HTTPClient overrides the default client (used by tests to point at
	// an httptest.Server, and to set a shorter timeout).
	HTTPClient *http.Client
}

// Client calls finanxe's local HTTP API.
type Client struct {
	baseURL    string
	userID     string
	httpClient *http.Client
}

// NewClient builds a Client from cfg.
func NewClient(cfg Config) *Client {
	httpClient := cfg.HTTPClient
	if httpClient == nil {
		httpClient = &http.Client{Timeout: defaultTimeout}
	}
	userID := cfg.UserID
	if userID == "" {
		userID = DefaultUserID
	}
	return &Client{
		baseURL:    strings.TrimRight(cfg.BaseURL, "/"),
		userID:     userID,
		httpClient: httpClient,
	}
}

// get issues a GET to path (e.g. "/api/snapshot") with the configured
// user_id query parameter, and returns the raw response body on a 200. Any
// other outcome (connection failure, timeout, non-200 status) is returned
// as a wrapped, tool-level error — never a panic.
func (c *Client) get(ctx context.Context, path string) ([]byte, error) {
	u := c.baseURL + path + "?user_id=" + url.QueryEscape(c.userID)

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return nil, fmt.Errorf("finanxe: building %s request: %w", path, err)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("finanxe: calling %s (is finanxe running on %s?): %w", path, c.baseURL, err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("finanxe: reading %s response: %w", path, err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("finanxe: %s returned %d: %s", path, resp.StatusCode, truncate(body, 300))
	}
	return body, nil
}

// postJSON issues a POST to path with body JSON-encoded from payload (with
// user_id merged in, matching finanxe's do_POST which reads it from the
// request body rather than a query param). Like get, any outcome other
// than a 200 — connection failure, timeout, or a non-200 status — is
// returned as a wrapped, tool-level error carrying finanxe's own error
// message when there is one, never a panic.
func (c *Client) postJSON(ctx context.Context, path string, payload map[string]any) ([]byte, error) {
	payload["user_id"] = c.userID
	encoded, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("finanxe: encoding %s request: %w", path, err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+path, strings.NewReader(string(encoded)))
	if err != nil {
		return nil, fmt.Errorf("finanxe: building %s request: %w", path, err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("finanxe: calling %s (is finanxe running on %s?): %w", path, c.baseURL, err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("finanxe: reading %s response: %w", path, err)
	}

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusCreated {
		return nil, fmt.Errorf("finanxe: %s returned %d: %s", path, resp.StatusCode, truncate(body, 300))
	}
	return body, nil
}

func truncate(b []byte, n int) string {
	if len(b) <= n {
		return string(b)
	}
	return string(b[:n]) + "...(truncated)"
}

// Snapshot is finanxe_get_snapshot's tool result, mirroring /api/snapshot's
// response shape unmodified.
type Snapshot struct {
	CashPosition         float64  `json:"cash_position"`
	MonthlyIncome        float64  `json:"monthly_income"`
	TotalDebt            float64  `json:"total_debt"`
	TotalMinimums        float64  `json:"total_minimums"`
	TotalMonthlyInterest float64  `json:"total_monthly_interest"`
	DebtToIncome         float64  `json:"debt_to_income"`
	NetAvailable         float64  `json:"net_available"`
	Strengths            []string `json:"strengths"`
	WeakPoints           []string `json:"weak_points"`
	StressFactors        []string `json:"stress_factors"`
}

// GetSnapshot calls finanxe's GET /api/snapshot.
func (c *Client) GetSnapshot(ctx context.Context) (*Snapshot, error) {
	body, err := c.get(ctx, "/api/snapshot")
	if err != nil {
		return nil, err
	}
	var out Snapshot
	if err := json.Unmarshal(body, &out); err != nil {
		return nil, fmt.Errorf("finanxe: decoding /api/snapshot response: %w", err)
	}
	return &out, nil
}

// DebtsResult is finanxe_list_debts's tool result, mirroring /api/debts's
// response shape unmodified.
type DebtsResult struct {
	Debts          []map[string]any `json:"debts"`
	AccountOptions []map[string]any `json:"account_options"`
}

// ListDebts calls finanxe's GET /api/debts.
func (c *Client) ListDebts(ctx context.Context) (*DebtsResult, error) {
	body, err := c.get(ctx, "/api/debts")
	if err != nil {
		return nil, err
	}
	var out DebtsResult
	if err := json.Unmarshal(body, &out); err != nil {
		return nil, fmt.Errorf("finanxe: decoding /api/debts response: %w", err)
	}
	return &out, nil
}

// CalendarResult is finanxe_get_calendar's tool result, mirroring
// /api/calendar's response shape unmodified.
type CalendarResult map[string]any

// GetCalendar calls finanxe's GET /api/calendar.
func (c *Client) GetCalendar(ctx context.Context) (CalendarResult, error) {
	body, err := c.get(ctx, "/api/calendar")
	if err != nil {
		return nil, err
	}
	var out CalendarResult
	if err := json.Unmarshal(body, &out); err != nil {
		return nil, fmt.Errorf("finanxe: decoding /api/calendar response: %w", err)
	}
	return out, nil
}

// GoalsResult is finanxe_list_goals's tool result, mirroring /api/goals's
// response shape unmodified.
type GoalsResult struct {
	Goals []map[string]any `json:"goals"`
}

// ListGoals calls finanxe's GET /api/goals.
func (c *Client) ListGoals(ctx context.Context) (*GoalsResult, error) {
	body, err := c.get(ctx, "/api/goals")
	if err != nil {
		return nil, err
	}
	var out GoalsResult
	if err := json.Unmarshal(body, &out); err != nil {
		return nil, fmt.Errorf("finanxe: decoding /api/goals response: %w", err)
	}
	return &out, nil
}

// Register adds finanxe_get_snapshot, finanxe_list_debts,
// finanxe_get_calendar, and finanxe_list_goals to reg as read-only tools
// backed by client. None declare secret args: none of these tools take
// financial-credential input, so redaction is a documented no-op here.
func Register(reg *registry.Registry, client *Client) error {
	tools := []*registry.Definition{
		{
			Name:        "finanxe_get_snapshot",
			Description: "Get the user's current financial snapshot (cash position, income, debt totals, debt-to-income ratio).",
			Tier:        registry.TierReadOnly,
			SecretArgs:  []string{},
			Handler: func(ctx context.Context, _ string, _ map[string]any) (any, error) {
				return client.GetSnapshot(ctx)
			},
		},
		{
			Name:        "finanxe_list_debts",
			Description: "List the user's debts and their available funding accounts.",
			Tier:        registry.TierReadOnly,
			SecretArgs:  []string{},
			Handler: func(ctx context.Context, _ string, _ map[string]any) (any, error) {
				return client.ListDebts(ctx)
			},
		},
		{
			Name:        "finanxe_get_calendar",
			Description: "Get the user's upcoming money calendar (bills, income, goal milestones).",
			Tier:        registry.TierReadOnly,
			SecretArgs:  []string{},
			Handler: func(ctx context.Context, _ string, _ map[string]any) (any, error) {
				return client.GetCalendar(ctx)
			},
		},
		{
			Name:        "finanxe_list_goals",
			Description: "List the user's tracked financial goals with progress.",
			Tier:        registry.TierReadOnly,
			SecretArgs:  []string{},
			Handler: func(ctx context.Context, _ string, _ map[string]any) (any, error) {
				return client.ListGoals(ctx)
			},
		},
	}
	for _, def := range tools {
		if err := reg.Register(def); err != nil {
			return err
		}
	}
	return nil
}
