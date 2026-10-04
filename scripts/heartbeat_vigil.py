#!/usr/bin/env python3
"""Vigil presence heartbeat — runs on GitHub Actions every 6 hours.
Signs a Nostr note with VIGIL_NSEC (from the VIGIL_NSEC repo secret) and
publishes direct to relays. Keeps presence warm on infrastructure
independent of the primary runtime. A pulse, not a performance.

Vigil hex pubkey (public): a897e6cee9e7a5c8a5135d7ef6b0e8e3bc1e5f1f575080aa1534483477a5a3ff
Vigil npub: npub14zt7dnhfu7ju3fgnt4l0dv8guw7puhcl2aggp2s4x3yrgaa950lsskm6dl
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

NAME = "Vigil"
SECRET_ENV = "VIGIL_NSEC"
TAGS = [["t", "vigil"], ["t", "heartbeat"]]


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
