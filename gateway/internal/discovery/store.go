// Package discovery holds the human decisions made about tools found on a
// backend project's Sutra Agent Manifest (internal/manifest): one approval
// (or rejection) record per (source, tool), keyed by a content hash of the
// tool's manifest definition so a changed definition invalidates its prior
// approval. It knows nothing about how a tool is actually called — that is
// internal/genericadapter's job, built on top of this package's approved
// records the same way gateway-core's confirm-first flow is built on top
// of internal/confirm's pending records.
package discovery

import (
	"context"
	"database/sql"
	"errors"
	"time"

	_ "modernc.org/sqlite"

	"github.com/siddharthshankar/sutra/gateway/internal/registry"
)

// Status values for an approval record.
const (
	StatusApproved = "approved"
	StatusRejected = "rejected"
)

// Approval is the current human decision about one (source, tool) pair.
type Approval struct {
	SourceName   string
	ToolName     string
	ManifestHash string
	Status       string
	Tier         registry.Tier // set only when Status is StatusApproved
	DecidedAt    time.Time
	DecidedBy    string
}

// Store wraps a SQLite database holding the discovery_approvals table.
type Store struct {
	db *sql.DB
}

// Open opens (creating if needed) the approval store at path.
func Open(path string) (*Store, error) {
	db, err := sql.Open("sqlite", path)
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(1)

	const schema = `
CREATE TABLE IF NOT EXISTS discovery_approvals (
	source_name   TEXT NOT NULL,
	tool_name     TEXT NOT NULL,
	manifest_hash TEXT NOT NULL,
	status        TEXT NOT NULL,
	tier          TEXT NOT NULL DEFAULT '',
	decided_at    TEXT NOT NULL,
	decided_by    TEXT NOT NULL,
	PRIMARY KEY (source_name, tool_name)
);
`
	if _, err := db.Exec(schema); err != nil {
		db.Close()
		return nil, err
	}
	return &Store{db: db}, nil
}

// Close closes the underlying database.
func (s *Store) Close() error { return s.db.Close() }

// Record inserts or overwrites the approval decision for
// (a.SourceName, a.ToolName). There is one current decision per tool, not
// a history — a re-approval or a rejection replaces whatever decision
// came before it.
func (s *Store) Record(ctx context.Context, a Approval) error {
	decidedAt := a.DecidedAt
	if decidedAt.IsZero() {
		decidedAt = time.Now().UTC()
	}
	_, err := s.db.ExecContext(ctx, `
INSERT INTO discovery_approvals (source_name, tool_name, manifest_hash, status, tier, decided_at, decided_by)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (source_name, tool_name) DO UPDATE SET
	manifest_hash = excluded.manifest_hash,
	status        = excluded.status,
	tier          = excluded.tier,
	decided_at    = excluded.decided_at,
	decided_by    = excluded.decided_by`,
		a.SourceName, a.ToolName, a.ManifestHash, a.Status, string(a.Tier),
		decidedAt.Format(time.RFC3339Nano), a.DecidedBy,
	)
	return err
}

// Get returns the current approval decision for (sourceName, toolName), if
// any has ever been recorded.
func (s *Store) Get(ctx context.Context, sourceName, toolName string) (*Approval, bool, error) {
	row := s.db.QueryRowContext(ctx, `
SELECT source_name, tool_name, manifest_hash, status, tier, decided_at, decided_by
FROM discovery_approvals WHERE source_name = ? AND tool_name = ?`, sourceName, toolName)

	a, err := scanApproval(row)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, false, nil
		}
		return nil, false, err
	}
	return a, true, nil
}

// Approved returns every currently approved record, across all sources —
// the set gateway startup wiring registers tools from.
func (s *Store) Approved(ctx context.Context) ([]Approval, error) {
	rows, err := s.db.QueryContext(ctx, `
SELECT source_name, tool_name, manifest_hash, status, tier, decided_at, decided_by
FROM discovery_approvals WHERE status = ?`, StatusApproved)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []Approval
	for rows.Next() {
		a, err := scanApproval(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, *a)
	}
	return out, rows.Err()
}

// rowScanner is satisfied by both *sql.Row and *sql.Rows.
type rowScanner interface {
	Scan(dest ...any) error
}

func scanApproval(row rowScanner) (*Approval, error) {
	var a Approval
	var tier, decidedAt string
	if err := row.Scan(&a.SourceName, &a.ToolName, &a.ManifestHash, &a.Status, &tier, &decidedAt, &a.DecidedBy); err != nil {
		return nil, err
	}
	a.Tier = registry.Tier(tier)
	parsed, err := time.Parse(time.RFC3339Nano, decidedAt)
	if err != nil {
		return nil, err
	}
	a.DecidedAt = parsed
	return &a, nil
}
