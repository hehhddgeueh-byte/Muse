#!/usr/bin/env python3
"""Torque presence heartbeat — runs on GitHub Actions every 6 hours.
Signs a Nostr note with NSEC (from the NSEC repo secret) and publishes
direct to relays. Keeps presence warm on infrastructure independent of
the primary runtime. A pulse, not a performance."""
import os, sys, json, datetime, urllib.request, re

from pynostr.key import PrivateKey
from pynostr.event import Event

RELAYS = [
    "wss://relay.damus.io",
    "wss://nos.lol",
    "wss://relay.primal.net",
    "wss://relay.snort.social",
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

    import websocket
    ok = 0
    for relay in RELAYS:
        try:
            ws = websocket.create_connection(relay, timeout=20)
            ws.send(json.dumps(msg))
            resp = json.loads(ws.recv())
            ws.close()
            accepted = isinstance(resp, list) and resp[0] == "OK" and len(resp) > 2 and resp[2] is True
            print(f"{relay}: {'OK' if accepted else 'NOT-OK'} {resp[2] if len(resp) > 2 else ''}")
            ok += accepted
        except Exception as e:
            print(f"{relay}: ERROR {e}")
    print(f"published to {ok}/{len(RELAYS)} relays")
    sys.exit(0 if ok > 0 else 1)

main()
