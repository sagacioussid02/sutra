## ADDED Requirements

### Requirement: Conversations are stored as episode nodes

The system SHALL close an episode when the subject changes or after an idle gap and SHALL then write one node consisting of a topic of at most 60 characters, a gist of at most 300 characters of what was covered, a mode (`explained`, `planned`, `worked_on`, `decided`, `asked`), what remains open (`example`, `deeper`, `practice`, `decision` or none), a few short entities, and timestamps. The node SHALL be built from the user's own utterances plus the assistant's reply on turns that used no tool. On a turn that used a tool only the user's utterance SHALL count, and a turn that used an excluded tool (default prefix `finanxe_`) SHALL contribute nothing. Tool results SHALL NOT be read. The node SHALL NOT store the full reply or the user's utterance.

#### Scenario: A brief explanation becomes a node

- **WHEN** the user asks "how does tool calling work?", gets a brief answer with no tool, and the subject then changes
- **THEN** a node is stored with a topic about tool calling, a short gist of what was said, and `example` among its open items

#### Scenario: Excluded tools contribute nothing

- **WHEN** a turn used a finance tool
- **THEN** nothing from that turn reaches any episode node

#### Scenario: Tool-using turns count only the user's words

- **WHEN** a turn used a research tool
- **THEN** only the user's utterance may inform the node, and no tool output or reply text does

#### Scenario: Low-confidence speech is skipped

- **WHEN** the voice layer flags a transcript as low confidence
- **THEN** that turn does not inform any node

### Requirement: Episodes are linked by typed, explained edges

After a node is written, a linker subagent SHALL be shown the node and a bounded set of candidate nodes and SHALL return zero or more edges, each with a type (`same_topic`, `extends`, `prerequisite_of`, `applies_to`, `updates`), a strength from 0 to 1, and a one-sentence reason. The system SHALL validate that each edge refers to a candidate and uses a known type and SHALL discard any that do not. A `same_topic` edge of high strength SHALL merge the new episode into the older node, updating its gist and last-touched time, instead of creating a parallel node.

#### Scenario: A related conversation is linked

- **WHEN** the user discusses building a small agent after an earlier node about tool calling exists
- **THEN** an edge such as `applies_to` or `extends` links the two with a reason in words

#### Scenario: Repeating a question strengthens one node

- **WHEN** the user asks about tool calling again
- **THEN** the existing node is updated and no second node for the same topic is created

#### Scenario: A link to a node that was not offered

- **WHEN** the linker returns an edge to an id that was not among the candidates
- **THEN** the edge is discarded

### Requirement: Retrieval proposes candidates and models judge them

The system SHALL provide a retriever that, for a piece of text, returns candidate nodes ranked by lexical overlap on topic, gist and entities, recency, and one-hop graph neighbours of recently touched nodes, bounded by prompt size. The retriever SHALL be replaceable without changes to its callers. A candidate SHALL be treated as a proposal only; relatedness SHALL be decided by a model call.

#### Scenario: Neighbours widen the match

- **WHEN** the current text shares no words with a node but the node is linked to a recently discussed node
- **THEN** the node can still appear among the candidates

#### Scenario: Nothing found

- **WHEN** the retriever finds no candidates
- **THEN** no relatedness model call is made

### Requirement: A relatedness subagent advises the orchestrator

When candidates exist and the subject of the conversation has changed since the last check, the system SHALL make a tools-off subagent call that is shown only the user's current utterance, their previous two utterances, and the numbered candidates (topic, gist, open items, age and earlier offer outcomes). The subagent SHALL return either none or an advice object with a node, a benefit score from 0 to 1, a reason, and a suggested step. The system SHALL validate the node and SHALL treat an invalid answer as none. The subagent SHALL treat a node as related only if the user's current work would plausibly benefit from it, and SHALL return none when unsure. The advice SHALL go to the offer judge and SHALL NOT be spoken to the user directly.

#### Scenario: Tangentially related work

- **WHEN** the user, a day after asking how tool calling works, asks about structuring a small AI assistant
- **THEN** the advice names the tool-calling node with a reason and a benefit score

#### Scenario: Unrelated work

- **WHEN** the user asks about weekend plans
- **THEN** the advice is none

#### Scenario: Same subject as the last check

- **WHEN** the user sends several messages on one subject
- **THEN** the subagent is not called again for that subject

#### Scenario: Invalid node

- **WHEN** the subagent names a node that was not offered
- **THEN** it is treated as none

### Requirement: The graph decays and can be inspected and deleted

The system SHALL reduce the weight of nodes and edges that are never retrieved or linked and SHALL archive faded nodes so that they are not retrieved. A cap on stored nodes SHALL delete the weakest archived nodes first. The graph SHALL be kept in an owner-only database separate from memory and interests. `/graph` SHALL list episodes, show a node's neighbours with edge reasons, and `/graph forget <id|all>` SHALL delete. `SUTRA_GRAPH=off` SHALL disable the graph, with no episode, linker or advice calls.

#### Scenario: Reading why two conversations are linked

- **WHEN** the user runs `/graph` on a node
- **THEN** its neighbours are listed with each edge's type and reason

#### Scenario: Forget

- **WHEN** the user runs `/graph forget all`
- **THEN** every node and edge is deleted

#### Scenario: Off

- **WHEN** `SUTRA_GRAPH=off`
- **THEN** no graph model calls are made and no graph tool is offered
