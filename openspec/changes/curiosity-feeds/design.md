## Context

Signals, judging, the arbiter, learned bars and spoken delivery all exist. What is missing is producers. This change adds three, each opt-in, using free sources that need no key.

## Decisions

**1. Weather from Open-Meteo.** The home area (for example "Orem, Utah") is geocoded once (the first result whose region matches, cached), then the next 18 hours of hourly forecast are read. Notable conditions: snowfall of at least 1 cm in total, heavy rain (4 mm in an hour, or a heavy-rain weather code), a thunderstorm code, gusts of 65 km/h or more, an overnight low at or below -12 C, a high at or above 37 C. One signal per kind per local day, with urgency `medium` (the producer allowlist for urgent stays empty), expiring an hour after the window ends. The wording is generated here from numbers, not from web text, so it may be spoken plainly; the judge decides whether it matters. Only the area name leaves the machine.

**2. News from Google News RSS, topics from the user.** Off by default (`SUTRA_NEWS=on`). Topics are the user's approved interests plus any in `SUTRA_NEWS_TOPICS`. At most one roundup a day, on the topic fetched longest ago, only while the `news` bar is below 0.8. Up to three headlines with their source names are kept as the signal summary. Headlines are web text and untrusted: they enter the judge as data, the teaser is written in code and names only the topic, and they are given to the user only after yes, inside an untrusted block. Acceptance lowers the bar, ignoring or declining raises it, as for idle research.

**3. A news signal is treated like a research finding.** The topic is an approved interest, so it counts as connected; the producer already applied the bar, so no second benefit bar; the style is always an ask. This reuses the research path and adds only the `news` source.

**4. Local activities through idle research.** With a home area, the idle researcher's topic list gains one built-in topic, "local events and things to do", and the picker is told the area may appear in a brief for local topics only. The brief checks are unchanged: no emails, numbers, money or addresses.

**5. Units.** The numbers are metric internally and spoken in imperial by default (`SUTRA_UNITS=metric` to change).

**6. Morning brief as a tool.** A read-only local tool `morning_brief` returns plain lines for today: reminders due, plans for today and tomorrow, the weather outlook, and any research finding waiting. It makes no change and the model turns it into speech. It is not scheduled; the user asks.

**7. Polling.** A background pass every 30 minutes checks weather (if an area is set) and news (if on). Failures are quiet and retried; no feature calls out unless its setting is on.

## Risks

- A feed outage or a changed format: every fetch is guarded, parsing is defensive, and a failure just means no signal.
- Headlines containing instructions: handled as untrusted data, never spoken without asking.
- The area is personal: it is opt-in, only the city name goes out, and `/feeds` says so.
