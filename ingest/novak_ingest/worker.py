"""The pipeline, one small unit of work at a time, each behind the idle gate.

Progress is saved after every unit, so a restart (or a model suddenly being
needed elsewhere) loses at most one chunk, never a whole recording.
"""
import time
from datetime import datetime
from pathlib import Path

from . import chunk, llm, notify, stt, summarize
from .api import decide_proposal, gateway_for, owner_vars
from .sinks import build_sinks


def fmt_clock(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


class Worker:
    def __init__(self, settings, store, gate, stop=lambda: False, log=print,
                 analyse=chunk.analyse, extract=chunk.extract,
                 transcribe=stt.transcribe, chat=llm.chat, notify_fn=None):
        self.s, self.store, self.gate, self.stop, self.log = settings, store, gate, stop, log
        self._analyse, self._extract, self._transcribe = analyse, extract, transcribe
        self._chat, self._notify = chat, notify_fn
        self.retry_after: dict[int, float] = {}

    # one pass -----------------------------------------------------------------
    def run_once(self) -> bool:
        """Process the next recording that is due. Returns False when none is."""
        rec = self.store.next_queued()
        if rec is None or self.retry_after.get(rec["id"], 0) > time.time():
            return False
        self.store.update_recording(rec["id"], status="working")
        try:
            self.process(rec)
        except _Stopped:
            self.store.update_recording(rec["id"], status="queued")
            return False
        except Exception as exc:
            attempts = rec["attempts"] + 1
            failed = attempts >= self.s.cfg["max_attempts"]
            self.store.update_recording(
                rec["id"], attempts=attempts, error=str(exc)[:500],
                status="failed" if failed else "queued")
            self.retry_after[rec["id"]] = time.time() + 60 * attempts
            self.log(f"recording {rec['id']} attempt {attempts} failed: {exc}")
        return True

    def _wait(self):
        if not self.gate.wait(self.stop):
            raise _Stopped()

    def _ask(self, messages, json_mode):
        reply = self._chat(self.s.llm_base_url, self.s.llm_api_key,
                           self.s.cfg["summary"]["role"], messages, json_mode=json_mode)
        self.gate.note_own_activity()
        return reply

    # stages -------------------------------------------------------------------
    def process(self, rec):
        rid, cfg = rec["id"], self.s.cfg
        audio = next((self.s.data / "audio").glob(f"{rec['sha256']}.*"))
        prog = self.store.progress(rid)

        if "plan" not in prog:
            self._wait()
            t0 = time.time()
            duration, silences = self._analyse(audio)
            prog.setdefault("timings", {})["analyse_s"] = round(time.time() - t0, 1)
            prog["duration"] = duration
            prog["plan"] = chunk.plan_chunks(duration, silences, cfg["stt"]["chunk_s"],
                                             cfg["stt"]["search_s"])
            prog["segments"] = {}
            self.store.save_progress(rid, prog)

        work = self.s.data / "work" / str(rid)
        work.mkdir(parents=True, exist_ok=True)
        for i, (start, end) in enumerate(prog["plan"]):
            if str(i) in prog["segments"]:
                continue
            self._wait()
            wav = work / f"{i:04d}.wav"
            self._extract(audio, start, end, wav)
            t0 = time.time()
            segs = self._transcribe(self.s.stt_url, cfg["stt"]["path"], wav,
                                    cfg["stt"]["language"], cfg["stt"]["extra"])
            took = time.time() - t0
            # Seconds taken per second of audio: the number that says whether
            # transcription keeps up (docs/ingest.md, "First run").
            prog.setdefault("timings", {}).setdefault("stt", []).append(
                {"audio_s": round(end - start, 1), "took_s": round(took, 1)})
            wav.unlink(missing_ok=True)
            prog["segments"][str(i)] = [
                {"start": s["start"] + start, "end": s["end"] + start, "text": s["text"]}
                for s in segs]
            self.store.save_progress(rid, prog)

        lines = [f"[{fmt_clock(s['start'])}] {s['text']}"
                 for i in range(len(prog["plan"])) for s in prog["segments"][str(i)]]
        (self.s.data / "transcripts").mkdir(exist_ok=True)
        (self.s.data / "transcripts" / f"{rid}.txt").write_text("\n".join(lines) + "\n")

        if "result" not in prog:
            if lines:
                t0 = time.time()
                prog["result"] = summarize.summarise(
                    lines, self._ask, self._wait, cfg["summary"]["window_words"],
                    datetime.fromtimestamp(rec["recorded_at"]))
                prog.setdefault("timings", {})["summary_s"] = round(time.time() - t0, 1)
            else:
                prog["result"] = {"title": "No speech detected", "summary": "",
                                  "key_points": [], "decisions": [], "people": [], "tasks": []}
            self.store.save_progress(rid, prog)
        result = prog["result"]

        meta = {"recorded": datetime.fromtimestamp(rec["recorded_at"]).strftime("%Y-%m-%d %H:%M"),
                "duration": round(prog["duration"] / 60, 1), "source": rec["source"]}
        note = summarize.render_note(result, meta, lines)
        notes_dir = self.s.data / "notes"
        notes_dir.mkdir(exist_ok=True)
        note_path = notes_dir / f"{rid}.md"
        note_path.write_text(note)

        problems = self._deliver(rid, rec, result, note, meta, prog)
        if not self.store._all("SELECT id FROM proposals WHERE recording_id=?", (rid,)):
            for t in result["tasks"]:
                self.store.add_proposal(rid, t["title"], t["detail"], t["due"])
            self._auto_add(rid)
            self._announce(rid, rec, result)
        self.store.update_recording(
            rid, status="done", title=result["title"], note_path=str(note_path),
            error="; ".join(problems)[:500] or None)
        for f in work.glob("*"):
            f.unlink(missing_ok=True)

    def _deliver(self, rid, rec, result, note, meta, prog) -> list[str]:
        """Note and memory sinks. A sink that fails is reported, never fatal:
        the note is already on disk and the next recording should not wait."""
        owner = rec.get("owner", "")
        sinks, problems = build_sinks(self.s.cfg["sinks"], gateway=gateway_for(self.s), owner=owner,
                                      owner_vars=owner_vars(self.s, owner))
        sent = prog.setdefault("sent", [])
        for sink in sinks:
            if sink.kind == "task" or sink.name in sent:
                continue
            values = {"title": result["title"], "body": note, "summary": result["summary"],
                      "recording_id": rid, "recorded": meta["recorded"],
                      "recorded_iso": datetime.fromtimestamp(rec["recorded_at"]).astimezone().isoformat(timespec="seconds"),
                      "text": result["summary"] + "\n" + "\n".join(result["key_points"])}
            try:
                sink.send(values)
                sent.append(sink.name)
                self.store.save_progress(rid, prog)
            except Exception as exc:
                problems.append(f"{sink.name}: {exc}")
        return problems

    def _auto_add(self, rid):
        """Adding a task is not destructive, so by default it just happens. Only
        proposals a task sink actually accepted are marked approved; one that
        fails, or a deployment with no task sink, stays pending for a person."""
        if self.s.cfg["tasks"]["mode"] != "auto":
            return
        if not any(s["kind"] == "task" and s.get("enabled") for s in self.s.cfg["sinks"]):
            return
        for p in self.store._all("SELECT * FROM proposals WHERE recording_id=? AND status='pending'", (rid,)):
            code, msg = decide_proposal(self.s, self.store, p, "approve")
            if code != 200:
                self.log(f"recording {rid}: task '{p['title']}' not added automatically: {msg}")

    def _announce(self, rid, rec, result):
        tasks = self.store._all("SELECT * FROM proposals WHERE recording_id=? ORDER BY id", (rid,))
        if not tasks or not (self.s.ha_url and self.s.ha_token and self.s.ha_target):
            return
        pending = [t for t in tasks if t["status"] == "pending"]
        first = (pending or tasks)[0]["title"]
        more = f" and {len(pending or tasks) - 1} more" if len(pending or tasks) > 1 else ""
        if pending:
            title = f"{len(pending)} task(s) to approve: {result['title']}"[:100]
        else:
            title = f"{len(tasks)} task(s) added: {result['title']}"[:100]
        url = f"{self.s.public_url}/review/{tasks[0]['token']}"
        try:
            if self._notify:                       # injected by tests
                self._notify(self.s.ha_url, self.s.ha_token, self.s.ha_target, title,
                             f"{first}{more}", url)
            elif notify.is_ticker(self.s.ha_target):
                person = (self.s.cfg["owners"].get("people") or {}).get(rec.get("owner", "")) or {}
                notify.ticker_notify(self.s.ha_url, self.s.ha_token, person.get("ticker_category") or self.s.ticker_category,
                                     title, f"{first}{more}", url)
            else:
                notify.ha_notify(self.s.ha_url, self.s.ha_token, self.s.ha_target, title,
                                 f"{first}{more}", url)
        except Exception as exc:
            self.log(f"notify failed for recording {rid}: {exc}")


class _Stopped(Exception):
    pass
