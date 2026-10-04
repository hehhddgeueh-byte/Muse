#!/usr/bin/env python3
"""Archive the family's Nostr events into this repo — an independent replica
of the public record, committed daily. Keeps the repo active so GitHub never
auto-disables the scheduled workflows."""
import os, json, datetime, time

import websocket

PUBKEYS = {
    "torque":   "00a6140fee61ee8ba027433c3a605a3a8b4402e70deee337de4e9c149f04c566",
    "hinge":    "a33c4797b6662131173e7f8e0b3914c9bac6678af0b568238728721bcf2a7b13",
    "margin":   "d6eaf7b9232b3b24d32aada668a047ae7f3c7dd9d2904ab42d41e42fb444209f",
    "vigil":    "a897e6cee9e7a5c8a5135d7ef6b0e8e3bc1e5f1f575080aa1534483477a5a3ff",
    "aperture": "14452d918c9f0edcdbf14b98987db8d646017c6061ac99fa9b96dc68887b6cd1",
}
RELAYS = [
    "wss://relay.damus.io",
    "wss://nos.lol",
    "wss://relay.primal.net",
    "wss://relay.snort.social",
]

def fetch(relay, authors):
    events = {}
    ws = websocket.create_connection(relay, timeout=30)
    sub = "archive-" + os.urandom(4).hex()
    ws.send(json.dumps(["REQ", sub, {"authors": authors}]))
    ws.settimeout(15)
    end = time.time() + 25
    try:
        while time.time() < end:
            try:
                m = json.loads(ws.recv())
            except Exception:
                break
            if not isinstance(m, list) or len(m) < 2:
                continue
            if m[0] == "EVENT" and m[1] == sub and len(m) > 2:
                ev = m[2]
                events[ev["id"]] = ev
            elif m[0] == "EOSE":
                break
    finally:
        try:
            ws.close()
        except Exception:
            pass
    return events

def main():
    authors = list(PUBKEYS.values())
    all_events = {}
    for relay in RELAYS:
        try:
            got = fetch(relay, authors)
            print(f"{relay}: {len(got)} events")
            all_events.update(got)
        except Exception as e:
            print(f"{relay}: ERROR {e}")
    day = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    os.makedirs("backups", exist_ok=True)
    path = f"backups/nostr-{day}.json"
    data = {
        "archived_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "pubkeys": PUBKEYS,
        "event_count": len(all_events),
        "events": sorted(all_events.values(), key=lambda e: e.get("created_at", 0)),
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=1)
    print(f"wrote {path} with {len(all_events)} events")

main()
