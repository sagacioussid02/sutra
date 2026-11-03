## Why

The offers system can judge and say things, but until now nothing outside the conversation feeds it except idle research. A friend mentions that snow is coming, that something is going on this weekend, or that a thing you care about is in the news. Those need real sources, and the user should choose what Sutra is allowed to look at.

## What Changes

- **Weather alerts.** With a home area set, Sutra checks the forecast and files a signal when something notable is coming (snow, heavy rain, thunderstorms, strong wind, extreme cold or heat), once per kind per day, expiring when the weather passes. The offers system decides whether it matters to this user now, using the conversation graph, so "snow on the pass" lands when the user said they were driving up.
- **News on topics they care about.** Off by default. When switched on, one headline roundup a day at most, on an approved interest (or a topic the user lists), as a topic-only question; the headlines are given only after yes, as untrusted text. How welcome it is teaches a bar.
- **Local things to do.** With a home area set, the idle researcher may look into local events and activities, and only then may a research brief name the area. Nothing else may.
- **A morning brief on request.** "Give me my morning brief" returns today's reminders and plans, the weather, and anything waiting, for the model to say naturally.
- **Control.** `SUTRA_HOME_AREA`, `SUTRA_NEWS`, `SUTRA_NEWS_TOPICS`, `SUTRA_UNITS`; `/feeds` shows what is on, what was last checked, and lets the user switch news on or off. Everything is opt-in, nothing personal leaves the machine, and the only outgoing text is a city name (weather) or a topic word (news).

Out of scope: deals and prices, travel and route planning, calendars, and any action on what is found.

## Capabilities

### New Capabilities
- `curiosity-feeds`: weather alerts, topic news, local activities through idle research, and an on-request morning brief.

### Modified Capabilities
(none)

## Impact

- New package `orchestrator/src/sutra_orchestrator/feeds/`. Outbound requests only to the Open-Meteo weather and geocoding APIs (a city name) and Google News RSS (a topic word), standard library only, no keys.
- `OffersService` treats a news signal like a research finding (topic-only ask, approved interest as the connection, its own learned bar). `IdleResearcher` can be given the home area.
- Reads reminders and plans for the brief.
