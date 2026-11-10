// Package watch checks the health routes of the services Sutra depends on
// and decides when a change is worth a push notification. It is run once
// per invocation by cmd/sutra-watch (launchd starts it every few minutes),
// so everything it remembers between runs lives in a small JSON state file.
//
// States: up (2xx, and a JSON "status" of ok/healthy or none at all),
// degraded (2xx with a JSON "status" of degraded), down (anything else:
// connection refused, timeout, non-2xx). A target is only announced as down
// after FailThreshold consecutive failed checks, so one slow response
// doesn't page anyone. A recovery is announced only if the outage was.
package watch

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"gopkg.in/yaml.v3"
)

// State is a target's health as last seen.
type State string

const (
	StateUp       State = "up"
	StateDegraded State = "degraded"
	StateDown     State = "down"
)

// Target is one health route to check.
type Target struct {
	Name string `yaml:"name"`
	URL  string `yaml:"url"`
}

// NtfyConfig says where alerts go. The topic is read from the environment so
// the (public) repo and the config file never carry it: anyone who knows an
// ntfy topic can read its messages.
type NtfyConfig struct {
	Server   string `yaml:"server"`
	TopicEnv string `yaml:"topic_env"`
	TokenEnv string `yaml:"token_env"`
}

// Config is watch.yaml.
type Config struct {
	Ntfy          NtfyConfig `yaml:"ntfy"`
	FailThreshold int        `yaml:"fail_threshold"`
	Timeout       string     `yaml:"timeout"`
	Targets       []Target   `yaml:"targets"`
}

// LoadConfig reads and validates watch.yaml, filling defaults.
func LoadConfig(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("watch: reading %s: %w", path, err)
	}
	var c Config
	if err := yaml.Unmarshal(data, &c); err != nil {
		return nil, fmt.Errorf("watch: parsing %s: %w", path, err)
	}
	if c.Ntfy.Server == "" {
		c.Ntfy.Server = "https://ntfy.sh"
	}
	if c.Ntfy.TopicEnv == "" {
		c.Ntfy.TopicEnv = "SUTRA_WATCH_NTFY_TOPIC"
	}
	if c.FailThreshold <= 0 {
		c.FailThreshold = 2
	}
	if c.Timeout == "" {
		c.Timeout = "10s"
	}
	if _, err := time.ParseDuration(c.Timeout); err != nil {
		return nil, fmt.Errorf("watch: timeout %q: %w", c.Timeout, err)
	}
	seen := map[string]bool{}
	for _, t := range c.Targets {
		if t.Name == "" || t.URL == "" {
			return nil, fmt.Errorf("watch: every target needs a name and a url")
		}
		if !strings.HasPrefix(t.URL, "http://") && !strings.HasPrefix(t.URL, "https://") {
			return nil, fmt.Errorf("watch: target %q: url must be http(s)", t.Name)
		}
		if seen[t.Name] {
			return nil, fmt.Errorf("watch: duplicate target %q", t.Name)
		}
		seen[t.Name] = true
	}
	return &c, nil
}

// Result is the outcome of one check.
type Result struct {
	State  State
	Detail string // short, human-readable; never a response body dump
}

// Check probes one health URL.
func Check(ctx context.Context, client *http.Client, url string) Result {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return Result{StateDown, "bad url"}
	}
	resp, err := client.Do(req)
	if err != nil {
		return Result{StateDown, shortErr(err)}
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(io.LimitReader(resp.Body, 64<<10))
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return Result{StateDown, fmt.Sprintf("HTTP %d", resp.StatusCode)}
	}
	var payload struct {
		Status string `json:"status"`
	}
	if json.Unmarshal(body, &payload) == nil {
		switch strings.ToLower(payload.Status) {
		case "degraded", "warn", "warning":
			return Result{StateDegraded, "reports degraded"}
		case "", "ok", "healthy", "up", "pass":
		default:
			return Result{StateDown, "reports status " + truncate(payload.Status, 40)}
		}
	}
	return Result{StateUp, "ok"}
}

func shortErr(err error) string {
	switch {
	case errors.Is(err, context.DeadlineExceeded):
		return "timed out"
	case strings.Contains(err.Error(), "connection refused"):
		return "connection refused (not running?)"
	default:
		return truncate(err.Error(), 120)
	}
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "…"
}

// TargetState is what the state file remembers per target.
type TargetState struct {
	// Announced is the last state we told the user about (empty = never).
	Announced State `json:"announced"`
	// Failures counts consecutive down checks.
	Failures int       `json:"failures"`
	Since    time.Time `json:"since"`
}

// StateFile is the whole state file.
type StateFile map[string]TargetState

// LoadState reads the state file; a missing file is an empty state.
func LoadState(path string) (StateFile, error) {
	data, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		return StateFile{}, nil
	}
	if err != nil {
		return nil, err
	}
	s := StateFile{}
	if err := json.Unmarshal(data, &s); err != nil {
		// A corrupt state file must not stop the watcher; start fresh.
		return StateFile{}, nil
	}
	return s, nil
}

// SaveState writes the state file atomically.
func SaveState(path string, s StateFile) error {
	data, err := json.MarshalIndent(s, "", "  ")
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, data, 0o600); err != nil {
		return err
	}
	return os.Rename(tmp, path)
}

// Alert is one notification to send.
type Alert struct {
	Target   string
	State    State
	Detail   string
	Priority string // ntfy priority: "high" for down, "default" otherwise
}

// Title is the notification title.
func (a Alert) Title() string {
	switch a.State {
	case StateDown:
		return fmt.Sprintf("Sutra: %s is down", a.Target)
	case StateDegraded:
		return fmt.Sprintf("Sutra: %s is degraded", a.Target)
	default:
		return fmt.Sprintf("Sutra: %s is back up", a.Target)
	}
}

// Decide folds one check result into the target's remembered state and
// returns an alert when the user should hear about it.
func Decide(prev TargetState, r Result, threshold int, now time.Time) (TargetState, *Alert) {
	next := prev
	if r.State == StateDown {
		next.Failures++
	} else {
		next.Failures = 0
	}

	effective := r.State
	if r.State == StateDown && next.Failures < threshold {
		// Not yet confirmed down: hold whatever was announced before.
		return next, nil
	}

	announced := prev.Announced
	if announced == "" {
		announced = StateUp // first sight of a healthy target is not news
	}
	if effective == announced {
		if prev.Announced == "" {
			next.Announced = effective
			next.Since = now
		}
		return next, nil
	}

	next.Announced = effective
	next.Since = now
	prio := "default"
	if effective == StateDown {
		prio = "high"
	}
	return next, &Alert{Target: "", State: effective, Detail: r.Detail, Priority: prio}
}

// Notifier sends alerts.
type Notifier interface {
	Notify(ctx context.Context, a Alert) error
}

// Ntfy posts alerts to an ntfy topic.
type Ntfy struct {
	Server string
	Topic  string
	Token  string
	Client *http.Client
}

// Notify implements Notifier.
func (n Ntfy) Notify(ctx context.Context, a Alert) error {
	url := strings.TrimRight(n.Server, "/") + "/" + n.Topic
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, strings.NewReader(a.Detail))
	if err != nil {
		return err
	}
	req.Header.Set("Title", a.Title())
	req.Header.Set("Priority", a.Priority)
	req.Header.Set("Tags", "sutra,"+string(a.State))
	if n.Token != "" {
		req.Header.Set("Authorization", "Bearer "+n.Token)
	}
	resp, err := n.Client.Do(req)
	if err != nil {
		return fmt.Errorf("ntfy: %s", shortErr(err))
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("ntfy: HTTP %d", resp.StatusCode)
	}
	return nil
}

// Report is one target's line in a run's summary.
type Report struct {
	Target string
	Result Result
	Alert  *Alert
	Err    error // notification failure, if any
}

// Run checks every target once, updates state, and sends alerts. A failed
// notification leaves the target's announced state unchanged so the next
// run tries again.
func Run(ctx context.Context, cfg *Config, client *http.Client, state StateFile, n Notifier, now time.Time) []Report {
	timeout, _ := time.ParseDuration(cfg.Timeout)
	reports := make([]Report, 0, len(cfg.Targets))
	for _, t := range cfg.Targets {
		cctx, cancel := context.WithTimeout(ctx, timeout)
		r := Check(cctx, client, t.URL)
		cancel()

		prev := state[t.Name]
		next, alert := Decide(prev, r, cfg.FailThreshold, now)
		rep := Report{Target: t.Name, Result: r}
		if alert != nil {
			alert.Target = t.Name
			rep.Alert = alert
			if n != nil {
				if err := n.Notify(ctx, *alert); err != nil {
					rep.Err = err
					next.Announced = prev.Announced
					next.Since = prev.Since
				}
			}
		}
		state[t.Name] = next
		reports = append(reports, rep)
	}
	// Forget targets no longer configured.
	for name := range state {
		found := false
		for _, t := range cfg.Targets {
			if t.Name == name {
				found = true
				break
			}
		}
		if !found {
			delete(state, name)
		}
	}
	return reports
}
