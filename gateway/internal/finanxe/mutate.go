package finanxe

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/siddharthshankar/sutra/gateway/internal/registry"
)

// --- finanxe_set_debt_funding -----------------------------------------
//
// finanxe's real, agent-facing name-based resolution
// (set_debt_funding_by_name in app.py) only exists inside finanxe's own
// in-process agent chat loop — it is not a REST endpoint. The plain
// POST /api/debt/funding route takes a raw debt id, not a name. To keep
// this tool's voice-friendly (debt_name, account_text) signature (per
// design.md's decision, written before that gap was found), this adapter
// ports finanxe's own matching logic — same debt-name matching, same
// account-nickname aliases and token-overlap scoring — and then calls the
// real route with the resolved debt id.

var bankAliases = map[string]string{
	"bofa":   "bank of america",
	"boa":    "bank of america",
	"amex":   "american express",
	"b of a": "bank of america",
}

type debtRecord struct {
	ID   string `json:"id"`
	Name string `json:"name"`
}

type debtsRawResult struct {
	Debts          []debtRecord `json:"debts"`
	AccountOptions []string     `json:"account_options"`
}

// SetDebtFundingResult mirrors set_debt_funding_by_name's return shape.
type SetDebtFundingResult struct {
	Set                  bool   `json:"set"`
	Debt                 string `json:"debt,omitempty"`
	FundingAccount       string `json:"funding_account,omitempty"`
	MatchedLinkedAccount bool   `json:"matched_linked_account,omitempty"`
	Note                 string `json:"note"`
}

func matchDebtByName(debts []debtRecord, debtName string) *debtRecord {
	q := strings.ToLower(strings.TrimSpace(debtName))
	for _, d := range debts {
		if strings.ToLower(d.Name) == q {
			return &d
		}
	}
	if q != "" {
		for _, d := range debts {
			if strings.Contains(strings.ToLower(d.Name), q) {
				return &d
			}
		}
		for _, d := range debts {
			if strings.Contains(q, strings.ToLower(d.Name)) {
				return &d
			}
		}
	}
	return nil
}

func accountTokens(s string) map[string]struct{} {
	set := make(map[string]struct{})
	for _, w := range strings.Fields(strings.ReplaceAll(strings.ToLower(s), "··", " ")) {
		if len(w) > 2 {
			set[w] = struct{}{}
		}
	}
	return set
}

func resolveFundingAccount(options []string, accountText string) (label string, matched bool) {
	at := strings.TrimSpace(accountText)
	atl := strings.ToLower(at)
	for short, full := range bankAliases {
		if strings.Contains(atl, short) {
			atl += " " + full
		}
	}

	var digits strings.Builder
	for _, ch := range atl {
		if ch >= '0' && ch <= '9' {
			digits.WriteRune(ch)
		}
	}
	if d := digits.String(); len(d) >= 3 {
		for _, o := range options {
			if strings.Contains(o, d) {
				return o, true
			}
		}
	}

	qWords := accountTokens(atl)
	bestScore, bestOption := 0, ""
	for _, o := range options {
		score := 0
		for w := range accountTokens(o) {
			if _, ok := qWords[w]; ok {
				score++
			}
		}
		if score > bestScore {
			bestScore, bestOption = score, o
		}
	}
	if bestScore > 0 {
		return bestOption, true
	}
	return at, false
}

// SetDebtFunding resolves debtName and accountText against finanxe's
// current debts and account options (mirroring set_debt_funding_by_name's
// matching rules), then calls POST /api/debt/funding with the resolved
// debt id. A debt name that matches nothing is a soft, non-error result
// (Set: false, with a Note listing known debts) — matching finanxe's own
// agent-facing contract, not a Go error, since it isn't a finanxe/HTTP
// failure.
func (c *Client) SetDebtFunding(ctx context.Context, debtName, accountText string) (*SetDebtFundingResult, error) {
	body, err := c.get(ctx, "/api/debts")
	if err != nil {
		return nil, err
	}
	var debts debtsRawResult
	if err := json.Unmarshal(body, &debts); err != nil {
		return nil, fmt.Errorf("finanxe: decoding /api/debts response: %w", err)
	}

	match := matchDebtByName(debts.Debts, debtName)
	if match == nil {
		names := "none"
		if len(debts.Debts) > 0 {
			parts := make([]string, len(debts.Debts))
			for i, d := range debts.Debts {
				parts[i] = d.Name
			}
			names = strings.Join(parts, ", ")
		}
		return &SetDebtFundingResult{
			Set:  false,
			Note: fmt.Sprintf("Couldn't find a debt matching %q. Debts: %s.", debtName, names),
		}, nil
	}

	resolved, matched := resolveFundingAccount(debts.AccountOptions, accountText)

	respBody, err := c.postJSON(ctx, "/api/debt/funding", map[string]any{
		"id":              match.ID,
		"funding_account": resolved,
	})
	if err != nil {
		return nil, err
	}
	var resp struct {
		Status string `json:"status"`
	}
	if err := json.Unmarshal(respBody, &resp); err != nil {
		return nil, fmt.Errorf("finanxe: decoding /api/debt/funding response: %w", err)
	}
	if resp.Status != "updated" {
		return nil, fmt.Errorf("finanxe: /api/debt/funding did not update debt %q (status %q)", match.ID, resp.Status)
	}

	return &SetDebtFundingResult{
		Set:                  true,
		Debt:                 match.Name,
		FundingAccount:       resolved,
		MatchedLinkedAccount: matched,
		Note:                 fmt.Sprintf("Got it — %s is paid from %s.", match.Name, resolved),
	}, nil
}

func describeSetDebtFunding(args map[string]any) string {
	return fmt.Sprintf("Redirect funding for debt %q to account %q.", argString(args, "debt_name"), argString(args, "account_text"))
}

// --- finanxe_create_goal ------------------------------------------------

// CreateGoalResult is finanxe_create_goal's tool result, mirroring
// /api/goals/add's response shape unmodified.
type CreateGoalResult struct {
	Status string         `json:"status"`
	Goal   map[string]any `json:"goal"`
}

// CreateGoal calls finanxe's POST /api/goals/add.
func (c *Client) CreateGoal(ctx context.Context, goalType, description string, targetValue *float64, targetDate, reference string) (*CreateGoalResult, error) {
	payload := map[string]any{
		"goal_type":   goalType,
		"description": description,
	}
	if targetValue != nil {
		payload["target_value"] = *targetValue
	}
	if targetDate != "" {
		payload["target_date"] = targetDate
	}
	if reference != "" {
		payload["reference"] = reference
	}

	body, err := c.postJSON(ctx, "/api/goals/add", payload)
	if err != nil {
		return nil, err
	}
	var out CreateGoalResult
	if err := json.Unmarshal(body, &out); err != nil {
		return nil, fmt.Errorf("finanxe: decoding /api/goals/add response: %w", err)
	}
	return &out, nil
}

func describeCreateGoal(args map[string]any) string {
	return fmt.Sprintf("Create a %s goal: %s.", argString(args, "goal_type"), argString(args, "description"))
}

// --- finanxe_add_calendar_event -----------------------------------------

// AddCalendarEventResult is finanxe_add_calendar_event's tool result,
// mirroring /api/calendar/event's response shape unmodified.
type AddCalendarEventResult struct {
	Status string `json:"status"`
	ID     string `json:"id"`
}

// AddCalendarEvent calls finanxe's POST /api/calendar/event. detail may be
// empty (finanxe's own default for an omitted detail).
func (c *Client) AddCalendarEvent(ctx context.Context, title, eventDate, detail string) (*AddCalendarEventResult, error) {
	payload := map[string]any{
		"title": title,
		"date":  eventDate,
	}
	if detail != "" {
		payload["detail"] = detail
	}

	body, err := c.postJSON(ctx, "/api/calendar/event", payload)
	if err != nil {
		return nil, err
	}
	var out AddCalendarEventResult
	if err := json.Unmarshal(body, &out); err != nil {
		return nil, fmt.Errorf("finanxe: decoding /api/calendar/event response: %w", err)
	}
	return &out, nil
}

func describeAddCalendarEvent(args map[string]any) string {
	return fmt.Sprintf("Add calendar event %q on %s.", argString(args, "title"), argString(args, "event_date"))
}

// argString extracts a string argument, returning "" for a missing or
// non-string value rather than panicking — args is untrusted MCP client
// input.
func argString(args map[string]any, key string) string {
	s, _ := args[key].(string)
	return s
}

func argFloatPtr(args map[string]any, key string) *float64 {
	switch v := args[key].(type) {
	case float64:
		return &v
	default:
		return nil
	}
}

// RegisterMutating adds finanxe_set_debt_funding, finanxe_create_goal, and
// finanxe_add_calendar_event to reg as confirm-first tools backed by
// client. None execute on the initial call — gateway-core's confirmation
// flow only invokes Handler once a returned pending id is confirmed.
func RegisterMutating(reg *registry.Registry, client *Client) error {
	tools := []*registry.Definition{
		{
			Name:        "finanxe_set_debt_funding",
			Description: "Redirect which account a debt is paid from, by debt name and account description. Requires confirmation.",
			Tier:        registry.TierConfirmFirst,
			SecretArgs:  []string{},
			Describe:    describeSetDebtFunding,
			Handler: func(ctx context.Context, _ string, args map[string]any) (any, error) {
				debtName := argString(args, "debt_name")
				accountText := argString(args, "account_text")
				if debtName == "" {
					return nil, fmt.Errorf("finanxe_set_debt_funding: debt_name is required")
				}
				if accountText == "" {
					return nil, fmt.Errorf("finanxe_set_debt_funding: account_text is required")
				}
				return client.SetDebtFunding(ctx, debtName, accountText)
			},
		},
		{
			Name:        "finanxe_create_goal",
			Description: "Create a new tracked financial goal. Requires confirmation.",
			Tier:        registry.TierConfirmFirst,
			SecretArgs:  []string{},
			Describe:    describeCreateGoal,
			Handler: func(ctx context.Context, _ string, args map[string]any) (any, error) {
				goalType := argString(args, "goal_type")
				description := argString(args, "description")
				if goalType == "" {
					return nil, fmt.Errorf("finanxe_create_goal: goal_type is required")
				}
				if description == "" {
					return nil, fmt.Errorf("finanxe_create_goal: description is required")
				}
				return client.CreateGoal(ctx, goalType, description, argFloatPtr(args, "target_value"), argString(args, "target_date"), argString(args, "reference"))
			},
		},
		{
			Name:        "finanxe_add_calendar_event",
			Description: "Add an event to the user's money calendar. Requires confirmation.",
			Tier:        registry.TierConfirmFirst,
			SecretArgs:  []string{},
			Describe:    describeAddCalendarEvent,
			Handler: func(ctx context.Context, _ string, args map[string]any) (any, error) {
				title := argString(args, "title")
				eventDate := argString(args, "event_date")
				if title == "" {
					return nil, fmt.Errorf("finanxe_add_calendar_event: title is required")
				}
				if eventDate == "" {
					return nil, fmt.Errorf("finanxe_add_calendar_event: event_date is required")
				}
				return client.AddCalendarEvent(ctx, title, eventDate, argString(args, "detail"))
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
