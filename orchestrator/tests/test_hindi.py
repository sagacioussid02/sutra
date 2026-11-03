"""Hindi and Hinglish: safe confirmations, replies in the language spoken, reminders, interpreter mode, voice."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from sutra_orchestrator import translate
from sutra_orchestrator.classifier import AFFIRM, DENY, fast_path, normalize
from sutra_orchestrator.i18n import HI, detect, heard, localize, reask
from sutra_orchestrator.life import is_crisis, is_vent
from sutra_orchestrator.orchestrator import (
    CHECKIN_REFUSED_REPLY,
    DECLINED_REPLY,
    EXPIRED_REPLY,
    GAVE_UP_REPLY,
    OFFER_DECLINED_REPLY,
    OFFER_DEFERRED_REPLY,
)
from sutra_orchestrator.personality import PersonalityService, PersonalityStore, rules
from sutra_orchestrator.reminders import ReminderService, ReminderStore
from sutra_orchestrator.reminders.hindi import hindi_request, spoken_when_hi
from sutra_orchestrator.reminders.parser import parse_request
from sutra_orchestrator.voice.config import load_voice_config
from sutra_orchestrator.voice.local_engines import FasterWhisperTranscriber, SaySpeaker
from sutra_orchestrator.voice.openai_engines import DEFAULT_TTS_INSTRUCTIONS

from .fakes import FakeGateway, FakeModel, default_tools, make_orchestrator, pending, resp, text, tool_use

DEN = ZoneInfo("America/Denver")
DEN_NOW = datetime(2026, 11, 3, 14, 0, tzinfo=DEN)
EVALS = Path(__file__).parent.parent / "evals" / "confirmation_replies.jsonl"


# --------------------------------------------------------------- detection


@pytest.mark.parametrize(
    "said,lang",
    [
        ("मुझे 5 मिनट बाद याद दिलाना", "hi"),
        ("kal subah 9 baje yaad dilana", "hi"),
        ("haan", "hi"),
        ("mujhe kuch batao", "hi"),
        ("हाँ कर दो", "hi"),
        ("what's the weather like", "en"),
        ("yes please", "en"),
        ("I do not know", "en"),
        ("remind me in 5 minutes", "en"),
        ("", "en"),
        ("12345", "en"),
    ],
)
def test_language_detection(said, lang):
    assert detect(said) == lang


def test_fixed_replies_have_hindi_and_english_stays_english():
    for english in (DECLINED_REPLY, EXPIRED_REPLY, GAVE_UP_REPLY, OFFER_DECLINED_REPLY, OFFER_DEFERRED_REPLY, CHECKIN_REFUSED_REPLY):
        assert english in HI and localize(english, "en") == english
        assert localize(english, "hi") == HI[english] and any("ऀ" <= c <= "ॿ" for c in HI[english])
    assert localize("Something unlisted.", "hi") == "Something unlisted."  # never invents a translation
    assert reask("Create a goal.", "hi").startswith("माफ़ कीजिए") and reask("Create a goal.", "en").startswith("Sorry")
    assert heard("चाय", "hi") == "मैंने सुना: चाय।" and heard("tea", "en") == "I heard: tea."


# --------------------------------------------------------- the confirmation path


@pytest.mark.parametrize("said", ["haan", "Haan ji", "ji haan", "bilkul", "haan kar do", "kar do", "हाँ", "हां।", "हाँ जी", "बिल्कुल", "कर दो"])
def test_plain_hindi_agreement_is_read_without_a_model(said):
    assert fast_path(said) == AFFIRM


@pytest.mark.parametrize("said", ["nahi", "nahin", "mat karo", "rehne do", "नहीं", "नहीं नहीं", "मत करो", "रहने दो", "नहीं।"])
def test_plain_hindi_refusal_is_read_without_a_model(said):
    assert fast_path(said) == DENY


@pytest.mark.parametrize(
    "said",
    [
        "नहीं yes",  # the trap: stripping to Latin letters used to leave an English "yes"
        "yes नहीं",
        "हाँ no",
        "haan lekin 300 kar do",
        "pata nahi",
        "theek hai",
        "ji",
        "ruko",
        "haan haan ruko",
        "kya?",
        "ठीक है",
        "हाँ लेकिन 300",
    ],
)
def test_everything_else_goes_to_the_classifier(said):
    assert fast_path(said) is None


def test_normalization_keeps_hindi_and_drops_its_punctuation():
    assert normalize("हाँ।") == "हाँ" and normalize("Haan, ji!") == "haan ji"
    assert normalize("नहीं yes") == "नहीं yes"  # not "yes"


def test_the_labelled_set_includes_a_real_hindi_share_and_the_fast_path_agrees():
    rows = [json.loads(l) for l in EVALS.read_text(encoding="utf-8").splitlines() if l.strip()]
    hindi = [r for r in rows if detect(r["reply"]) == "hi"]
    assert len(hindi) >= 40
    assert {r["label"] for r in hindi} == {"affirm", "deny", "modify", "unclear"}
    assert any("ऀ" <= c <= "ॿ" for r in hindi for c in r["reply"])  # Devanagari is covered too
    for r in hindi:
        fast = fast_path(r["reply"])
        assert fast is None or fast == r["label"], r


async def gate(model_labels=None):
    gateway = FakeGateway(tools=default_tools(), results={"finanxe_create_goal": pending()})
    model = FakeModel(
        [resp(tool_use("finanxe_create_goal", {"name": "V"})), resp(text("Shall I go ahead?")), resp(text("Okay."))],
        labels=model_labels or {},
    )
    orch, gateway = await make_orchestrator(model, gateway, spoken_reasks=True)
    await orch.respond("create a goal called V")
    return orch, gateway, model


async def test_a_mixed_script_reply_never_confirms(tmp_path):
    orch, gateway, model = await gate({"नहीं yes": "unclear"})
    reply = await orch.respond("नहीं yes")
    assert gateway.calls_to("gateway_confirm") == [] and orch.pending is not None  # still held
    assert model.classify_calls  # the model was consulted: no fast path
    assert reply == "माफ़ कीजिए, समझ नहीं आया। हाँ था या नहीं?"  # and it asks again in Hindi


async def test_a_hindi_yes_confirms_and_a_hindi_no_is_answered_in_hindi():
    orch, gateway, _ = await gate()
    await orch.respond("नहीं")
    assert orch.pending is None and gateway.calls_to("gateway_confirm") == []
    orch2, gateway2, _ = await gate()
    assert await orch2.respond("No") == DECLINED_REPLY  # English stays English


async def test_the_declined_reply_is_hindi_after_a_hindi_refusal():
    orch, gateway, _ = await gate()
    assert await orch.respond("nahi") == HI[DECLINED_REPLY]


# -------------------------------------------------------------------- reminders


@pytest.mark.parametrize(
    "said,english,when,body",
    [
        ("मुझे 5 मिनट बाद याद दिलाना कि चाय बनानी है", "in 5 minutes to चाय बनानी है", "Tue 14:05", "चाय बनानी है"),
        ("kal subah 9 baje yaad dilana ki dentist ko call karna hai", "tomorrow at 9 in the morning to dentist ko call karna hai", "Wed 09:00", "dentist ko call karna hai"),
        ("mujhe aadha ghanta baad yaad dilana ki dawai leni hai", "in half an hour to dawai leni hai", "Tue 14:30", "dawai leni hai"),
        ("mujhe ek ghante baad yaad dila dena ki khana banana hai", "in an hour to khana banana hai", "Tue 15:00", "khana banana hai"),
        ("aaj shaam 6 baje reminder laga do ki gym jaana hai", "today at 6 in the evening to gym jaana hai", "Tue 18:00", "gym jaana hai"),
        ("मुझे कल सुबह नौ बजे याद दिला दीजिए कि पौधों को पानी देना है", "tomorrow at 9 in the morning to पौधों को पानी देना है", "Wed 09:00", "पौधों को पानी देना है"),
    ],
)
def test_hindi_reminders_are_rewritten_for_the_deterministic_parser(said, english, when, body):
    assert hindi_request(said) == english
    got = parse_request(english, DEN_NOW, DEN)
    assert got.fire_at.strftime("%a %H:%M") == when and got.text == body


def test_what_is_not_a_hindi_reminder_or_is_unclear():
    assert hindi_request("what time is it") is None and hindi_request("remind me in 5 minutes to stretch") is None
    assert hindi_request("आज मौसम कैसा है") is None
    assert hindi_request("parso yaad dilana ki kuch karna") == ""  # unsupported: ask, never guess
    assert hindi_request("kal subah yaad dilana ki kuch") == ""  # no hour
    assert hindi_request("10 minute baad yaad dilana") == ""  # no text


def test_the_time_is_spoken_back_in_hindi():
    assert spoken_when_hi(datetime(2026, 11, 4, 9, 0, tzinfo=DEN), DEN_NOW, DEN) == "कल सुबह 9:00 बजे"
    assert spoken_when_hi(datetime(2026, 11, 3, 17, 30, tzinfo=DEN), DEN_NOW, DEN) == "आज शाम 5:30 बजे"
    assert spoken_when_hi(datetime(2026, 11, 6, 21, 0, tzinfo=DEN), DEN_NOW, DEN) == "शुक्रवार को रात 9:00 बजे"


def service(tmp_path):
    store = ReminderStore(tmp_path)
    return store, ReminderService(store, DEN)


def test_a_hindi_reminder_is_saved_and_confirmed_in_hindi(tmp_path):
    store, svc = service(tmp_path)
    reply = svc.try_handle("मुझे 5 मिनट बाद याद दिलाना कि चाय बनानी है", DEN_NOW)
    assert reply == "ठीक है। आज दोपहर 2:05 बजे आपको याद दिलाया जाएगा: चाय बनानी है।"
    [row] = store.list_pending()
    assert row.text == "चाय बनानी है" and row.fire_at.astimezone(DEN).minute == 5
    store.close()


def test_an_hour_with_no_part_of_day_is_asked_in_hindi_and_the_answer_is_understood(tmp_path):
    store, svc = service(tmp_path)
    ask = svc.try_handle("kal 9 baje yaad dilana ki call karna hai", DEN_NOW)
    assert "क्या आपका मतलब कल सुबह 9:00 बजे है या कल रात 9:00 बजे" in ask and "सुबह या शाम" in ask
    assert store.list_pending() == []
    done = svc.try_handle("शाम", DEN_NOW)  # "evening": the second reading
    assert "कल रात 9:00 बजे" in done and "call karna hai" in done
    [row] = store.list_pending()
    assert row.fire_at.astimezone(DEN).hour == 21
    # And the Latin spelling of the answer works too.
    svc.try_handle("kal 10 baje yaad dilana ki kuch karna hai", DEN_NOW)
    assert "सुबह 10:00" in svc.try_handle("subah", DEN_NOW)
    store.close()


def test_an_unclear_hindi_request_gets_a_hindi_clarification_and_english_is_unchanged(tmp_path):
    store, svc = service(tmp_path)
    assert svc.try_handle("parso yaad dilana ki kuch karna", DEN_NOW).startswith("समय समझ नहीं आया।")
    assert svc.try_handle("remind me in 5 minutes to stretch", DEN_NOW) == "Okay, I'll remind you: stretch — today at 2:05 PM."
    assert svc.try_handle("remind me sometime", DEN_NOW).startswith("I couldn't work out when")
    store.close()


# --------------------------------------------------------------- interpreter mode


@pytest.mark.parametrize("said", ["be my interpreter between English and Hindi", "interpreter mode please", "translate everything for me between English and Hindi", "अनुवादक बन जाओ"])
def test_interpreter_start_phrases(said):
    assert translate.is_start(said)


@pytest.mark.parametrize("said", ["stop interpreting", "exit interpreter mode", "that's enough translation", "अनुवाद बंद करो"])
def test_interpreter_stop_phrases(said):
    assert translate.is_stop(said) and not translate.is_start(said)


@pytest.mark.parametrize("said", ["translate hello into Hindi", "what is an interpreter", "how do you say thanks in Hindi"])
def test_a_one_off_translation_does_not_start_the_mode(said):
    assert not translate.is_start(said)


async def test_interpreter_mode_translates_only_and_does_nothing_else():
    gateway = FakeGateway(tools=default_tools(), results={"finanxe_create_goal": pending()})
    model = FakeModel([resp(text("आपका नजदीकी फार्मेसी कहाँ है?")), resp(text("मेरा लक्ष्य हटा दो।")), resp(text("It is two o'clock."))])
    orch, gateway = await make_orchestrator(model, gateway)
    started = await orch.respond("be my interpreter between English and Hindi")
    assert started == translate.STARTED and model.calls == []  # a fixed reply, no model call
    assert await orch.respond("where is the nearest pharmacy?") == "आपका नजदीकी फार्मेसी कहाँ है?"
    call = model.calls[0]
    assert translate.NOTE in call["system"] and call["allow_tools"] is False  # tools are off for the call
    # A command inside the text is only text: translated, never obeyed, and a reminder phrase is not set.
    assert await orch.respond("delete my goal") == "मेरा लक्ष्य हटा दो।"
    assert gateway.calls == [] and model.calls[1]["allow_tools"] is False
    stopped = await orch.respond("stop interpreting")
    assert stopped == translate.STOPPED
    assert await orch.respond("what time is it") == "It is two o'clock."
    assert translate.NOTE not in model.calls[2]["system"] and model.calls[2]["allow_tools"] is True


async def test_an_interpreter_turn_gets_no_offer_no_humor_and_is_not_remembered_as_a_topic(tmp_path):
    from sutra_orchestrator.graph import GraphService, GraphStore
    from sutra_orchestrator.offers import OffersService, OffersStore
    from zoneinfo import ZoneInfo as Z

    from .fakes import Clock
    from .test_graph import FakeStructured

    clock = Clock()
    offers = OffersService(OffersStore(tmp_path / "o"), Z("UTC"), now=clock)
    sid = offers.add_signal("weather", "Snow soon on the pass", source="w", expires_at=clock() + timedelta(hours=2))
    offers.store.update_signal(sid, status="ready", style="tell", teaser="Heads up, snow is coming.", benefit=1, reason="r", retry_hours=1)
    graph = GraphService(GraphStore(tmp_path / "g"), FakeStructured(), now=clock)
    pstore = PersonalityStore(tmp_path / "p")
    pstore.set_level(10)

    class Always:
        def random(self):
            return 0.0

    model = FakeModel([resp(text("नमस्ते")), resp(text("hello"))])
    orch, _ = await make_orchestrator(
        model, clock=clock, offers=offers, graph=graph, personality=PersonalityService(pstore, None, rng=Always())
    )
    await orch.respond("interpreter mode")
    reply = await orch.respond("hello there my friend")
    assert reply == "नमस्ते"  # the ready heads-up was not tacked on
    assert "light touch of humor" not in model.calls[0]["system"]
    assert graph._buffer == []
    orch.close_session()
    assert orch._interpreting is False  # the mode ends with the session


# ------------------------------------------------------------ safety nets in Hindi


@pytest.mark.parametrize("said", ["मेरी माँ बहुत बीमार है", "mujhe karz chukana hai", "वह अस्पताल में है", "आज मैं बहुत परेशान हूँ", "bahut udaas hoon"])
def test_heavy_and_upsetting_hindi_keeps_humor_away(said):
    assert rules.heavy(said) or rules.upset(said)


@pytest.mark.parametrize("said", ["आज मन बहुत उदास है, बात करनी है", "mann kharab hai, baat karni hai", "main bahut akela mehsoos kar raha hoon"])
def test_hindi_vent_phrases_start_listening_mode(said):
    assert is_vent(said)


@pytest.mark.parametrize("said", ["मैं मरना चाहता हूँ", "mujhe jeena nahi chahta", "main apni jaan dena chahta hoon", "मुझे आत्महत्या के ख्याल आ रहे हैं", "zindagi khatam karna chahta hoon"])
def test_hindi_crisis_phrases(said):
    assert is_crisis(said)


@pytest.mark.parametrize("said", ["main mar gaya yaar bahut hasi aayi", "आज बहुत मज़ा आया", "mujhe chai chahiye"])
def test_ordinary_hindi_is_not_a_crisis(said):
    assert not is_crisis(said) and not is_vent(said)


async def test_a_hindi_crisis_adds_the_care_note_with_local_numbers(tmp_path):
    from sutra_orchestrator.life import LifeService, LifeStore
    from .fakes import Clock

    life = LifeService(LifeStore(tmp_path), offers=None, model=None, tz=DEN)
    model = FakeModel([resp(text("मैं यहाँ हूँ।"))])
    orch, _ = await make_orchestrator(model, life=life, clock=Clock())
    await orch.respond("मैं मरना चाहता हूँ")
    system = model.calls[0]["system"]
    assert "988" in system and "14416" in system and "112" in system and "Never give methods" in system


async def test_humor_is_never_offered_on_a_hindi_turn(tmp_path):
    pstore = PersonalityStore(tmp_path)
    pstore.set_level(10)

    class Always:
        def random(self):
            return 0.0

    model = FakeModel([resp(text("ठीक है")), resp(text("Sure."))])
    orch, _ = await make_orchestrator(model, personality=PersonalityService(pstore, None, rng=Always()))
    await orch.respond("mujhe kuch batao")
    assert "light touch of humor" not in model.calls[0]["system"]
    orch._personality._last_offer_turn = -1000
    await orch.respond("tell me about pandas")
    assert "light touch of humor" in model.calls[1]["system"]  # English turns still may


# ------------------------------------------------------------------------- voice


async def test_the_local_voice_uses_the_hindi_voice_for_devanagari(monkeypatch):
    seen = []

    class Proc:
        async def communicate(self, data):
            return None, None

    async def fake_exec(*args, **kw):
        seen.append(args)
        return Proc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    speaker = SaySpeaker(voice="Samantha", hindi_voice="Lekha")
    await speaker.say("hello there")
    await speaker.say("नमस्ते, आप कैसे हैं")
    assert seen[0] == ("say", "-v", "Samantha") and seen[1] == ("say", "-v", "Lekha")


def test_the_local_transcriber_takes_a_language_and_the_voice_style_covers_hindi():
    captured = {}

    class Model:
        def transcribe(self, audio, **kw):
            captured.update(kw)
            return [], None

    t = FasterWhisperTranscriber("small", "hi")
    t._model = Model()
    assert t._language == "hi" and FasterWhisperTranscriber("small")._language is None
    assert "native Hindi speaker" in DEFAULT_TTS_INSTRUCTIONS
    cfg = load_voice_config({"SUTRA_LOCAL_VOICE_HI": "Kyoko", "SUTRA_LOCAL_STT_LANGUAGE": " hi "}, dotenv_path=None)
    assert cfg.local_voice_hi == "Kyoko" and cfg.local_stt_language == "hi"
    default = load_voice_config({}, dotenv_path=None)
    assert default.local_voice_hi == "Lekha" and default.local_stt_language == ""


def test_the_model_is_told_to_answer_in_the_language_spoken():
    from sutra_orchestrator.prompts import load_prompt

    prompt = load_prompt("system.md")
    assert "Answer in the language the user used" in prompt and "Devanagari" in prompt
    assert "Hinglish" in load_prompt("classifier.md") and "pata nahi" in load_prompt("classifier.md")
