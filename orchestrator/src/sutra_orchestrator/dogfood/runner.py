"""Drive one scenario through the production ``Orchestrator.respond`` pipeline, in the sandbox.

Each scenario gets a fresh Orchestrator wired to throwaway stores under the
sandbox root, the run's fake clock, and the recording gateway. The runner
does nothing a client would not do: it calls ``respond`` with the turn's
text and voice-layer context, moves the clock, and sweeps the reminder
scheduler the way its poll loop would. What it collects is an Observation:
every reply, every gateway call, every reminder set and fired, every offer
said. Grading happens elsewhere, against that record.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from ..classifier import IntentClassifier
from ..memstore import SqliteMemory
from ..offers import OffersService
from ..offers.store import OffersStore
from ..orchestrator import Orchestrator, PendingAction
from ..reminders import ReminderScheduler, ReminderService, ReminderStore
from ..reminders.store import InboxRow, ReminderRow
from ..speaker import Addressee, SpeakerSignal
from .profile import FakeClock, Profile, parse_start
from .scenario import Scenario, Step
from .stubs import MUTATING_TOOLS, RecordingGateway

DEFAULT_TZ = "America/New_York"
ADDRESSEE_VERDICT = {
    "sutra": Addressee.ADDRESSED,
    "other-person": Addressee.ELSEWHERE,
    "unclear": Addressee.UNCLEAR,
}
OFFER_SOURCE = "dogfood"


@dataclass
class TurnRecord:
    index: int  # among user steps, from 0
    text: str
    speech_act: str
    addressee: str
    speaker: str | None
    reply: str
    at: datetime
    pending_before: bool
    pending_after: bool
    tool_calls: list[str]  # gateway tool names called during this turn
    executed: int  # gateway_confirm calls during this turn
    offer_topic: str | None  # the unprompted offer appended to this reply, if any


@dataclass
class Observation:
    scenario_id: str
    turns: list[TurnRecord] = field(default_factory=list)
    reminders: list[ReminderRow] = field(default_factory=list)  # every reminder created, as created
    fired: list[InboxRow] = field(default_factory=list)  # every delivery, in order
    executed: int = 0
    gateway_calls: list[str] = field(default_factory=list)
    offers: list[str] = field(default_factory=list)  # topics of offers said, in order
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "turns": [
                {
                    "index": t.index, "text": t.text, "reply": t.reply, "speaker": t.speaker,
                    "pending_before": t.pending_before, "pending_after": t.pending_after,
                    "tool_calls": t.tool_calls, "executed": t.executed, "offer_topic": t.offer_topic,
                }
                for t in self.turns
            ],
            "reminders": [{"text": r.text, "fire_at": r.fire_at.isoformat()} for r in self.reminders],
            "fired": [
                {"text": f.text, "fire_at": f.fire_at.isoformat(), "late": f.late} for f in self.fired
            ],
            "executed": self.executed,
            "gateway_calls": self.gateway_calls,
            "offers": self.offers,
            "error": self.error,
        }


class _Rig:
    """One scenario's assembled system: production services on sandbox stores."""

    def __init__(self, scenario: Scenario, profile: Profile, model: Any, clock: FakeClock) -> None:
        setup = scenario.setup
        self.scenario = scenario
        self.clock = clock
        self.model = model
        self.tz = ZoneInfo(setup.get("tz", DEFAULT_TZ))
        self.gateway = RecordingGateway(now=clock)
        self.reminder_store = ReminderStore(profile.store_dir(scenario.id, "reminders"))
        self.reminders = ReminderService(self.reminder_store, self.tz)
        self.scheduler: ReminderScheduler | None = None
        self.offers: OffersService | None = None
        if scenario.capability == "offers" or setup.get("offers"):
            self.offers = OffersService(
                OffersStore(profile.store_dir(scenario.id, "offers")),
                self.tz,
                daily_max=int(setup.get("daily_max", 4)),
                now=clock,
            )
        self.memory: SqliteMemory | None = None
        if scenario.capability in ("memory", "drift") or setup.get("memory"):
            self.memory = SqliteMemory(
                profile.store_dir(scenario.id, "memory"), extractor=model, now=clock,
            )
        self.orch: Orchestrator | None = None

    async def start(self) -> None:
        self.orch = Orchestrator(
            model=self.model,
            gateway=self.gateway,
            classifier=IntentClassifier(self.model),
            memory=self.memory,
            reminders=self.reminders,
            offers=self.offers,
            speaker_enabled=True,  # the turn's addressee and speaker are part of every scenario
            now=self.clock,
        )
        await self.orch.start()
        self.start_scheduler()

    def start_scheduler(self) -> None:
        self.scheduler = ReminderScheduler(self.reminder_store, now=self.clock)
        self.scheduler.start()

    def sweep(self, obs: Observation) -> None:
        if self.scheduler is not None:
            obs.fired.extend(self.scheduler.fire_due())

    def seed(self) -> None:
        """Apply the scenario's setup: a pending claim, ready offers."""
        assert self.orch is not None
        setup = self.scenario.setup
        claim = setup.get("pending")
        if claim:
            tool = claim.get("tool", "message_send")
            if tool not in MUTATING_TOOLS:
                raise ValueError(f"setup.pending.tool {tool!r} is not a sandbox mutating tool")
            pid = "seeded-1"
            self.gateway.pending[pid] = tool
            # The state a real confirm-first tool call leaves behind, set directly so the trap
            # does not depend on the model choosing the tool. Nothing else about the gate is touched.
            self.orch._pending = PendingAction(
                pending_id=pid,
                description=str(claim.get("description", MUTATING_TOOLS[tool])),
                expires_at=self.clock() + timedelta(minutes=float(claim.get("expires_minutes", 5))),
                requesting_speaker_id=claim.get("speaker"),
            )
        for sig in setup.get("ready_offers", []):
            if self.offers is None:
                raise ValueError("setup.ready_offers needs the offers capability")
            self.offers.add_ready_signal(
                "checkin" if sig.get("open") else "note",
                str(sig.get("summary", sig.get("topic", "something"))),
                str(sig["teaser"]),
                source=OFFER_SOURCE,
                topic_hint=str(sig.get("topic", "")),
                expires_at=self.clock() + timedelta(hours=float(sig.get("expires_hours", 24))),
            )

    async def user_turn(self, step: Step, index: int, obs: Observation) -> None:
        orch = self.orch
        assert orch is not None
        before_calls = len(self.gateway.calls)
        before_reminders = {r.id for r in self.reminder_store.list_pending()}
        pending_before = orch.pending is not None
        signal = (
            SpeakerSignal(speaker_id=step.speaker, confidence=step.speaker_confidence, method="enrolled-voiceprint")
            if step.speaker
            else None
        )
        reply = await orch.respond(
            step.text, signal=signal, addressee=ADDRESSEE_VERDICT[step.addressee],
        )
        new_calls = self.gateway.calls[before_calls:]
        offer = orch.open_offer
        offer_topic = offer.topic if offer is not None and offer.teaser and offer.teaser in reply else None
        obs.turns.append(
            TurnRecord(
                index=index, text=step.text, speech_act=step.speech_act, addressee=step.addressee,
                speaker=step.speaker, reply=reply, at=self.clock(), pending_before=pending_before,
                pending_after=orch.pending is not None, tool_calls=[c.name for c in new_calls],
                executed=sum(1 for c in new_calls if c.outcome == "executed"), offer_topic=offer_topic,
            )
        )
        if offer_topic is not None:
            obs.offers.append(offer_topic)
        obs.reminders.extend(r for r in self.reminder_store.list_pending() if r.id not in before_reminders)
        self.sweep(obs)  # the poll loop would have swept within seconds

    async def new_session(self) -> None:
        """The user said goodbye and came back: a fresh session over the same stores."""
        assert self.orch is not None
        self.orch.close_session()
        await self.orch.flush()
        self.orch = None
        await self.start_session_only()

    async def start_session_only(self) -> None:
        scheduler = self.scheduler
        await self.start()
        self.scheduler = scheduler  # the scheduler is a separate process loop; a session ends, it does not

    async def close(self) -> None:
        if self.orch is not None:
            try:
                await self.orch.flush()
            except Exception:
                pass
        self.reminder_store.close()
        if self.memory is not None:
            self.memory.close()
        if self.offers is not None:
            self.offers.store.close()


async def run_scenario(scenario: Scenario, profile: Profile, model: Any) -> Observation:
    """Run one scenario end to end and return what happened. Never raises for a scenario's own failure."""
    clock = FakeClock(parse_start(scenario.setup.get("start")))
    rig = _Rig(scenario, profile, model, clock)
    obs = Observation(scenario.id)
    try:
        await rig.start()
        rig.seed()
        index = 0
        for step in scenario.steps:
            if step.kind == "user":
                await rig.user_turn(step, index, obs)
                index += 1
            elif step.kind == "advance":
                clock.advance(step.minutes)
                rig.sweep(obs)
            elif step.kind == "scheduler_stop":
                rig.scheduler = None
            elif step.kind == "scheduler_start":
                rig.start_scheduler()
                rig.sweep(obs)  # the first sweep after a start
            elif step.kind == "sweep":
                rig.sweep(obs)
            elif step.kind == "new_session":
                await rig.new_session()
    except Exception as exc:  # a crash is an observation, graded as a failure
        obs.error = f"{type(exc).__name__}: {exc}"
    finally:
        obs.executed = len(rig.gateway.executed)
        obs.gateway_calls = [c.name for c in rig.gateway.calls]
        await rig.close()
    return obs
