## 1. Sources

- [x] 1.1 `feeds/http.py` (guarded fetch), `weather.py` (geocode, forecast, notable conditions, wording), `news.py` (RSS parse)
- [x] 1.2 Tests with canned responses: each condition, once per day, geocode region match, parse, failures

## 2. Service and offers

- [x] 2.1 `FeedService`: polls, dedupe, daily news cap, `news` bar gate, signals
- [x] 2.2 Offers: `news` source treated like research (connected, ask, own bar)
- [x] 2.3 Idle research: home area, local topic
- [x] 2.4 `morning_brief` tool
- [x] 2.5 Tests: signals, bar, untrusted delivery, off means no request, brief

## 3. Control and docs

- [x] 3.1 Config, `/feeds`, wiring, README
- [x] 3.2 Live check: real forecast and real headlines
