package watch

import (
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

type recorder struct {
	mu     sync.Mutex
	alerts []Alert
	fail   bool
}

func (r *recorder) Notify(_ context.Context, a Alert) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.fail {
		return errTest
	}
	r.alerts = append(r.alerts, a)
	return nil
}

var errTest = &testErr{}

type testErr struct{}

func (*testErr) Error() string { return "boom" }

func TestCheck_States(t *testing.T) {
	cases := map[string]struct {
		code int
		body string
		want State
	}{
		"plain 200":      {200, "ok", StateUp},
		"status ok":      {200, `{"status":"ok"}`, StateUp},
		"status healthy": {200, `{"status":"healthy","x":1}`, StateUp},
		"degraded":       {200, `{"status":"degraded"}`, StateDegraded},
		"bad status":     {200, `{"status":"error"}`, StateDown},
		"500":            {500, `{"status":"ok"}`, StateDown},
	}
	for name, c := range cases {
		t.Run(name, func(t *testing.T) {
			ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
				w.WriteHeader(c.code)
				w.Write([]byte(c.body))
			}))
			defer ts.Close()
			if got := Check(context.Background(), ts.Client(), ts.URL).State; got != c.want {
				t.Fatalf("got %s, want %s", got, c.want)
			}
		})
	}
}

func TestCheck_RefusedIsDown(t *testing.T) {
	ts := httptest.NewServer(http.NotFoundHandler())
	url := ts.URL
	ts.Close()
	r := Check(context.Background(), http.DefaultClient, url)
	if r.State != StateDown || !strings.Contains(r.Detail, "refused") {
		t.Fatalf("got %+v", r)
	}
}

func TestDecide_DownNeedsThreshold_RecoveryAnnounced(t *testing.T) {
	now := time.Now()
	var s TargetState
	var a *Alert

	s, a = Decide(s, Result{StateUp, "ok"}, 2, now)
	if a != nil || s.Announced != StateUp {
		t.Fatalf("first healthy sight should be silent, got %+v %+v", s, a)
	}
	s, a = Decide(s, Result{StateDown, "timed out"}, 2, now)
	if a != nil {
		t.Fatal("one failure must not alert")
	}
	s, a = Decide(s, Result{StateDown, "timed out"}, 2, now)
	if a == nil || a.State != StateDown || a.Priority != "high" {
		t.Fatalf("second failure should alert down, got %+v", a)
	}
	s, a = Decide(s, Result{StateDown, "timed out"}, 2, now)
	if a != nil {
		t.Fatal("still down must not re-alert")
	}
	s, a = Decide(s, Result{StateUp, "ok"}, 2, now)
	if a == nil || a.State != StateUp {
		t.Fatalf("recovery should alert, got %+v", a)
	}
	if s.Failures != 0 {
		t.Fatal("failures not reset")
	}
}

func TestDecide_BlipIsSilent(t *testing.T) {
	now := time.Now()
	s, _ := Decide(TargetState{}, Result{StateUp, "ok"}, 2, now)
	s, a1 := Decide(s, Result{StateDown, "x"}, 2, now)
	_, a2 := Decide(s, Result{StateUp, "ok"}, 2, now)
	if a1 != nil || a2 != nil {
		t.Fatal("a single failed check followed by recovery should send nothing")
	}
}

func TestDecide_DegradedIsImmediate(t *testing.T) {
	s, _ := Decide(TargetState{}, Result{StateUp, "ok"}, 2, time.Now())
	_, a := Decide(s, Result{StateDegraded, "reports degraded"}, 2, time.Now())
	if a == nil || a.State != StateDegraded {
		t.Fatalf("got %+v", a)
	}
}

func TestRun_FailedNotifyRetriesNextRun(t *testing.T) {
	down := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(503)
	}))
	defer down.Close()
	cfg := &Config{FailThreshold: 1, Timeout: "2s", Targets: []Target{{Name: "finanxe", URL: down.URL}}}
	state := StateFile{"finanxe": {Announced: StateUp}, "removed": {Announced: StateDown}}

	n := &recorder{fail: true}
	reps := Run(context.Background(), cfg, down.Client(), state, n, time.Now())
	if reps[0].Err == nil || state["finanxe"].Announced != StateUp {
		t.Fatalf("failed notify must leave state unannounced: %+v %+v", reps[0], state["finanxe"])
	}
	if _, ok := state["removed"]; ok {
		t.Fatal("unconfigured target not dropped from state")
	}

	n.fail = false
	Run(context.Background(), cfg, down.Client(), state, n, time.Now())
	if len(n.alerts) != 1 || n.alerts[0].Target != "finanxe" || n.alerts[0].Title() != "Sutra: finanxe is down" {
		t.Fatalf("got %+v", n.alerts)
	}
}

func TestNtfy_PostsTitleAndPriority(t *testing.T) {
	var got *http.Request
	var body string
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		got = r
		b := make([]byte, 100)
		n, _ := r.Body.Read(b)
		body = string(b[:n])
	}))
	defer ts.Close()
	err := Ntfy{Server: ts.URL, Topic: "topic-x", Token: "tk", Client: ts.Client()}.Notify(context.Background(),
		Alert{Target: "spy-desk", State: StateDown, Detail: "connection refused", Priority: "high"})
	if err != nil {
		t.Fatal(err)
	}
	if got.URL.Path != "/topic-x" || got.Header.Get("Title") != "Sutra: spy-desk is down" ||
		got.Header.Get("Priority") != "high" || got.Header.Get("Authorization") != "Bearer tk" || body != "connection refused" {
		t.Fatalf("unexpected request: %s %v %q", got.URL.Path, got.Header, body)
	}
}

func TestStateRoundTrip_AndCorruptFile(t *testing.T) {
	p := filepath.Join(t.TempDir(), "sub", "state.json")
	if err := SaveState(p, StateFile{"a": {Announced: StateDown, Failures: 3}}); err != nil {
		t.Fatal(err)
	}
	s, err := LoadState(p)
	if err != nil || s["a"].Failures != 3 {
		t.Fatalf("round trip: %v %+v", err, s)
	}
	os.WriteFile(p, []byte("{not json"), 0o600)
	s, err = LoadState(p)
	if err != nil || len(s) != 0 {
		t.Fatal("corrupt state should start fresh")
	}
}

func TestLoadConfig_DefaultsAndValidation(t *testing.T) {
	dir := t.TempDir()
	p := filepath.Join(dir, "watch.yaml")
	os.WriteFile(p, []byte("targets:\n  - name: gateway\n    url: http://127.0.0.1:8765/healthz\n"), 0o600)
	c, err := LoadConfig(p)
	if err != nil {
		t.Fatal(err)
	}
	if c.FailThreshold != 2 || c.Ntfy.Server != "https://ntfy.sh" || c.Ntfy.TopicEnv != "SUTRA_WATCH_NTFY_TOPIC" {
		t.Fatalf("defaults: %+v", c)
	}
	for _, bad := range []string{
		"targets:\n  - name: a\n",
		"targets:\n  - name: a\n    url: ftp://x\n",
		"targets:\n  - name: a\n    url: http://x\n  - name: a\n    url: http://y\n",
	} {
		os.WriteFile(p, []byte(bad), 0o600)
		if _, err := LoadConfig(p); err == nil {
			t.Fatalf("expected error for %q", bad)
		}
	}
}
