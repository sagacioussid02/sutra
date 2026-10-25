package registry

// RedactionMarker replaces a secret argument's value before it reaches the
// audit log. It masks the value rather than omitting the field, so the log
// still shows that the argument was present.
const RedactionMarker = "[REDACTED]"

// Redact returns a copy of args with every key in secretNames replaced by
// RedactionMarker. args is not mutated.
func Redact(args map[string]any, secretNames []string) map[string]any {
	if len(secretNames) == 0 {
		return args
	}
	secret := make(map[string]struct{}, len(secretNames))
	for _, n := range secretNames {
		secret[n] = struct{}{}
	}
	out := make(map[string]any, len(args))
	for k, v := range args {
		if _, ok := secret[k]; ok {
			out[k] = RedactionMarker
			continue
		}
		out[k] = v
	}
	return out
}
