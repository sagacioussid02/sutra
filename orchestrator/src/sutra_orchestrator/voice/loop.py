"""The voice loop: listen, ``respond()``, speak, and keep listening while work runs.

While a request is being worked on the loop stays listening. If you speak, the
request keeps going as a background job (a separate conversation lane) and your new
question is answered right away. Finished jobs are never announced unprompted: the
loop asks first, and speaks the result only after you agree.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..classifier import AFFIRM, DENY
from ..orchestrator import Orchestrator
from .types import Engines, Recorder, Transcript, VoiceError

log = logging.getLogger("sutra_orchestrator")

DEFAULT_FILLERS = (
    "Hmm, one sec.",
    "Okay, let me look.",
    "Mm, give me a moment.",
    "Yeah, just checking.",
    "Let me think.",
    "Sure, one sec.",
)
WAIT_NOTICES = (
    "This one's taking a bit. I'm still on it, so feel free to ask me something else.",
    "Still working on that. Ask me something else if you like, and I'll come back to this.",
)
BUSY_LINE = "I'm already working on a couple of things. Give me a moment."
CAME_BACK_PHRASES = ("came back", "any update", "anything back", "is it done", "done yet")


@dataclass
class VoiceSettings:
    min_confidence: float = 0.5
    reask_limit: int = 2
    filler_delay: float = 1.0
    wait_notice_delay: float = 4.0
    max_background: int = 2
    conversation: bool = True
    fillers: tuple[str, ...] = DEFAULT_FILLERS
    record_dir: Path | None = None
    stream: bool = False  # speak the reply sentence by sentence while the model writes it
    barge_in: bool = False  # speak-over: stop talking when the user starts (headphones only)


class Streamed(str):
    """A finished reply that was already being spoken, sentence by sentence, while it was written."""

    spoken: list[str]
    cut: bool  # the user spoke over it: the rest is not to be said

    def remainder(self) -> str:
        """What is left to say after the streamed sentences (an appended offer, say).

        Sentences spoken from an earlier model step (a lead-in before a tool call) are not part of the
        reply, so the match may begin at a later spoken sentence. If no match is found the whole reply is
        spoken: better to repeat than to lose any of it.
        """
        full = " ".join(str(self).split())
        for i in range(len(self.spoken) + 1):
            said = " ".join(" ".join(self.spoken[i:]).split())
            if full.startswith(said):
                return full[len(said) :].strip()
        return full


@dataclass
class Job:
    label: str
    utterance: str
    lane: Orchestrator
    task: asyncio.Future
    plain: bool = False  # a research run: its result never needs the lane's confirmation


@dataclass
class Notice:
    job: Job
    kind: str  # "result", "confirm", or "error"
    reply: str
    declined: bool = False


@dataclass
class _State:
    private: bool
    doubtful: int = 0
    filler_index: int = 0
    notice_index: int = 0


def _label(utterance: str) -> str:
    words = utterance.strip().rstrip("?.!").split()
    return " ".join(words[:8])


class VoiceSession:
    def __init__(
        self,
        orchestrator: Orchestrator,
        recorder: Recorder,
        cloud: Engines | None,
        local: Engines,
        settings: VoiceSettings,
        *,
        start_private: bool = False,
        read: Callable[[str], Awaitable[str]] | None = None,
        out: Callable[[str], None] = print,
        on_reminder_spoken: Callable[[object], None] | None = None,
    ) -> None:
        self._fg = orchestrator
        self._recorder = recorder
        self._cloud = cloud
        self._local = local
        self._s = settings
        self._read = read or _read_line
        self._out = out
        self._state = _State(private=start_private or cloud is None)
        self._speak_lock = asyncio.Lock()
        self._background: set[asyncio.Task] = set()
        self._jobs: list[Job] = []
        self._ready: deque[Notice] = deque()
        self._offer: Notice | None = None
        self._awaiting: Orchestrator | None = None  # lane whose held action the user is answering
        self._notify = asyncio.Event()
        self._interests = None  # InterestService, attached by the caller
        self._i_offer = None  # the interest question currently put to the user
        self._offers = None  # OffersService, attached by the caller
        self._reminders: deque[tuple[object, str, bool]] = deque()
        self._on_reminder_spoken = on_reminder_spoken
        self._read_task: asyncio.Future | None = None
        self._barge_in = settings.barge_in
        self._last_cut = False
        self._stt_seconds = 0.0
        self._first_words_at: float | None = None

    @property
    def engines(self) -> Engines:
        return self._local if self._state.private else self._cloud  # type: ignore[return-value]

    def attach_interests(self, service) -> None:
        """Let new interest proposals, changes and check-ins be asked about at quiet moments."""
        self._interests = service
        service.set_on_offer(self._notify.set)

    def attach_offers(self, service) -> None:
        """Let ready outside signals be said at quiet moments, in words the judge chose."""
        self._offers = service
        service.set_on_ready(self._notify.set)

    async def _maybe_timely(self) -> bool:
        """Say a ready timely offer if the moment is quiet. The answer is read by the next turn."""
        if (
            self._offers is None
            or self._i_offer is not None
            or self._offer is not None
            or self._fg.open_offer is not None
            or self._fg.pending is not None
        ):
            return False
        notice = self._offers.ready_notice()
        if notice is None or not notice.teaser:
            return False
        self._fg.set_open_offer(notice)
        self._out(f"sutra> {notice.teaser}")
        await self._say(notice.teaser)
        return True

    async def _maybe_interest_offer(self) -> bool:
        if self._interests is None or self._i_offer is not None or self._offer is not None:
            return False
        offer = self._interests.next_offer()
        if offer is None:
            return False
        self._i_offer = offer
        self._out(f"sutra> {offer.line}")
        await self._say(offer.line)
        return True

    async def _handle_interest_offer(self, text: str) -> bool:
        """Act on the answer to an interest question. True if the reply was consumed."""
        offer, self._i_offer = self._i_offer, None
        assert offer is not None and self._interests is not None
        t = text.lower()
        if any(p in t for p in ("not now", "not right now", "later", "maybe later")):
            outcome = "later"
        else:
            label = await self._fg.classify_reply(offer.line, text)
            outcome = {AFFIRM: "yes", DENY: "no"}.get(label)
        if outcome is None:
            self._interests.answer(offer, "later")
            return False  # something else entirely: treat it as a normal request
        reply = self._interests.answer(offer, outcome)
        self._out(f"sutra> {reply}")
        await self._say(reply)
        return True

    def busy(self) -> bool:
        """True while a background job runs or a question to the user is still open."""
        return (
            any(not j.task.done() for j in self._jobs)
            or self._offer is not None
            or self._i_offer is not None
            or self._fg.open_offer is not None
        )

    def can_start_job(self) -> bool:
        return len(self._jobs) < self._s.max_background

    def adopt_research(self, label: str, task: str, work: asyncio.Future) -> None:
        """Track a delegated research run as a background job, announced after asking."""
        job = Job(label, task, self._fg, work, plain=True)
        self._jobs.append(job)
        work.add_done_callback(lambda t, j=job: self._job_done(j, t))

    def deliver_reminder(self, entry: object, text: str, late: bool = False) -> None:
        """Queue a fired reminder. It is spoken at the next quiet moment, not asked about."""
        self._reminders.append((entry, text, late))
        self._notify.set()

    async def _speak_reminders(self) -> None:
        """Say queued reminders. Only called when nobody is talking and nothing is recording."""
        while self._reminders:
            entry, text, late = self._reminders.popleft()
            line = (
                f"Sorry, this one is late. You asked me to remind you: {text}."
                if late
                else f"Reminder: {text}."
            )
            self._out(f"sutra> {line}")
            await self._say(line)
            if self._on_reminder_spoken is not None:
                self._on_reminder_spoken(entry)

    # ------------------------------------------------------------------ main loop

    async def run(self) -> None:
        self._recorder.check()
        how = "it stops when you stop talking" if self._recorder.auto_stop else "Enter again to stop"
        self._out(
            f"Voice is on ({self.engines.label}). Enter = start talking ({how}), "
            "p = switch private/cloud, b = interrupting on/off, q = quit."
        )
        self._out(
            "  Interrupting is "
            + ("on: just start talking while I speak." if self._barge_in else "off (press b to turn it on; use headphones, or I will hear myself).")
        )
        while True:
            try:
                cmd = (await self._next_command()).strip().lower()
            except (EOFError, KeyboardInterrupt):
                break
            if cmd in ("q", "quit", "exit"):
                break
            if cmd == "p":
                await self._toggle_private()
                continue
            if cmd == "b":
                self._toggle_barge_in()
                continue
            if cmd:
                continue
            await self._conversation()

    async def _next_command(self) -> str:
        """Wait for a typed command, but speak up (after asking) if background work finishes."""
        if self._read_task is None:
            self._read_task = asyncio.ensure_future(self._read("[Enter to talk]> "))
        while True:
            if self._reminders:
                await self._speak_reminders()
            waiter = asyncio.ensure_future(self._notify.wait())
            await asyncio.wait({self._read_task, waiter}, return_when=asyncio.FIRST_COMPLETED)
            waiter.cancel()
            if self._read_task.done():
                task, self._read_task = self._read_task, None
                return task.result()
            self._notify.clear()
            if self._next_offerable() is not None or (
                self._interests is not None and self._interests.next_offer() is not None
            ):
                await self._conversation(announce=True)
            elif self._offers is not None and self._offers.has_ready():
                await self._conversation(announce=True)

    async def _conversation(self, announce: bool = False) -> None:
        """Take turns. In conversation mode keep listening after each reply until you go quiet."""
        try:
            if announce and not await self._maybe_offer():
                if not await self._maybe_timely():
                    await self._maybe_interest_offer()
            carry: Transcript | None = None
            while True:
                try:
                    answered, carry = await self._turn(carry)
                except VoiceError as exc:
                    self._out(f"  {exc}")
                    return
                if carry is not None:
                    continue
                if self._reminders:
                    await self._speak_reminders()  # between turns: nobody is talking
                if not (answered and self._s.conversation and self._recorder.auto_stop):
                    return
        finally:
            self._recorder.release()  # nothing is captured while idle
            if self._offer is not None:  # asked, but got no answer: keep it for later
                self._offer.declined = True
                self._offer = None
            if self._i_offer is not None and self._interests is not None:
                self._interests.answer(self._i_offer, "later")
                self._i_offer = None

    def _in_background(self, coro) -> None:
        task = asyncio.ensure_future(coro)
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def close(self) -> None:
        """Wait for background jobs and memory work so nothing is lost on exit."""
        for j in self._jobs:
            if j.plain:
                j.task.cancel()  # a research run is recorded as interrupted, not waited for
        pending = [j.task for j in self._jobs]
        if pending:
            self._out(f"  waiting for {len(pending)} background job(s) to finish...")
            await asyncio.gather(*pending, return_exceptions=True)
        if self._background:
            await asyncio.gather(*self._background, return_exceptions=True)

    async def _toggle_private(self) -> None:
        if self._cloud is None:
            self._out("  Cloud voice isn't set up (no OPENAI_API_KEY), so this is already private.")
            return
        self._state.private = not self._state.private
        label = self.engines.label
        self._out(f"  Now using {label}.")
        await self._say("Okay, switched.")

    # ----------------------------------------------------------------------- listen

    async def _listen_once(self) -> Transcript | None:
        """Record one utterance and transcribe it. None means nothing was heard."""
        self._recorder.start()
        try:
            if self._recorder.auto_stop:
                await asyncio.to_thread(self._recorder.wait_done)
            else:
                self._out("  listening... press Enter when you're done")
                await self._read("")
        finally:
            wav = self._recorder.stop()
        if not wav:
            return None
        self._save_audio(wav)
        started = time.perf_counter()
        heard = await self.engines.transcriber.transcribe(wav)
        self._stt_seconds = time.perf_counter() - started
        return heard

    async def _stop_listening(self, listen: asyncio.Future | None) -> Transcript | None:
        """Abort a recording in progress (so we can speak). Returns anything already heard."""
        if listen is None:
            return None
        self._recorder.cancel()
        return await listen

    def _is_interruption(self, t: Transcript | None) -> bool:
        if t is None or t.confidence < self._s.min_confidence:
            return False
        return len(t.text.split()) >= 2

    # ------------------------------------------------------------------------ turn

    async def _turn(self, carry: Transcript | None = None) -> tuple[bool, Transcript | None]:
        """One exchange. Returns (answered, utterance that interrupted it, if any)."""
        transcript = carry
        if transcript is None:
            if self._recorder.auto_stop:
                self._out("  listening...")
            transcript = await self._listen_once()
        if transcript is None:
            self._out("  I didn't hear anything.")
            return False, None
        text = transcript.text.strip()
        if text:
            self._out(f"you> {text}")

        if self._offer is not None and text and await self._handle_offer(text):
            return True, None
        if self._i_offer is not None and text and await self._handle_interest_offer(text):
            return True, None
        if text and self._asks_what_came_back(text) and await self._reoffer():
            return True, None

        lane = self._awaiting or self._fg
        if lane.pending is not None:
            if not await self._confirmation_ok(lane, text, transcript.confidence):
                return True, None
            await self._say(f"I heard: {text}.")
        elif not text:
            self._out("  I didn't catch any words.")
            return False, None

        asked_at = time.perf_counter()
        reply, interrupted = await self._respond(
            lane, text, low_confidence=transcript.confidence < self._s.min_confidence
        )
        if reply is not None:
            think = time.perf_counter() - asked_at
            self._out(f"sutra> {reply}")
            spoken_over = None
            if isinstance(reply, Streamed):
                if not reply.cut:
                    rest = reply.remainder()
                    if rest:
                        spoken_over = await self._say_reply(rest)
            else:
                spoken_over = await self._say_reply(reply)
            first_words = self._first_words_at if self._first_words_at is not None else think
            log.debug(
                "turn timing: transcribe %.2fs, reply finished %.2fs, first words %.2fs after the request",
                self._stt_seconds, think, first_words,
            )
            if interrupted is None and self._is_interruption(spoken_over):
                interrupted = spoken_over  # what they said over me is their next turn
            # Memory work (like extracting what you said) must not delay listening.
            self._in_background(lane.flush())
            self._show_pending(lane)
            if lane is self._awaiting and lane.pending is None:
                self._awaiting = None
        if interrupted is None and not await self._maybe_offer():  # a natural gap: now is the time to ask
            if not await self._maybe_timely():
                await self._maybe_interest_offer()
        return True, interrupted

    def _show_pending(self, lane: Orchestrator) -> None:
        pending = lane.pending
        if pending is not None:
            self._out(f"  pending: {pending.description}")
            self._out(f"  expires: {pending.expires_at.astimezone().strftime('%H:%M:%S')}")

    async def _confirmation_ok(self, lane: Orchestrator, text: str, confidence: float) -> bool:
        """Gate a reply to a held action. A doubtful transcript never reaches respond()."""
        if text and confidence >= self._s.min_confidence:
            self._state.doubtful = 0
            return True
        self._state.doubtful += 1
        if self._state.doubtful > self._s.reask_limit:
            self._state.doubtful = 0
            lane.cancel_pending()
            if lane is self._awaiting:
                self._awaiting = None
            self._out("  dropped the pending action; nothing was done")
            await self._say("Okay, I'll leave that for now. Nothing was done.")
        else:
            await self._say("Sorry, I didn't catch that. Was that a yes or a no?")
        return False

    # ------------------------------------------------------------- doing the work

    async def _respond(
        self, lane: Orchestrator, text: str, *, low_confidence: bool = False
    ) -> tuple[str | None, Transcript | None]:
        """Run the request. Returns (reply or None if detached, utterance that interrupted it)."""
        if not self._recorder.auto_stop:
            return await self._respond_with_filler(lane, text, low_confidence), None

        loop = asyncio.get_running_loop()
        sentences: asyncio.Queue[str] = asyncio.Queue()
        stream = self._s.stream
        extra = {"on_text": sentences.put_nowait} if stream else {}
        work = asyncio.ensure_future(lane.respond(text, low_confidence=low_confidence, **extra))
        started = loop.time()
        self._first_words_at = None
        timers: list[tuple[float, str]] = []
        if self._s.filler_delay > 0 and self._s.fillers:
            timers.append((self._s.filler_delay, "filler"))
        if self._s.wait_notice_delay > 0:
            timers.append((self._s.wait_notice_delay, "notice"))
        timers.sort()
        return await self._wait_for_reply(lane, text, work, sentences, stream, timers, started, loop)

    async def _wait_for_reply(
        self, lane, text, work, sentences, stream, timers, started, loop
    ) -> tuple[str | None, Transcript | None]:
        """Wait for the reply, listening for the user and speaking fillers meanwhile; with streaming on,
        hand over to speaking as soon as the first sentence is written."""
        listen: asyncio.Future | None = None
        first: asyncio.Future | None = None
        try:
            while True:
                if listen is None and not work.done():
                    listen = asyncio.ensure_future(self._listen_once())
                if stream and first is None:
                    first = asyncio.ensure_future(sentences.get())
                wait_for = {work} | ({listen} if listen else set()) | ({first} if first else set())
                timeout = max(0.0, timers[0][0] - (loop.time() - started)) if timers else None
                done, _ = await asyncio.wait(wait_for, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)

                if first is not None and first in done:
                    # The reply has started to arrive: stop listening (as a filler would) and speak as it writes.
                    sentence, first = first.result(), None
                    heard = await self._stop_listening(listen)
                    listen = None
                    if self._is_interruption(heard) and len(self._jobs) < self._s.max_background:
                        self._detach(lane, text, work)
                        return None, heard
                    self._first_words_at = loop.time() - started
                    return await self._speak_stream(work, sentences, sentence)

                if work in done:
                    late = await self._stop_listening(listen)
                    listen = None
                    return work.result(), (late if self._is_interruption(late) else None)

                heard: Transcript | None = None
                if listen is not None and listen in done:
                    heard, listen = listen.result(), None
                elif not done:  # a timer fired: stop recording so the mic doesn't hear us speak
                    heard = await self._stop_listening(listen)
                    listen = None

                if self._is_interruption(heard):
                    if len(self._jobs) >= self._s.max_background:
                        await self._say(BUSY_LINE)
                    else:
                        self._detach(lane, text, work)
                        return None, heard
                if not done:
                    await self._say(self._timer_line(timers.pop(0)[1]))
        finally:
            if first is not None and not first.done():
                first.cancel()  # never leave a waiter on the sentence queue behind

    async def _speak_stream(
        self, work: asyncio.Future, sentences: asyncio.Queue, first: str
    ) -> tuple[str, Transcript | None]:
        """Speak sentences as the model writes them. A cut-in stops it; the model is left to finish quietly.

        If anything goes wrong here the plain reply is returned, to be spoken whole, so streaming can
        never leave Sutra mute.
        """
        spoken: list[str] = []
        cut, cut_heard = False, None
        try:
            sentence: str | None = first
            while sentence is not None:
                heard = await self._say_reply(sentence)
                spoken.append(sentence)
                if self._last_cut:
                    cut, cut_heard = True, heard
                    break
                sentence = await self._next_sentence(sentences, work)
        except Exception:
            log.warning("streamed speech failed; speaking the whole reply instead", exc_info=True)
            return await work, None
        reply = Streamed(await work)
        reply.spoken, reply.cut = spoken, cut
        return reply, (cut_heard if self._is_interruption(cut_heard) else None)

    @staticmethod
    async def _next_sentence(sentences: asyncio.Queue, work: asyncio.Future) -> str | None:
        """The next sentence to speak, or None once the reply is complete and everything was spoken."""
        while True:
            if not sentences.empty():
                return sentences.get_nowait()
            if work.done():
                return None
            getter = asyncio.ensure_future(sentences.get())
            await asyncio.wait({getter, work}, return_when=asyncio.FIRST_COMPLETED)
            if getter.done():
                return getter.result()
            getter.cancel()
            await asyncio.gather(getter, return_exceptions=True)

    def _timer_line(self, kind: str) -> str:
        if kind == "filler":
            line = self._s.fillers[self._state.filler_index % len(self._s.fillers)]
            self._state.filler_index += 1
            return line
        line = WAIT_NOTICES[self._state.notice_index % len(WAIT_NOTICES)]
        self._state.notice_index += 1
        return line

    async def _respond_with_filler(
        self, lane: Orchestrator, text: str, low_confidence: bool = False
    ) -> str:
        """Press-Enter mode cannot listen while working, so only the short filler applies."""
        started = False

        async def filler() -> None:
            nonlocal started
            await asyncio.sleep(self._s.filler_delay)
            if not self._s.fillers:
                return
            async with self._speak_lock:
                started = True
                await self.engines.speaker.say(self._timer_line("filler"))

        task = asyncio.create_task(filler())
        try:
            return await lane.respond(text, low_confidence=low_confidence)
        finally:
            if started:
                try:
                    await task
                except VoiceError:
                    pass
            else:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    # ---------------------------------------------------------- background jobs

    def _detach(self, lane: Orchestrator, utterance: str, work: asyncio.Future) -> None:
        job = Job(_label(utterance), utterance, lane, work)
        self._jobs.append(job)
        work.add_done_callback(lambda t, j=job: self._job_done(j, t))
        if lane is self._fg:
            self._fg = lane.fork()  # the main conversation carries on, without the unfinished request
        elif lane is self._awaiting:
            self._awaiting = None
        self._out(f"  (still working on: {job.label}. Carrying on with your new question.)")

    def _job_done(self, job: Job, task: asyncio.Future) -> None:
        if job in self._jobs:
            self._jobs.remove(job)
        if task.cancelled():
            return  # shutting down: there is nobody to tell
        try:
            reply = task.result()
            kind = "confirm" if job.lane.pending is not None and not job.plain else "result"
        except Exception:
            reply, kind = "That didn't work out.", "error"
        self._in_background(job.lane.flush())
        self._ready.append(Notice(job, kind, reply))
        self._notify.set()

    def _next_offerable(self, include_declined: bool = False) -> Notice | None:
        busy = self._fg.pending is not None or self._awaiting is not None
        for n in self._ready:
            if n.declined and not include_declined:
                continue
            if n.kind == "confirm" and busy:
                continue  # only one action may await confirmation at a time
            return n
        return None

    async def _maybe_offer(self, include_declined: bool = False) -> bool:
        if self._offer is not None:
            return False
        notice = self._next_offerable(include_declined)
        if notice is None:
            return False
        self._offer = notice
        label = notice.job.label
        if notice.kind == "confirm":
            line = f"I need your go-ahead on something for your earlier request, {label}. Want to hear it?"
        elif notice.kind == "error":
            line = f"Your earlier request, {label}, didn't work out. Want the details?"
        else:
            line = f"By the way, I've got an answer to your earlier request, {label}. Want it now?"
        self._out(f"sutra> {line}")
        await self._say(line)
        return True

    async def _handle_offer(self, text: str) -> bool:
        """Act on the reply to 'want it now?'. Returns True if the reply was consumed."""
        notice, self._offer = self._offer, None
        assert notice is not None
        label = await self._fg.classify_reply(
            f"Hear the result of your earlier request: {notice.job.label}", text
        )
        if label == AFFIRM:
            self._ready.remove(notice)
            self._out(f"sutra> {notice.reply}")
            await self._say(notice.reply)
            if notice.kind == "confirm":
                self._awaiting = notice.job.lane
                self._show_pending(notice.job.lane)
            else:
                self._fg.note_background_result(notice.job.utterance, notice.reply)
            return True
        notice.declined = True
        if label == DENY:
            await self._say("Okay, later.")
            return True
        return False  # something else entirely: treat it as a normal request

    def _asks_what_came_back(self, text: str) -> bool:
        t = text.lower()
        return any(p in t for p in CAME_BACK_PHRASES)

    async def _reoffer(self) -> bool:
        if self._offer is not None:
            return False
        if await self._maybe_offer(include_declined=True):
            return True
        if self._jobs:
            await self._say("Still working on it.")
        else:
            await self._say("Nothing has come back yet.")
        return True

    # ------------------------------------------------------------------- helpers

    def _toggle_barge_in(self) -> None:
        self._barge_in = not self._barge_in
        self._out(
            "  Interrupting is on: start talking while I speak and I'll stop. Use headphones, "
            "or I will hear my own voice and cut myself off."
            if self._barge_in
            else "  Interrupting is off."
        )

    async def _say_reply(self, text: str) -> Transcript | None:
        """Speak a reply; if interrupting is on and the user starts talking, stop and return what they said.

        The microphone listens while the speaker plays. A burst of speech (longer than a cough) cuts the
        voice off at once; the person is then heard out and transcribed like any other turn. Returns None
        if the reply played to the end, or nothing usable was heard.
        """
        self._last_cut = False
        if not (self._barge_in and self._recorder.auto_stop):
            await self._say(text)
            return None
        async with self._speak_lock:
            speaker = self.engines.speaker
            try:
                self._recorder.start(barge_in=True)
            except (TypeError, VoiceError) as exc:  # no mic, or a recorder without this mode: just speak
                self._out(f"  {exc}")
                with contextlib.suppress(VoiceError):
                    await speaker.say(text)
                return None
            speak = asyncio.ensure_future(speaker.say(text))
            cut = False
            try:
                while not speak.done():
                    await asyncio.sleep(0.03)  # first let the voice start, then listen for the user
                    if not speak.done() and self._recorder.speech_started:
                        cut = True
                        break
                if cut:
                    speak.cancel()
                    with contextlib.suppress(asyncio.CancelledError, VoiceError):
                        await speak
                    self._out("  (you cut in)")
                    await asyncio.to_thread(self._recorder.wait_done)  # hear them out
                else:
                    await speak
            except VoiceError as exc:
                self._out(f"  {exc}")
            except asyncio.CancelledError:
                speak.cancel()
                raise
            finally:
                if not cut:
                    self._recorder.cancel()
                wav = self._recorder.stop()
            self._last_cut = cut
            if not cut or not wav:
                return None
            self._save_audio(wav)
            return await self.engines.transcriber.transcribe(wav)

    async def _say(self, text: str) -> None:
        async with self._speak_lock:
            try:
                await self.engines.speaker.say(text)
            except VoiceError as exc:
                self._out(f"  {exc}")

    def _save_audio(self, wav: bytes) -> None:
        if self._s.record_dir is None:
            return
        self._s.record_dir.mkdir(parents=True, exist_ok=True)
        (self._s.record_dir / f"turn-{int(time.time() * 1000)}.wav").write_bytes(wav)


async def _read_line(prompt: str) -> str:
    return await asyncio.to_thread(input, prompt)
