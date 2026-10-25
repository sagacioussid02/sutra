package discovery

import (
	"context"

	"github.com/siddharthshankar/sutra/gateway/internal/manifest"
)

// ChangeKind classifies one manifest tool against the approval store's
// current record for it.
type ChangeKind string

const (
	// ChangeNew: no approval decision has ever been recorded for this tool.
	ChangeNew ChangeKind = "new"
	// ChangeChanged: a decision exists, but the tool's manifest definition
	// has changed since — the prior decision no longer applies.
	ChangeChanged ChangeKind = "changed"
	// ChangeUnchanged: an approved decision exists and still matches the
	// tool's current manifest definition — nothing to review.
	ChangeUnchanged ChangeKind = "unchanged"
	// ChangeRejectedAgain: the tool was previously rejected and its
	// definition has not changed since — resurfaced for review rather
	// than hidden, since the human may want to reconsider.
	ChangeRejectedAgain ChangeKind = "rejected-again"
)

// PendingReview is one manifest tool worth showing a human, alongside its
// prior decision (if any).
type PendingReview struct {
	Tool  manifest.Tool
	Kind  ChangeKind
	Prior *Approval // nil for ChangeNew
}

// Diff compares m's tools against store's current approvals for
// m.Project.Name and classifies each one. Only ChangeNew, ChangeChanged,
// and ChangeRejectedAgain are worth a human's attention; ChangeUnchanged
// entries are included so a caller can report a count without a second
// query, but are not meant to be interactively reviewed.
func Diff(ctx context.Context, store *Store, m *manifest.Manifest) ([]PendingReview, error) {
	reviews := make([]PendingReview, 0, len(m.Tools))
	for _, tool := range m.Tools {
		prior, found, err := store.Get(ctx, m.Project.Name, tool.Name)
		if err != nil {
			return nil, err
		}

		hash := tool.Hash()
		switch {
		case !found:
			reviews = append(reviews, PendingReview{Tool: tool, Kind: ChangeNew})
		case prior.ManifestHash != hash:
			reviews = append(reviews, PendingReview{Tool: tool, Kind: ChangeChanged, Prior: prior})
		case prior.Status == StatusRejected:
			reviews = append(reviews, PendingReview{Tool: tool, Kind: ChangeRejectedAgain, Prior: prior})
		default:
			reviews = append(reviews, PendingReview{Tool: tool, Kind: ChangeUnchanged, Prior: prior})
		}
	}
	return reviews, nil
}
