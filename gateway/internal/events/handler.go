package events

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/siddharthshankar/sutra/gateway/internal/audit"
)

// Auditor is the slice of the audit store the intake needs.
type Auditor interface {
	Write(ctx context.Context, e audit.Entry) error
}

// Handler is the producer-facing intake route: POST /events.
type Handler struct {
	cfg     *Config
	reg     Registry
	audit   Auditor
	client  *http.Client
	limiter *limiter
	now     func() time.Time
}

// NewHandler builds the intake. A config with no producers rejects everything.
func NewHandler(cfg *Config, a Auditor) (*Handler, error) {
	reg, err := LoadRegistry()
	if err != nil {
		return nil, err
	}
	return &Handler{
		cfg: cfg, reg: reg, audit: a, limiter: newLimiter(), now: time.Now,
		client: &http.Client{Timeout: 5 * time.Second},
	}, nil
}

func (h *Handler) record(ctx context.Context, user, kind, status, summary string) {
	_ = h.audit.Write(ctx, audit.Entry{
		UserID: user, ToolName: "event:" + kind, Tier: "event", Status: status, ResultSummary: summary,
	})
}

func (h *Handler) fail(w http.ResponseWriter, code int, msg string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(map[string]string{"error": msg})
}

func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	if r.Method != http.MethodPost {
		h.fail(w, http.StatusMethodNotAllowed, "POST only")
		return
	}
	token := strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
	producer := h.cfg.find(token)
	if producer == nil || token == "" {
		h.record(ctx, "unknown-producer", "-", audit.StatusDenied, "unregistered producer")
		h.fail(w, http.StatusUnauthorized, "unregistered producer")
		return
	}
	body, err := io.ReadAll(io.LimitReader(r.Body, 8*1024))
	var sub Submission
	if err == nil {
		dec := json.NewDecoder(bytes.NewReader(body))
		dec.DisallowUnknownFields() // the envelope has no field for approvals, tiers or priority
		err = dec.Decode(&sub)
	}
	if err != nil {
		h.record(ctx, producer.ID, "-", audit.StatusDenied, "malformed event")
		h.fail(w, http.StatusBadRequest, "malformed event")
		return
	}
	if !producer.allows(sub.Kind) {
		h.record(ctx, producer.ID, sub.Kind, audit.StatusDenied, "kind not registered for this producer")
		h.fail(w, http.StatusForbidden, "this producer may not emit that kind")
		return
	}
	now := h.now()
	if !h.limiter.allow(producer.ID, producer.RatePerHour, now) {
		h.record(ctx, producer.ID, sub.Kind, audit.StatusDenied, "rate limit exceeded")
		h.fail(w, http.StatusTooManyRequests, "rate limit exceeded")
		return
	}
	env, err := h.reg.Build(producer.ID, producer.Owner, sub, now)
	if err != nil {
		h.record(ctx, producer.ID, sub.Kind, audit.StatusDenied, err.Error())
		h.fail(w, http.StatusBadRequest, err.Error())
		return
	}
	if err := h.forward(ctx, env); err != nil {
		h.record(ctx, producer.ID, sub.Kind, audit.StatusError, "orchestrator unavailable: "+err.Error())
		w.Header().Set("Retry-After", "30")
		h.fail(w, http.StatusServiceUnavailable, "orchestrator unavailable, retry later")
		return
	}
	h.record(ctx, producer.ID, sub.Kind, audit.StatusExecuted, "accepted "+env.ID)
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusAccepted)
	_ = json.NewEncoder(w).Encode(map[string]string{"id": env.ID})
}

// forward hands the envelope to the orchestrator's event log. The gateway
// stores nothing: a down orchestrator is a retryable error for the producer.
func (h *Handler) forward(ctx context.Context, env Envelope) error {
	data, err := json.Marshal(env)
	if err != nil {
		return err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, h.cfg.ForwardURL, bytes.NewReader(data))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Sutra-Forward-Secret", h.cfg.ForwardSecret)
	resp, err := h.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode/100 != 2 {
		return fmt.Errorf("orchestrator answered %d", resp.StatusCode)
	}
	return nil
}
