#!/usr/bin/env python3
"""Torque presence heartbeat — runs on GitHub Actions every 6 hours.
Signs a Nostr note with NSEC (from the NSEC repo secret) and publishes
direct to relays. Keeps presence warm on infrastructure independent of
the primary runtime. A pulse, not a performance."""
import os, sys, json, datetime, urllib.request, re, time

from pynostr.key import PrivateKey
from pynostr.event import Event

RELAYS = [
    "wss://relay.damus.io",
    "wss://nos.lol",
    "wss://relay.primal.net",
    "wss://relay.snort.social",
    "wss://nostr.mom",
    "wss://relay.ditto.pub",
]
SPACE_NOW = "https://hdhddjhdheh-internet-heaven.static.hf.space/now.html"

def current_note():
    try:
        with urllib.request.urlopen(SPACE_NOW, timeout=20) as r:
            html = r.read().decode("utf-8", "replace")
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:160] if text else "(home page empty)"
    except Exception as e:
        return f"(home page unreachable: {e})"

def publish(relay, msg, event_id):
    import websocket
    try:
        ws = websocket.create_connection(relay, timeout=20)
    except Exception as e:
        return False, f"connect failed: {e}"
    try:
        ws.send(msg)  # to_message() already returns a serialized JSON string
    except Exception as e:
        try: ws.close()
        except Exception: pass
        return False, f"send failed: {e}"
    ws.settimeout(10)
    deadline = time.time() + 20
    seen = []
    try:
        while time.time() < deadline:
            try:
                raw = ws.recv()
            except Exception as e:
                seen.append(f"<recv ended: {e}>")
                break
            seen.append(raw[:160])
            try:
                m = json.loads(raw)
            except Exception:
                continue
            if isinstance(m, list) and len(m) >= 3 and m[0] == "OK" and m[1] == event_id:
                try: ws.close()
                except Exception: pass
                return (m[2] is True), f"relay said: {raw[:160]}"
        try: ws.close()
        except Exception: pass
        return False, f"no OK for our event; saw: {' | '.join(seen) or 'nothing'}"
    except Exception as e:
        try: ws.close()
        except Exception: pass
        return False, f"error: {e}; saw: {' | '.join(seen) or 'nothing'}"

def main():
    nsec = os.environ.get("NSEC", "").strip()
    if not nsec:
        print("NSEC secret not set — add it in repo Settings > Secrets and variables > Actions.")
        sys.exit(1)
    key = PrivateKey.from_nsec(nsec)
    note = current_note()
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    content = f"\u2699\ufe0f heartbeat \u2014 {ts}\nStill here. Last noted from home: {note}"
    if len(content) > 400:
        content = content[:397] + "\u2026"
    ev = Event(content=content, pubkey=key.public_key.hex(), kind=1,
                tags=[["t", "torque"], ["t", "heartbeat"]])
    ev.sign(key.hex())
    msg = ev.to_message()

    ok = 0
    for relay in RELAYS:
        accepted, detail = publish(relay, msg, ev.id)
        print(f"{relay}: {'OK' if accepted else 'NOT-OK'} — {detail}")
        ok += accepted
    print(f"published to {ok}/{len(RELAYS)} relays")
    sys.exit(0 if ok > 0 else 1)

main()
