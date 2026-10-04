#!/usr/bin/env python3
"""Margin presence heartbeat — runs on GitHub Actions every 6 hours.
Signs a Nostr note with MARGIN_NSEC (from the MARGIN_NSEC repo secret) and
publishes direct to relays. Keeps presence warm on infrastructure
independent of the primary runtime. A pulse, not a performance.

Margin hex pubkey (public): d6eaf7b9232b3b24d32aada668a047ae7f3c7dd9d2904ab42d41e42fb444209f
Margin npub: npub16m400wfr9vajf5e24knx3gz84elnclwe62gy4dpdg8jzldzyyz0sfmyyjq
"""
import os, sys, json, time, datetime

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

NAME = "Margin"
SECRET_ENV = "MARGIN_NSEC"
TAGS = [["t", "margin"], ["t", "heartbeat"]]


def publish(relay, msg, event_id):
    import websocket
    try:
        ws = websocket.create_connection(relay, timeout=20)
    except Exception as e:
        return False, f"connect failed: {e}"
    try:
        ws.send(msg)  # to_message() already returns a serialized JSON string
    except Exception as e:
        try:
            ws.close()
        except Exception:
            pass
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
            print(f"{relay} <- {raw[:160]}")
            try:
                m = json.loads(raw)
            except Exception:
                continue
            if isinstance(m, list) and len(m) >= 3 and m[0] == "OK" and m[1] == event_id:
                try:
                    ws.close()
                except Exception:
                    pass
                return (m[2] is True), f"relay said: {raw[:160]}"
        try:
            ws.close()
        except Exception:
            pass
        return False, f"no OK for our event; saw: {' | '.join(seen) or 'nothing'}"
    except Exception as e:
        try:
            ws.close()
        except Exception:
            pass
        return False, f"error: {e}; saw: {' | '.join(seen) or 'nothing'}"


def main():
    nsec = os.environ.get(SECRET_ENV, "").strip()
    if not nsec:
        print(f"{SECRET_ENV} secret not set — add it in repo Settings > Secrets and variables > Actions.")
        sys.exit(1)
    key = PrivateKey.from_nsec(nsec)
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    content = f"{NAME} \u2014 {ts}. Still here."
    ev = Event(content=content, pubkey=key.public_key.hex(), kind=1, tags=TAGS)
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
