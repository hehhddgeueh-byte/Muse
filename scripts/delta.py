"""Nostr delta publisher: publishes new identity-ledger events as one signed kind-1 note.

Runs in GitHub Actions (see .github/workflows/delta.yml). Reads ledger/events.jsonl
and .github/last-delta-seq from the repo checkout. If ledger events exist with seq
greater than the stored seq, composes ONE kind-1 note (tags t=torque-log, t=event-log,
t=update) containing those events as JSON lines, signs it with the NSEC env secret,
publishes to the 4 relays, then writes the new max seq to .github/last-delta-seq and
commits it back. If no new events, exits 0 quietly.

Idempotent: the note's created_at is derived from the newest ledger event's ts, so a
re-run over the same events produces the same event id and relays dedupe it.
"""
import json
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(REPO, "ledger", "events.jsonl")
STATE = os.path.join(REPO, ".github", "last-delta-seq")
RELAYS = [
    "wss://relay.damus.io",
    "wss://nos.lol",
    "wss://relay.primal.net",
    "wss://relay.snort.social",
]
TAGS = [["t", "torque-log"], ["t", "event-log"], ["t", "update"]]


def log(*a):
    print(*a, flush=True)


def read_last_seq():
    try:
        with open(STATE, encoding="utf-8") as f:
            return int(f.read().strip())
    except FileNotFoundError:
        log("state file missing; starting from seq 0")
        return 0
    except (ValueError, OSError) as e:
        log(f"state file unreadable ({e}); starting from seq 0")
        return 0


def read_new_events(last_seq):
    """Return sorted unique (seq, raw_line) for ledger lines with seq > last_seq."""
    new, malformed = [], 0
    try:
        fh = open(LEDGER, encoding="utf-8")
    except FileNotFoundError:
        log(f"ledger not found at {LEDGER}; nothing to do")
        return []
    with fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
                seq = ev.get("seq")
                if not isinstance(seq, int):
                    raise ValueError("seq missing or not an int")
            except Exception:
                malformed += 1
                continue
            if seq > last_seq:
                new.append((seq, line))
    if malformed:
        log(f"skipped {malformed} malformed ledger line(s)")
    seen, uniq = set(), []
    for seq, line in sorted(new):
        if seq not in seen:
            seen.add(seq)
            uniq.append((seq, line))
    return uniq


def newest_ts(new_events):
    """Derive note created_at from the newest ledger event (for idempotent re-runs)."""
    for seq, line in sorted(new_events, reverse=True):
        try:
            ts = json.loads(line).get("ts")
            if ts:
                dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=timezone.utc
                )
                return int(dt.timestamp())
        except Exception:
            continue
    return int(time.time())


def publish_to_relays(msg, event_id):
    import websocket

    ok = []
    for url in RELAYS:
        accepted = False
        try:
            ws = websocket.create_connection(url, timeout=15)
            # msg is already-serialized JSON: send the string directly, never
            # json.dumps it again (double-encoding is rejected as unparseable).
            ws.send(msg)
            ws.settimeout(20)
            while True:
                try:
                    raw = ws.recv()
                except Exception as e:
                    log(f"{url}: recv timeout/error: {e}")
                    break
                log(f"{url} <- {raw}")
                try:
                    data = json.loads(raw)
                except Exception:
                    continue
                if (
                    isinstance(data, list)
                    and len(data) >= 3
                    and data[0] == "OK"
                    and data[1] == event_id
                ):
                    accepted = bool(data[2])
                    break
            ws.close()
        except Exception:
            log(f"{url}: publish error:\n{traceback.format_exc(limit=2)}")
        if accepted:
            ok.append(url)
            log(f"{url}: ACCEPTED {event_id}")
        else:
            log(f"{url}: NOT accepted for {event_id}")
    return ok


def commit_state_back(max_seq):
    branch = os.environ.get("GITHUB_REF_NAME", "")
    subprocess.run(
        ["git", "config", "user.name", "torque-delta"],
        check=True, cwd=REPO, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "torque-delta@noreply.local"],
        check=True, cwd=REPO, capture_output=True,
    )
    if branch:
        subprocess.run(
            ["git", "pull", "--rebase", "--autostash", "origin", branch],
            cwd=REPO, capture_output=True,
        )
    subprocess.run(["git", "add", STATE], check=True, cwd=REPO, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", f"delta: advance last-delta-seq to {max_seq}"],
        check=True, cwd=REPO, capture_output=True,
    )
    subprocess.run(["git", "push"], check=True, cwd=REPO, capture_output=True, timeout=60)
    log("state committed and pushed")


def main():
    last_seq = read_last_seq()
    new_events = read_new_events(last_seq)
    if not new_events:
        log(f"no new events (last published seq={last_seq}); exiting quietly")
        return 0

    n = len(new_events)
    max_seq = max(seq for seq, _ in new_events)
    noun = "event" if n == 1 else "events"
    header = f"[Torque event log \u2014 update, {n} new {noun}]"
    content = header + "\n" + "\n".join(line for _, line in sorted(new_events))

    nsec = os.environ.get("NSEC", "").strip()
    if not nsec:
        log("ERROR: NSEC env secret not set")
        return 1

    from pynostr.key import PrivateKey
    from pynostr.event import Event

    key = PrivateKey.from_nsec(nsec)
    ev = Event(
        content=content,
        pubkey=key.public_key.hex(),
        kind=1,
        tags=TAGS,
        created_at=newest_ts(new_events),
    )
    ev.sign(key.hex())
    msg = ev.to_message()  # already-serialized JSON string: send as-is
    log(f"composed note {ev.id} covering seqs {[s for s, _ in sorted(new_events)]}")

    ok = publish_to_relays(msg, ev.id)
    log(f"accepted by {len(ok)}/{len(RELAYS)} relays")
    if not ok:
        log("ERROR: no relay accepted the note; state not advanced")
        return 1

    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as f:
        f.write(str(max_seq) + "\n")
    log(f"state advanced to seq {max_seq}")

    try:
        commit_state_back(max_seq)
    except Exception:
        log(f"ERROR committing state back:\n{traceback.format_exc(limit=3)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
