## ADDED Requirements

### Requirement: General questions are answered directly when no tool applies

When the user asks a general question that no available tool covers, the assistant SHALL answer it directly from the model's knowledge, in the normal short spoken style, instead of refusing for lack of a tool.

#### Scenario: A general knowledge question

- **WHEN** the user asks "what is compound interest?" and no tool covers it
- **THEN** the assistant explains it directly and briefly

### Requirement: Personal facts still come only from tools

The assistant SHALL state financial figures and other personal facts only when they appear in a tool result from the conversation. It SHALL NOT answer a question about the user's own accounts, balances, or personal data from model knowledge, and SHALL say plainly when it does not have the information.

#### Scenario: A personal question phrased as general chat

- **WHEN** the user asks "what do I owe on my card?" and no tool result in the conversation states it
- **THEN** the assistant uses the relevant tool or says it does not have the information; it never estimates or invents a figure

### Requirement: Volatile facts need a tool check or an honest decline

For facts that change over time — prices, current dates and times, news, and anything the model is unsure still holds — the assistant SHALL use a tool that can check when one is available, and SHALL otherwise say it cannot check right now rather than answering from training memory.

#### Scenario: A current price with no way to check

- **WHEN** the user asks for a current price and no tool can look it up
- **THEN** the assistant says it can't check that right now, and does not quote a remembered price

### Requirement: The refusal applies to actions, not questions

When the user asks the assistant to perform an action that no tool can perform, the assistant SHALL say it can't do it and SHALL NOT pretend the action was taken.

#### Scenario: An action with no tool

- **WHEN** the user asks the assistant to book a flight and no tool can book one
- **THEN** the assistant says it can't do that, without implying it was done
