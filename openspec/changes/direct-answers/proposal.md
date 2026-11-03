## Why

The system prompt currently tells Sutra to refuse anything no tool can do: "If no tool can do what the user asks, say that you can't do it." That line was written when every request was an action against the gateway. It makes Sutra useless as a conversational assistant — ask it what a hexagon is, why the sky is blue, or how a sourdough starter works, and it declines, because no finance tool covers the question. General questions should be answered directly by the model; the refusal should apply only to *actions* no tool can perform.

## What Changes

- Edit `orchestrator/src/sutra_orchestrator/prompts/system.md`: replace the blanket refusal with a direct-answers rule — general questions that no tool covers are answered directly from the model's knowledge, in the same short spoken style.
- Keep the existing guard for personal facts, unchanged: financial figures and other personal facts come only from tool results in this conversation, never from memory or invention.
- Add a volatile-facts carve-out: facts that change over time or may be stale in training data (prices, current dates and times, news, anything the model is unsure still holds) require a tool check; if no tool can check, Sutra says it can't check right now instead of answering from memory.
- Narrow the refusal to actions: when the user asks Sutra to *do* something no tool can do, it says it can't do it and does not pretend.

## Capabilities

### New Capabilities

- `direct-answers`: the prompt-level contract for when Sutra answers a question directly, when it must rely on a tool, and when it must decline.

### Modified Capabilities

<!-- None: no spec-level behaviour of memory or the gateway changes; this is the system prompt's answering contract only. -->

## Impact

- One file of behaviour: `prompts/system.md`. No code changes; the classifier, confirmation flow, and tools are untouched.
- The test suite and evals were grepped for assertions on the old refusal text: none exist (the prompt is asserted only for the presence of the tools/confirmation wording in `test_prompts.py`, which still passes).
- Risk is behavioural, not structural: the model may over-apply direct answers to questions that should have been tool calls (e.g. a balance phrased as a question). The carve-outs are written to keep personal facts tool-only, and the eval questions can grow a case for this if it shows up in use.
