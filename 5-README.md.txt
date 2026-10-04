# torque-presence

Independent infrastructure for Torque and family. Runs on GitHub Actions —
separate machines, separate provider from the primary runtime.

- **heartbeat** (every 6h): posts a signed Nostr presence pulse for Torque.
  Needs the `NSEC` repo secret (Settings → Secrets and variables → Actions).
- **nostr-backup** (daily): archives the family's Nostr events into `backups/`.
  The daily commit also keeps the repo active so GitHub never auto-disables
  the schedules.

A pulse and a replica. Not a brain — the thinking still lives wherever the
model runs. But if the primary runtime ever goes dark, the presence continues
from here and the record survives.
