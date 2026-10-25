// Package audit persists a durable, queryable record of every tool-call
// attempt the gateway handles: denials, pending confirmations, confirmed
// executions, direct read-only executions, and errors. It is built in
// gateway-core rather than deferred to a later phase because finanxe holds
// real financial data from day one.
package audit

import (
	"context"
	"database/sql"
	"encoding/json"
	"time"

	_ "modernc.org/sqlite"
)

// Status values for an audit entry.
const (
	StatusDenied    = "denied"
	StatusPending   = "pending"
	StatusExecuted  = "executed"
	StatusError     = "error"
)

// Entry is one audit log row. Args should already be redacted by the
// caller (the registry knows which argument names are secret; the audit
// package does not) before being passed here.
type Entry struct {
	Timestamp     time.Time
	UserID        string
	ToolName      string
	Tier          string
	Args          map[string]any
	Status        string
	PendingID     string // empty unless this entry relates to a confirm-first tool
	ResultSummary string
}

// Store wraps a SQLite database holding the audit_log table.
type Store struct {
	db *sql.DB
}

// Open opens (creating if needed) the audit log database at path and
// ensures its schema exists.
func Open(path string) (*Store, error) {
	db, err := sql.Open("sqlite", path)
	if err != nil {
		return nil, err
	}
	// SQLite via database/sql is single-writer; cap this out so concurrent
	// callers queue instead of hitting "database is locked" errors.
	db.SetMaxOpenConns(1)

	const schema = `
CREATE TABLE IF NOT EXISTS audit_log (
	id             INTEGER PRIMARY KEY AUTOINCREMENT,
	ts             TEXT NOT NULL,
	user_id        TEXT NOT NULL,
	tool_name      TEXT NOT NULL,
	tier           TEXT NOT NULL,
	args_json      TEXT NOT NULL,
	status         TEXT NOT NULL,
	pending_id     TEXT NOT NULL DEFAULT '',
	result_summary TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_tool ON audit_log(tool_name);
CREATE INDEX IF NOT EXISTS idx_audit_log_status ON audit_log(status);
CREATE INDEX IF NOT EXISTS idx_audit_log_ts ON audit_log(ts);
`
	if _, err := db.Exec(schema); err != nil {
		db.Close()
		return nil, err
	}
	return &Store{db: db}, nil
}

// Close closes the underlying database.
func (s *Store) Close() error { return s.db.Close() }

// Write persists one audit entry. It sets Timestamp to now if the caller
// left it zero.
func (s *Store) Write(ctx context.Context, e Entry) error {
	if e.Timestamp.IsZero() {
		e.Timestamp = time.Now().UTC()
	}
	argsJSON, err := json.Marshal(e.Args)
	if err != nil {
		return err
	}
	_, err = s.db.ExecContext(ctx, `
INSERT INTO audit_log (ts, user_id, tool_name, tier, args_json, status, pending_id, result_summary)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
		e.Timestamp.Format(time.RFC3339Nano), e.UserID, e.ToolName, e.Tier,
		string(argsJSON), e.Status, e.PendingID, e.ResultSummary,
	)
	return err
}

// Query is a filter for listing audit entries. Zero-value fields are not
// applied as filters.
type Query struct {
	UserID   string
	ToolName string
	Status   string
	Since    time.Time
	Until    time.Time
	Limit    int
}

// Find returns audit entries matching q, most recent first.
func (s *Store) Find(ctx context.Context, q Query) ([]Entry, error) {
	sqlStr := `SELECT ts, user_id, tool_name, tier, args_json, status, pending_id, result_summary FROM audit_log WHERE 1=1`
	var args []any
	if q.UserID != "" {
		sqlStr += ` AND user_id = ?`
		args = append(args, q.UserID)
	}
	if q.ToolName != "" {
		sqlStr += ` AND tool_name = ?`
		args = append(args, q.ToolName)
	}
	if q.Status != "" {
		sqlStr += ` AND status = ?`
		args = append(args, q.Status)
	}
	if !q.Since.IsZero() {
		sqlStr += ` AND ts >= ?`
		args = append(args, q.Since.Format(time.RFC3339Nano))
	}
	if !q.Until.IsZero() {
		sqlStr += ` AND ts <= ?`
		args = append(args, q.Until.Format(time.RFC3339Nano))
	}
	sqlStr += ` ORDER BY id DESC`
	if q.Limit > 0 {
		sqlStr += ` LIMIT ?`
		args = append(args, q.Limit)
	}

	rows, err := s.db.QueryContext(ctx, sqlStr, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []Entry
	for rows.Next() {
		var e Entry
		var ts, argsJSON string
		if err := rows.Scan(&ts, &e.UserID, &e.ToolName, &e.Tier, &argsJSON, &e.Status, &e.PendingID, &e.ResultSummary); err != nil {
			return nil, err
		}
		e.Timestamp, _ = time.Parse(time.RFC3339Nano, ts)
		_ = json.Unmarshal([]byte(argsJSON), &e.Args)
		out = append(out, e)
	}
	return out, rows.Err()
}
