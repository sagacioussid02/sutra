// Command sutra-watch checks the health route of every service Sutra
// depends on (the gateway itself, finanxe, the SPY desk, Minions, cloud
// projects) once, and sends an ntfy push when one goes down, turns
// degraded, or comes back. launchd runs it every five minutes (see
// deploy/launchd/com.sutra.watch.plist); state between runs lives in a
// small JSON file.
//
// The ntfy topic is read from the environment (SUTRA_WATCH_NTFY_TOPIC by
// default), never from the repo: anyone who knows an ntfy topic can read it.
package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/siddharthshankar/sutra/gateway/internal/watch"
)

func main() {
	home, _ := os.UserHomeDir()
	configPath := flag.String("config", "watch.yaml", "path to the watch config (see watch.example.yaml)")
	statePath := flag.String("state", filepath.Join(home, ".local", "state", "sutra", "watch-state.json"), "where to remember what was last announced")
	dryRun := flag.Bool("dry-run", false, "check and print, but send nothing and don't update state")
	test := flag.Bool("test-notify", false, "send one test notification and exit")
	flag.Parse()

	cfg, err := watch.LoadConfig(*configPath)
	if err != nil {
		log.Fatal(err)
	}

	client := &http.Client{Timeout: 30 * time.Second}
	var notifier watch.Notifier
	topic := strings.TrimSpace(os.Getenv(cfg.Ntfy.TopicEnv))
	switch {
	case *dryRun:
	case topic == "":
		log.Printf("sutra-watch: $%s is empty: checking without sending alerts", cfg.Ntfy.TopicEnv)
	default:
		token := ""
		if cfg.Ntfy.TokenEnv != "" {
			token = strings.TrimSpace(os.Getenv(cfg.Ntfy.TokenEnv))
		}
		notifier = watch.Ntfy{Server: cfg.Ntfy.Server, Topic: topic, Token: token, Client: client}
	}

	ctx := context.Background()
	if *test {
		if notifier == nil {
			log.Fatalf("sutra-watch: no topic set ($%s)", cfg.Ntfy.TopicEnv)
		}
		if err := notifier.Notify(ctx, watch.Alert{Target: "sutra-watch", State: watch.StateUp, Detail: "Test notification: alerts reach this phone.", Priority: "default"}); err != nil {
			log.Fatal(err)
		}
		fmt.Println("sent a test notification")
		return
	}

	state, err := watch.LoadState(*statePath)
	if err != nil {
		log.Fatalf("sutra-watch: reading state: %v", err)
	}
	reports := watch.Run(ctx, cfg, client, state, notifier, time.Now())
	for _, r := range reports {
		line := fmt.Sprintf("%-14s %-9s %s", r.Target, r.Result.State, r.Result.Detail)
		if r.Alert != nil {
			line += "  -> alert: " + r.Alert.Title()
		}
		if r.Err != nil {
			line += "  (alert not sent: " + r.Err.Error() + ")"
		}
		fmt.Println(line)
	}
	if *dryRun {
		return
	}
	if err := watch.SaveState(*statePath, state); err != nil {
		log.Fatalf("sutra-watch: saving state: %v", err)
	}
}
