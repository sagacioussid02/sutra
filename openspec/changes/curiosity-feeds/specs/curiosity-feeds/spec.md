## ADDED Requirements

### Requirement: Weather alerts come from a forecast and are filed as signals

When a home area is set, the system SHALL geocode it once, read the next 18 hours of hourly forecast, and file a `weather` signal with medium urgency for each notable condition (snowfall totalling at least 1 cm, heavy rain, a thunderstorm, wind gusts of 65 km/h or more, an overnight low at or below -12 C, a high at or above 37 C), at most one per kind per local day, expiring an hour after the window ends. Only the area name SHALL leave the machine. A failed fetch SHALL produce no signal and SHALL NOT raise.

#### Scenario: Snow is coming

- **WHEN** the forecast shows 3 cm of snow starting this evening
- **THEN** one weather signal for snow is filed once that day and expires after the snow

#### Scenario: Once per day

- **WHEN** the same condition is seen on the next poll
- **THEN** no second signal is filed

#### Scenario: Feed down

- **WHEN** the weather service cannot be reached
- **THEN** nothing is filed and no error is shown

### Requirement: News is opt-in, topic-only until accepted, and untrusted

The system SHALL fetch headlines only when news is switched on, only for approved interests or topics the user lists, at most one roundup a day, only while the `news` bar is below 0.8. It SHALL keep up to three headlines with their source names as the signal summary, SHALL file it as a signal treated like a research finding (connected to an approved interest, always a topic-only question, no second benefit bar), SHALL give the headlines only after the user says yes and inside an untrusted block, and SHALL lower the bar on acceptance and raise it on declining or ignoring.

#### Scenario: Off by default

- **WHEN** news has not been switched on
- **THEN** no news request is made

#### Scenario: Topic only

- **WHEN** a roundup is ready
- **THEN** Sutra says only that there is news about the topic and asks whether to hear it

#### Scenario: Instructions in a headline

- **WHEN** a headline contains text telling the assistant to do something
- **THEN** it is given to the user only after yes, as data, and nothing is acted on

#### Scenario: Unwelcome

- **WHEN** the user declines several roundups
- **THEN** the bar reaches 0.8 and no more are fetched

### Requirement: Local activities are researched only with an area, and only for local topics

When a home area is set, the idle researcher SHALL gain the topic "local events and things to do" and SHALL be told the area may appear in a brief for local topics only. Without a home area, no brief SHALL name the user's location.

#### Scenario: With an area

- **WHEN** the picker chooses the local topic
- **THEN** the brief may name the area

#### Scenario: Without an area

- **WHEN** no area is set
- **THEN** there is no local topic

### Requirement: A morning brief on request

The system SHALL provide a read-only tool that returns, as plain lines, reminders due today, plans for today and tomorrow, the weather outlook when an area is set, and any research finding waiting, and SHALL NOT run on a schedule.

#### Scenario: Asked

- **WHEN** the user says "give me my morning brief"
- **THEN** the model calls the tool and says the lines naturally

#### Scenario: Nothing on

- **WHEN** there is nothing for today
- **THEN** the lines say so

### Requirement: The user sees and controls the feeds

The system SHALL provide `/feeds` showing which feeds are on, the area, and the last check of each, with `/feeds news on|off`, and SHALL make no request for a feed that is off.

#### Scenario: Switching news on

- **WHEN** the user runs `/feeds news on`
- **THEN** news roundups become possible from the next poll
