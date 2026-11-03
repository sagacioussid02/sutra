## Context

`prompts/system.md` is the whole answering contract: short spoken replies, facts only from tool results, confirm before anything that changes things, and — until now — refuse whatever no tool covers. The refusal line made sense when the tool set was the product. With memory, reminders, and ordinary conversation in scope, it makes the assistant refuse homework questions.

This change is prompt-only. The design work is drawing three lines precisely enough that a model can follow them:

1. **Questions vs actions.** A question ("what is compound interest?") is answered. An action ("book me a flight") with no tool is declined. The old line conflated the two.
2. **Personal facts vs general knowledge.** Anything about *this user's* finances, accounts, or life still comes only from tool results or memory tools — the model must never answer "what do I owe?" from vibes. General knowledge ("what is APR?") is answered directly.
3. **Stable vs volatile facts.** Training knowledge goes stale. Prices, the current date/time, news, and anything the model is unsure still holds need a tool check; with no tool able to check, the honest answer is "I can't check that right now," not a confident stale number.

## Goals / Non-Goals

**Goals:**

- General questions get real answers, in the established voice: short, plain, speakable.
- The personal-facts guard survives verbatim in effect: no invented figures, ever.
- Volatile facts are checked or honestly declined, never recited from stale memory.

**Non-Goals:**

- Adding a web-search tool. If one lands later, the volatile-facts line already tells the model to use it; this change only fixes behaviour when no such tool exists.
- Changing the classifier, the tool set, or the confirmation flow.
- Long-form answers. The spoken style rules (a sentence or two, offer more on request) still apply to direct answers.

## Decisions

### Replace, don't append

The new lines replace the refusal line in place rather than adding a paragraph elsewhere in the prompt, so the contract has exactly one statement of each rule and no internal contradiction for the model to resolve.

### The refusal narrows to actions

"I can't do it" remains — for actions. Keeping the sentence for the case it was written for preserves the anti-pretending guarantee (no fake "done" for an unperformed action) without extending it to questions.

### Volatile facts: name the categories

The prompt names examples (prices, current dates and times, news) plus a catch-all ("anything you are not sure still holds"), because a bare "be careful with stale facts" is too vague to change behaviour. Naming the current date/time matters: models are routinely wrong about "today" without a tool.

## Risks / Trade-offs

- **Over-eager direct answers.** The model may answer a question that a tool should have handled ("what's the rate on my card?" — personal, tool-only; the carve-out covers it, but phrasing edge cases will occur). Mitigation: the personal-facts line stays first and unqualified, and dogfooding will show whether eval cases are needed.
- **Prompt-only means no test can pin the behaviour.** The suite asserts prompt *wording* only where safety depends on it (confirmation language). The direct-answers behaviour is verified by use and by the manual voice checks, and noted as such in tasks.
