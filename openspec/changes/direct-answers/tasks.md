## 1. Prompt change

- [x] 1.1 Replace the blanket refusal line in `prompts/system.md` with the direct-answers rule: general questions with no applicable tool are answered directly from the model, in the short spoken style
- [x] 1.2 Add the volatile-facts carve-out: prices, current dates/times, news, and anything possibly stale need a tool check; with no tool able to check, say so instead of answering from memory
- [x] 1.3 Narrow the refusal to actions: "say that you can't do it" applies to doing something no tool can do; keep the personal-facts guard (figures and personal facts only from tool results) intact

## 2. Consistency checks

- [x] 2.1 Grep the test suite and evals for assertions on the old refusal text and update any found (result: none — only `system.md` contained the line; `test_prompts.py` asserts the tools/confirmation wording and still passes)
- [x] 2.2 Run the full orchestrator suite to confirm no prompt-wording assertion regressed

## 3. Verification

- [ ] 3.1 Dogfood during the A+B trial: ask a mix of general questions, personal questions, and volatile-fact questions by voice and text; note any case where a direct answer was given for a personal or volatile fact (behaviour is prompt-level, so this is the real check)
