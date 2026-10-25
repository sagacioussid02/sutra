// Command sutra-discover fetches a backend project's Sutra Agent Manifest,
// shows a human every new or changed tool it declares, and records an
// explicit approval decision (a chosen tier, a rejection, or a skip) for
// each one. It never calls anything the manifest describes — only the
// manifest endpoint itself is ever fetched. Approved tools become callable
// only after cmd/gateway is restarted; see docs/agent-manifest.md.
package main

import (
	"bufio"
	"context"
	"flag"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"strings"

	"github.com/siddharthshankar/sutra/gateway/internal/discovery"
	"github.com/siddharthshankar/sutra/gateway/internal/discoverysrc"
	"github.com/siddharthshankar/sutra/gateway/internal/manifest"
	"github.com/siddharthshankar/sutra/gateway/internal/registry"
)

func main() {
	urlFlag := flag.String("url", "", "single manifest URL to discover (alternative to -sources)")
	baseURLFlag := flag.String("base-url", "", "base URL approved tools are called against (defaults to -url with the manifest suffix stripped)")
	sourcesPath := flag.String("sources", "discovery-sources.yaml", "path to the discovery sources config (see discovery-sources.example.yaml)")
	approvalDBPath := flag.String("approval-db", "sutra-discovery.db", "path to the discovery approval SQLite database")
	approver := flag.String("approver", os.Getenv("SUTRA_USER_ID"), "gateway user id recorded as the approver (defaults to $SUTRA_USER_ID)")
	flag.Parse()

	if *approver == "" {
		log.Fatal("sutra-discover: -approver (or $SUTRA_USER_ID) is required")
	}

	store, err := discovery.Open(*approvalDBPath)
	if err != nil {
		log.Fatalf("sutra-discover: opening approval store: %v", err)
	}
	defer store.Close()

	var sources []discoverysrc.Source
	if *urlFlag != "" {
		base := *baseURLFlag
		if base == "" {
			base = strings.TrimSuffix(*urlFlag, manifest.WellKnownPath)
		}
		sources = []discoverysrc.Source{{ManifestURL: *urlFlag, BaseURL: base}}
	} else {
		cfg, err := discoverysrc.Load(*sourcesPath)
		if err != nil {
			log.Fatalf("sutra-discover: loading %s: %v", *sourcesPath, err)
		}
		sources = cfg.Sources
	}
	if len(sources) == 0 {
		log.Fatal("sutra-discover: nothing to discover — pass -url or configure -sources")
	}

	ctx := context.Background()
	scanner := bufio.NewScanner(os.Stdin)
	for _, src := range sources {
		runSource(ctx, store, src, *approver, scanner, os.Stdout)
	}
}

func runSource(ctx context.Context, store *discovery.Store, src discoverysrc.Source, approver string, scanner *bufio.Scanner, out io.Writer) {
	fmt.Fprintf(out, "\n=== %s ===\n", src.ManifestURL)

	m, err := manifest.Fetch(ctx, http.DefaultClient, src.ManifestURL)
	if err != nil {
		fmt.Fprintf(out, "error fetching manifest: %v\n", err)
		return
	}
	if err := m.Validate(); err != nil {
		fmt.Fprintf(out, "invalid manifest, nothing to review:\n%v\n", err)
		return
	}

	sourceName := src.Name
	if sourceName == "" {
		sourceName = m.Project.Name
	}

	reviews, err := discovery.Diff(ctx, store, m)
	if err != nil {
		fmt.Fprintf(out, "error comparing against prior approvals: %v\n", err)
		return
	}

	var pending []discovery.PendingReview
	for _, r := range reviews {
		if r.Kind != discovery.ChangeUnchanged {
			pending = append(pending, r)
		}
	}
	if len(pending) == 0 {
		fmt.Fprintf(out, "%s: nothing new to review (%d tool(s) already settled)\n", sourceName, len(reviews))
		return
	}

	for _, r := range pending {
		reviewTool(ctx, store, sourceName, r, approver, scanner, out)
	}
	fmt.Fprintln(out, "\nRestart the gateway for any newly approved tools to go live.")
}

func reviewTool(ctx context.Context, store *discovery.Store, sourceName string, r discovery.PendingReview, approver string, scanner *bufio.Scanner, out io.Writer) {
	t := r.Tool
	fmt.Fprintf(out, "\n--- %s (%s) ---\n", t.Name, r.Kind)
	fmt.Fprintf(out, "  %s\n", t.Description)
	fmt.Fprintf(out, "  %s %s\n", t.Method, t.Path)
	fmt.Fprintf(out, "  suggested tier (not trusted — you choose the real one below): %s\n", t.TierHint)
	if t.GenericCallable {
		fmt.Fprintln(out, "  generic-callable: yes — approval alone makes this callable")
	} else {
		fmt.Fprintf(out, "  generic-callable: no (%s)\n", t.GenericCallableReason)
		fmt.Fprintln(out, "  approving this still requires a hand-written adapter before it's callable")
	}

	for {
		fmt.Fprint(out, "  approve as [read-only/confirm-first/never-by-voice] / reject / skip> ")
		answer, ok := readLine(scanner)
		if !ok {
			return
		}

		switch answer {
		case "reject":
			record(ctx, store, sourceName, t, discovery.StatusRejected, "", approver, out)
			return
		case "skip", "":
			fmt.Fprintln(out, "  skipped")
			return
		case "read-only", "confirm-first", "never-by-voice":
			tier := registry.Tier(answer)
			if tier == registry.TierReadOnly && t.Method == http.MethodPost {
				fmt.Fprintf(out, "  WARNING: %q calls %s %s, which looks mutating, but you're approving it as read-only.\n", t.Name, t.Method, t.Path)
				fmt.Fprint(out, "  type the tool name again to confirm anyway> ")
				confirmName, ok := readLine(scanner)
				if !ok || confirmName != t.Name {
					fmt.Fprintln(out, "  not confirmed — skipped")
					return
				}
			}
			record(ctx, store, sourceName, t, discovery.StatusApproved, tier, approver, out)
			return
		default:
			fmt.Fprintln(out, "  please type read-only, confirm-first, never-by-voice, reject, or skip")
		}
	}
}

func record(ctx context.Context, store *discovery.Store, sourceName string, t manifest.Tool, status string, tier registry.Tier, approver string, out io.Writer) {
	err := store.Record(ctx, discovery.Approval{
		SourceName:   sourceName,
		ToolName:     t.Name,
		ManifestHash: t.Hash(),
		Status:       status,
		Tier:         tier,
		DecidedBy:    approver,
	})
	if err != nil {
		fmt.Fprintf(out, "  error recording decision: %v\n", err)
		return
	}
	fmt.Fprintf(out, "  recorded: %s\n", status)
}

// readLine reads one line from scanner with surrounding whitespace
// trimmed. ok is false at EOF.
func readLine(scanner *bufio.Scanner) (line string, ok bool) {
	if !scanner.Scan() {
		return "", false
	}
	return strings.TrimSpace(scanner.Text()), true
}
