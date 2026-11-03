## 1. Confirmations and detection

- [x] 1.1 `i18n.py` detection and fixed-reply table; classifier normalization keeps Devanagari, explicit Hindi phrase sets, mixed-script guard
- [x] 1.2 Classifier prompt with Hindi/Hinglish; about 60 labelled rows; tests; live eval run
- [x] 1.3 Orchestrator and voice use localized fixed replies

## 2. Reminders and interpreter

- [x] 2.1 `reminders/hindi.py` front end, Hindi replies and answers
- [x] 2.2 `translate.py` interpreter mode; orchestrator handling (no tools, no offers, no humor, private)
- [x] 2.3 Tests

## 3. Voice and safety nets

- [x] 3.1 TTS style line, Hindi local voice, local STT language
- [x] 3.2 Hindi wording in heavy/upset/vent/crisis lists; humor off for Hindi turns
- [x] 3.3 Tests, README, live checks
