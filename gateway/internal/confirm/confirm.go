// Package confirm implements the gateway's hold-and-confirm flow for
// confirm-first tools: calling such a tool creates a pending record here
// instead of executing anything; a separate, explicit confirmation is
// required to actually run it, and only the user who created the pending
// record, before it expires, exactly once, may do so.
package confirm

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"time"

	"github.com/google/uuid"
	_ "modernc.org/sqlite"
)

// Errors returned by Claim, distinguishing why a confirmation could not be
// executed.
var (
	ErrNotFound    = errors.New("confirm: pending confirmation not found")
	ErrForbidden   = errors.New("confirm: pending confirmation belongs to a different user")
	ErrExpired     = errors.New("confirm: pending confirmation has expired")
	ErrAlreadyUsed = errors.New("confirm: pending confirmation was already confirmed")
)

// Record is one pending (or resolved) confirmation.
type Record struct {
	ID          string
	UserID      string
	ToolName    string
	Args        map[string]any
	Description string
	CreatedAt   time.Time
	ExpiresAt   time.Time
	Status      string // "pending" or "executed"
}

// Store wraps a SQLite database holding the pending_confirmations table.
type Store struct {
	db  *sql.DB
	ttl time.Duration
}

// DefaultTTL is how long a pending confirmation remains executable if the
// caller does not specify one. Chosen per gateway-core's design.md as a
// starting point for a conversational (voice) round trip; tune once real
// usage is observed.
const DefaultTTL = 5 * time.Minute

// Open opens (creating if needed) the confirmation store at path.
func Open(path string, ttl time.Duration) (*Store, error) {
	if ttl <= 0 {
		ttl = DefaultTTL
	}
	db, err := sql.Open("sqlite", path)
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(1)

	const schema = `
CREATE TABLE IF NOT EXISTS pending_confirmations (
	id          TEXT PRIMARY KEY,
	user_id     TEXT NOT NULL,
	tool_name   TEXT NOT NULL,
	args_json   TEXT NOT NULL,
	description TEXT NOT NULL,
	created_at  TEXT NOT NULL,
	expires_at  TEXT NOT NULL,
	status      TEXT NOT NULL
);
`
	if _, err := db.Exec(schema); err != nil {
		db.Close()
		return nil, err
	}
	return &Store{db: db, ttl: ttl}, nil
}

// Close closes the underlying database.
func (s *Store) Close() error { return s.db.Close() }

// Create records a new pending confirmation for userID calling toolName
// with args, described by description. It does not execute anything.
func (s *Store) Create(ctx context.Context, userID, toolName string, args map[string]any, description string) (*Record, error) {
	id := uuid.NewString()
	now := time.Now().UTC()
	exp := now.Add(s.ttl)
	argsJSON, err := json.Marshal(args)
	if err != nil {
		return nil, err
	}
	_, err = s.db.ExecContext(ctx, `
INSERT INTO pending_confirmations (id, user_id, tool_name, args_json, description, created_at, expires_at, status)
VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')`,
		id, userID, toolName, string(argsJSON), description,
		now.Format(time.RFC3339Nano), exp.Format(time.RFC3339Nano),
	)
	if err != nil {
		return nil, err
	}
	return &Record{
		ID: id, UserID: userID, ToolName: toolName, Args: args,
		Description: description, CreatedAt: now, ExpiresAt: exp, Status: "pending",
	}, nil
}

// Claim validates that pendingID exists, belongs to userID, has not
// expired, and has not already been used — then atomically marks it
// executed and returns the original call so the gateway can dispatch it.
// A caller must treat a non-nil Record from Claim as authorization to run
// the tool call exactly once; Claim will not return the same usable
// Record twice, including under concurrent callers racing the same id.
func (s *Store) Claim(ctx context.Context, pendingID, userID string) (*Record, error) {
	row := s.db.QueryRowContext(ctx, `
SELECT user_id, tool_name, args_json, description, created_at, expires_at, status
FROM pending_confirmations WHERE id = ?`, pendingID)

	var uid, tool, argsJSON, desc, createdAt, expiresAt, status string
	if err := row.Scan(&uid, &tool, &argsJSON, &desc, &createdAt, &expiresAt, &status); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, ErrNotFound
		}
		return nil, err
	}
	if uid != userID {
		return nil, ErrForbidden
	}
	exp, err := time.Parse(time.RFC3339Nano, expiresAt)
	if err != nil {
		return nil, err
	}
	if time.Now().UTC().After(exp) {
		return nil, ErrExpired
	}
	if status != "pending" {
		return nil, ErrAlreadyUsed
	}

	// Atomic claim: only one caller can flip status pending -> executed.
	res, err := s.db.ExecContext(ctx, `
UPDATE pending_confirmations SET status = 'executed'
WHERE id = ? AND status = 'pending'`, pendingID)
	if err != nil {
		return nil, err
	}
	n, err := res.RowsAffected()
	if err != nil {
		return nil, err
	}
	if n == 0 {
		// Lost a race against a concurrent Claim call for the same id.
		return nil, ErrAlreadyUsed
	}

	var args map[string]any
	if err := json.Unmarshal([]byte(argsJSON), &args); err != nil {
		return nil, err
	}
	created, _ := time.Parse(time.RFC3339Nano, createdAt)
	return &Record{
		ID: pendingID, UserID: uid, ToolName: tool, Args: args,
		Description: desc, CreatedAt: created, ExpiresAt: exp, Status: "executed",
	}, nil
}
