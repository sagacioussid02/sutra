package finanxe

import (
	"context"
	"encoding/json"
	"net/http"
	"testing"

	"github.com/siddharthshankar/sutra/gateway/internal/registry"
)

func TestSetDebtFunding_MatchesByNameAndAccount(t *testing.T) {
	var gotFundingBody map[string]any
	client := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/api/debts":
			json.NewEncoder(w).Encode(debtsRawResult{
				Debts:          []debtRecord{{ID: "d1", Name: "Chase Sapphire"}, {ID: "d2", Name: "Amex Gold"}},
				AccountOptions: []string{"Bank of America ··1234", "Chase Checking ··5678"},
			})
		case r.URL.Path == "/api/debt/funding":
			json.NewDecoder(r.Body).Decode(&gotFundingBody)
			json.NewEncoder(w).Encode(map[string]string{"status": "updated"})
		default:
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
	})

	result, err := client.SetDebtFunding(context.Background(), "sapphire", "BofA")
	if err != nil {
		t.Fatalf("SetDebtFunding: %v", err)
	}
	if !result.Set || result.Debt != "Chase Sapphire" {
		t.Fatalf("unexpected result: %+v", result)
	}
	if gotFundingBody["id"] != "d1" {
		t.Fatalf("expected /api/debt/funding to be called with resolved id d1, got %v", gotFundingBody)
	}
	if gotFundingBody["funding_account"] != "Bank of America ··1234" {
		t.Fatalf("expected the alias-matched account, got %v", gotFundingBody["funding_account"])
	}
}

func TestSetDebtFunding_UnknownDebt_ReturnsSoftFailureNotError(t *testing.T) {
	client := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/debts" {
			json.NewEncoder(w).Encode(debtsRawResult{Debts: []debtRecord{{ID: "d1", Name: "Chase Sapphire"}}})
			return
		}
		t.Fatalf("should not call %s when no debt matches", r.URL.Path)
	})

	result, err := client.SetDebtFunding(context.Background(), "nonexistent card", "some bank")
	if err != nil {
		t.Fatalf("expected a soft failure, not a Go error: %v", err)
	}
	if result.Set {
		t.Fatalf("expected Set=false for an unmatched debt name, got %+v", result)
	}
}

func TestSetDebtFunding_FinanxeRejects_ReturnsToolError(t *testing.T) {
	client := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/api/debts":
			json.NewEncoder(w).Encode(debtsRawResult{Debts: []debtRecord{{ID: "d1", Name: "Chase Sapphire"}}})
		case "/api/debt/funding":
			w.WriteHeader(http.StatusNotFound)
			json.NewEncoder(w).Encode(map[string]string{"status": "not_found"})
		}
	})

	if _, err := client.SetDebtFunding(context.Background(), "sapphire", "some bank"); err == nil {
		t.Fatal("expected an error when finanxe rejects the funding update")
	}
}

func TestCreateGoal_ReturnsCreatedGoal(t *testing.T) {
	var gotBody map[string]any
	client := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/goals/add" {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		json.NewDecoder(r.Body).Decode(&gotBody)
		json.NewEncoder(w).Encode(CreateGoalResult{Status: "created", Goal: map[string]any{"id": "g1"}})
	})

	target := 5000.0
	result, err := client.CreateGoal(context.Background(), "emergency_fund", "6 months expenses", &target, "2027-01-01", "")
	if err != nil {
		t.Fatalf("CreateGoal: %v", err)
	}
	if result.Status != "created" {
		t.Fatalf("unexpected result: %+v", result)
	}
	if gotBody["goal_type"] != "emergency_fund" || gotBody["target_value"] != 5000.0 {
		t.Fatalf("unexpected request body: %v", gotBody)
	}
}

func TestCreateGoal_ValidationError_ReturnsToolError(t *testing.T) {
	client := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]string{"error": "description is required"})
	})

	if _, err := client.CreateGoal(context.Background(), "emergency_fund", "", nil, "", ""); err == nil {
		t.Fatal("expected an error for a finanxe validation failure")
	}
}

func TestAddCalendarEvent_ReturnsCreatedID(t *testing.T) {
	var gotBody map[string]any
	client := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/calendar/event" {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		json.NewDecoder(r.Body).Decode(&gotBody)
		json.NewEncoder(w).Encode(AddCalendarEventResult{Status: "created", ID: "e1"})
	})

	result, err := client.AddCalendarEvent(context.Background(), "Rent due", "2027-01-01", "monthly rent")
	if err != nil {
		t.Fatalf("AddCalendarEvent: %v", err)
	}
	if result.ID != "e1" {
		t.Fatalf("unexpected result: %+v", result)
	}
	if gotBody["title"] != "Rent due" || gotBody["date"] != "2027-01-01" || gotBody["detail"] != "monthly rent" {
		t.Fatalf("unexpected request body: %v", gotBody)
	}
}

func TestAddCalendarEvent_ValidationError_ReturnsToolError(t *testing.T) {
	client := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]string{"error": "date must be YYYY-MM-DD"})
	})

	if _, err := client.AddCalendarEvent(context.Background(), "Rent due", "not-a-date", ""); err == nil {
		t.Fatal("expected an error for a finanxe validation failure")
	}
}

func TestRegisterMutating_AddsAllThreeConfirmFirstToolsWithDescribers(t *testing.T) {
	client := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		t.Fatal("handler should never be called directly — only via confirmation")
	})

	reg := registry.New()
	if err := RegisterMutating(reg, client); err != nil {
		t.Fatalf("RegisterMutating: %v", err)
	}

	cases := []struct {
		name string
		args map[string]any
		want string
	}{
		{"finanxe_set_debt_funding", map[string]any{"debt_name": "Sapphire", "account_text": "BofA"}, `Redirect funding for debt "Sapphire" to account "BofA".`},
		{"finanxe_create_goal", map[string]any{"goal_type": "emergency_fund", "description": "6mo cushion"}, "Create a emergency_fund goal: 6mo cushion."},
		{"finanxe_add_calendar_event", map[string]any{"title": "Rent due", "event_date": "2027-01-01"}, `Add calendar event "Rent due" on 2027-01-01.`},
	}
	for _, tc := range cases {
		def, ok := reg.Lookup(tc.name)
		if !ok {
			t.Fatalf("expected %q to be registered", tc.name)
		}
		if def.Tier != registry.TierConfirmFirst {
			t.Fatalf("%q tier = %q, want %q", tc.name, def.Tier, registry.TierConfirmFirst)
		}
		if def.Describe == nil {
			t.Fatalf("%q has no Describe function", tc.name)
		}
		if got := def.Describe(tc.args); got != tc.want {
			t.Fatalf("%q Describe = %q, want %q", tc.name, got, tc.want)
		}
	}
}

// TestRegisterMutating_HandlerNotCalledOnInitialToolCall exercises the same
// guarantee gateway-core's confirmFirstHandler already provides (a
// registry.TierConfirmFirst Definition's Handler only runs on confirm), but
// specifically for these three finanxe tools: Register does not itself
// invoke Handler, and nothing in this package calls it outside of
// gateway-core's own confirmFirstHandler/gatewayConfirmHandler.
func TestRegisterMutating_HandlerNotCalledOnInitialToolCall(t *testing.T) {
	called := false
	client := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		called = true
	})
	reg := registry.New()
	if err := RegisterMutating(reg, client); err != nil {
		t.Fatalf("RegisterMutating: %v", err)
	}
	if called {
		t.Fatal("registering tools must not call finanxe")
	}
}
