// Package cliapp implements the interactive loop behind the sutra-cli
// command: list the tools available to the authenticated user, let them
// pick one and supply JSON arguments, dispatch it through the gateway, and
// — for a confirm-first tool — print the pending description and require
// an explicit "yes" before calling gateway_confirm. It knows nothing about
// process startup, flags, or how the connection was authenticated; that is
// cmd/sutra-cli's job.
package cliapp

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"strings"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// GatewayConfirmTool matches authcfg.GatewayConfirmTool. Duplicated as a
// literal (rather than importing internal/authcfg) since this package is a
// pure MCP client and has no reason to depend on the gateway's own
// internals — it only needs the tool name, which is part of the gateway's
// public MCP surface.
const GatewayConfirmTool = "gateway_confirm"

// Session is the subset of *mcp.ClientSession the interactive loop needs.
// A plain interface (rather than depending on *mcp.ClientSession directly)
// so tests can exercise Run's branching without a real network connection
// when that's all a given test cares about; most tests here still use a
// real ClientSession against a real gateway for the transport-level
// guarantees (auth, tiering) that only a real connection can prove.
type Session interface {
	ListTools(ctx context.Context, params *mcp.ListToolsParams) (*mcp.ListToolsResult, error)
	CallTool(ctx context.Context, params *mcp.CallToolParams) (*mcp.CallToolResult, error)
}

// pendingConfirmation is the shape of a confirm-first tool's initial
// result, as produced by gateway-core's confirmFirstHandler.
type pendingConfirmation struct {
	PendingID   string `json:"pending_id"`
	Description string `json:"description"`
	ExpiresAt   string `json:"expires_at"`
}

// Run drives the interactive loop: print the tool list once, then
// repeatedly prompt for a tool name and JSON arguments, dispatch, and
// handle the confirm-first branch. It returns when in reaches EOF or the
// user enters a blank tool name; it does not return an error for ordinary
// tool-call or confirmation-decline outcomes, only for I/O failures on in.
func Run(ctx context.Context, sess Session, in io.Reader, out io.Writer) error {
	tools, err := sess.ListTools(ctx, nil)
	if err != nil {
		return fmt.Errorf("cliapp: listing tools: %w", err)
	}
	fmt.Fprintln(out, "Available tools:")
	for _, t := range tools.Tools {
		fmt.Fprintf(out, "  %s — %s\n", t.Name, t.Description)
	}

	scanner := bufio.NewScanner(in)
	for {
		fmt.Fprint(out, "\ntool (blank to quit)> ")
		toolName, ok := readLine(scanner)
		if !ok || toolName == "" {
			return scanner.Err()
		}

		fmt.Fprint(out, "args as JSON (e.g. {} or {\"key\":\"value\"})> ")
		argsLine, ok := readLine(scanner)
		if !ok {
			return scanner.Err()
		}
		if argsLine == "" {
			argsLine = "{}"
		}
		var args map[string]any
		if err := json.Unmarshal([]byte(argsLine), &args); err != nil {
			fmt.Fprintf(out, "invalid JSON arguments: %v\n", err)
			continue
		}

		if err := callAndHandle(ctx, sess, scanner, out, toolName, args); err != nil {
			fmt.Fprintf(out, "error: %v\n", err)
		}
	}
}

func callAndHandle(ctx context.Context, sess Session, scanner *bufio.Scanner, out io.Writer, toolName string, args map[string]any) error {
	result, err := sess.CallTool(ctx, &mcp.CallToolParams{Name: toolName, Arguments: args})
	if err != nil {
		return err
	}
	if result.IsError {
		fmt.Fprintf(out, "tool error: %s\n", resultText(result))
		return nil
	}

	text := resultText(result)
	var pending pendingConfirmation
	if json.Unmarshal([]byte(text), &pending) == nil && pending.PendingID != "" {
		fmt.Fprintf(out, "pending confirmation: %s\n", pending.Description)
		fmt.Fprintf(out, "expires at: %s\n", pending.ExpiresAt)
		fmt.Fprint(out, "confirm? [y/N]> ")
		answer, ok := readLine(scanner)
		if !ok {
			return scanner.Err()
		}
		if !isAffirmative(answer) {
			fmt.Fprintln(out, "cancelled — nothing was executed")
			return nil
		}

		confirmResult, err := sess.CallTool(ctx, &mcp.CallToolParams{
			Name:      GatewayConfirmTool,
			Arguments: map[string]any{"pending_id": pending.PendingID},
		})
		if err != nil {
			return err
		}
		if confirmResult.IsError {
			fmt.Fprintf(out, "confirmation failed: %s\n", resultText(confirmResult))
			return nil
		}
		fmt.Fprintf(out, "confirmed — result: %s\n", resultText(confirmResult))
		return nil
	}

	fmt.Fprintf(out, "result: %s\n", text)
	return nil
}

func isAffirmative(s string) bool {
	s = strings.ToLower(strings.TrimSpace(s))
	return s == "y" || s == "yes"
}

// resultText returns the first TextContent's text from result, which is
// how gateway-core's jsonResult/errorResult always render results — empty
// if result has no text content.
func resultText(result *mcp.CallToolResult) string {
	for _, c := range result.Content {
		if tc, ok := c.(*mcp.TextContent); ok {
			return tc.Text
		}
	}
	return ""
}

// readLine reads one line from scanner with surrounding whitespace
// trimmed. ok is false at EOF (check scanner.Err() to distinguish a clean
// EOF from a read error).
func readLine(scanner *bufio.Scanner) (line string, ok bool) {
	if !scanner.Scan() {
		return "", false
	}
	return strings.TrimSpace(scanner.Text()), true
}
