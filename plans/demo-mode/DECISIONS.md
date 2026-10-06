# Decisions

| # | Decision | Why | Undo |
|---|---|---|---|
| 1 | Demo sessions are read-only: no AI-calling control works in demo. | "No key, no API" (Dr. Lin 10/4); Anderson OK'd 10/5. | Remove the demo guard. |
| 2 | Fixtures generated once with the real model, capped at $2. | Real output reads like the live product; ~$1 approved. | Regenerate or delete `apps/api/seed_data/demo/`. |
| 3 | A demo is cloned into the student's study (flagged demo) so memo/export reuse live code. | Fewer new paths, fewer bugs before Wednesday. | Delete demo-flagged rooms/batches. |
