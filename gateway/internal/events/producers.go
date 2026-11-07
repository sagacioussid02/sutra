package events

import (
	"crypto/subtle"
	"fmt"
	"os"
	"sync"
	"time"

	"gopkg.in/yaml.v3"
)

// Producer is one registered event producer. Registration is configuration,
// not code: its own bearer token, the kinds it may emit, a rate limit, and
// the user its events belong to.
type Producer struct {
	ID          string   `yaml:"id"`
	Token       string   `yaml:"token"`
	Owner       string   `yaml:"owner"`
	Kinds       []string `yaml:"kinds"`
	RatePerHour int      `yaml:"rate_per_hour"`
}

// Config is the gitignored events.yaml.
type Config struct {
	ForwardURL    string     `yaml:"forward_url"`
	ForwardSecret string     `yaml:"forward_secret"`
	Producers     []Producer `yaml:"producers"`
}

// LoadConfig reads events.yaml. A missing file means the intake is off.
func LoadConfig(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if os.IsNotExist(err) {
		return &Config{}, nil
	}
	if err != nil {
		return nil, fmt.Errorf("events: reading %s: %w", path, err)
	}
	var c Config
	if err := yaml.Unmarshal(data, &c); err != nil {
		return nil, fmt.Errorf("events: parsing %s: %w", path, err)
	}
	return &c, c.validate(path)
}

func (c *Config) validate(path string) error {
	if len(c.Producers) == 0 {
		return nil
	}
	if c.ForwardURL == "" || c.ForwardSecret == "" {
		return fmt.Errorf("events: %s needs forward_url and forward_secret", path)
	}
	reg, err := LoadRegistry()
	if err != nil {
		return err
	}
	seen := map[string]bool{}
	for _, p := range c.Producers {
		if p.ID == "" || p.Token == "" || p.Owner == "" || len(p.Kinds) == 0 {
			return fmt.Errorf("events: %s: producer %q needs id, token, owner and kinds", path, p.ID)
		}
		if seen[p.Token] {
			return fmt.Errorf("events: %s: producer %q reuses another producer's token", path, p.ID)
		}
		seen[p.Token] = true
		for _, k := range p.Kinds {
			if _, ok := reg[k]; !ok {
				return fmt.Errorf("events: %s: producer %q lists unknown kind %q", path, p.ID, k)
			}
		}
	}
	return nil
}

// find returns the producer whose token matches, comparing in constant time.
func (c *Config) find(token string) *Producer {
	var found *Producer
	for i := range c.Producers {
		if subtle.ConstantTimeCompare([]byte(c.Producers[i].Token), []byte(token)) == 1 {
			found = &c.Producers[i]
		}
	}
	return found
}

func (p *Producer) allows(kind string) bool { return contains(p.Kinds, kind) }

// limiter is a per-producer sliding one-hour window.
type limiter struct {
	mu   sync.Mutex
	hits map[string][]time.Time
}

func newLimiter() *limiter { return &limiter{hits: map[string][]time.Time{}} }

// allow records a hit and reports whether the producer is within its rate.
// A producer with no configured rate gets a conservative default.
func (l *limiter) allow(id string, perHour int, now time.Time) bool {
	if perHour <= 0 {
		perHour = 60
	}
	l.mu.Lock()
	defer l.mu.Unlock()
	cutoff := now.Add(-time.Hour)
	kept := l.hits[id][:0]
	for _, t := range l.hits[id] {
		if t.After(cutoff) {
			kept = append(kept, t)
		}
	}
	if len(kept) >= perHour {
		l.hits[id] = kept
		return false
	}
	l.hits[id] = append(kept, now)
	return true
}
