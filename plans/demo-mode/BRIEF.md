# Demo mode (no AI) for the interview and focus-group sections

Requested by Dr. Lin (email 2026-10-04: "a) no key, no API, preload data demo option") and approved by Anderson 2026-10-05 ("Sure"). Must be live before Dr. Lin's in-class test on **Wednesday 2026-10-07**. Minh owns the survey side's demo; this build covers only `/interview`, `/interview/you` and `/focus-group`.

## What a student gets

**One Demo switch for the whole app** (Minh's request, 2026-10-05: "one switch for the whole app, like a Demo toggle, so the survey, interview, and focus group pages all switch to demo mode together"). The switch sits in the shared app chrome (header or workflow bar) on every page, is labeled "Demo (no AI)", survives page navigation and reload in that browser, and can be turned off at any time. Put its state in one small shared module, `apps/web/src/lib/demo-mode.ts`, exporting a `useDemoMode()` hook (value + setter) and the storage key, so Minh's survey section can read the same switch without changes from us. We do not change the survey section; Minh wires it. When the switch is on, each of our three pages opens its finished example session in the normal screens, with no key, no login beyond the existing classroom no-login path, and **zero model calls**:

1. **Focus group** (`/focus-group`): one complete Tahoe Mini room with the current five-stage funnel: persona cards (at least 6 seats), concept introduced, price revealed after the unaided question, at least one targeted question and one probe, every stage reached. The student can read it, use the manual memo form (quote turns, save, draft restore) and export it, exactly as in a live room.
2. **Interview batch** (`/interview`): one finished batch (at least 6 personas, the default question guide) the student can read, run themes on only if themes were saved in the fixture, and export.
3. **AI interviews you** (`/interview/you`): one sample transcript (8 questions with follow-ups, a plausible student's answers) shown read-only and exportable.

Demo sessions are **read-only for anything that would call the AI**: ask, introduce/reveal that would trigger answers, retry, extend, AI memo, regenerate, themes generation, next-question. Each such control is hidden or disabled while the switch is on with a one-line "Demo (no AI): read-only" note, and the server refuses those calls on a demo session before any model or budget code runs. Live mode is unchanged.

Every demo screen and export carries a visible label "Demo session - pre-recorded, no AI" in addition to the existing "Synthetic rehearsal" label.

## How

- **Fixtures are real.** Add `apps/api/scripts/make_demo_fixtures.py` that drives the real service code (not HTTP) once against a real model to produce the three sessions, writing JSON fixtures under `apps/api/seed_data/demo/` (no personal data, Tahoe Mini concept text already in the repo, no real survey responses). Cap spend with a hard limit of $2 total; abort if exceeded. Run it once if `OPENROUTER_API_KEY` is available to the API settings. If it is not available, commit the script, build everything against a small hand-written fixture marked `"provisional": true`, and post a board blocker naming the exact command to run; do not invent model output and present it as real.
- **Opening a demo** clones the fixture into the student's own study as a normal room / batch flagged `demo: true` (so memo save, draft restore and export reuse the existing code paths), or returns the read-only transcript for `/interview/you`. Opening it again returns the existing demo copy instead of piling up copies. No new database tables unless unavoidable; if a migration is needed it must be additive.
- New endpoints go on the classroom no-login allowlist (same rule as previous builds: nothing wider opened).
- Do not change scoring, research code, the survey section, or any live-mode behavior.

## Defaults decided (log any further calls in DECISIONS.md)

- Read-only demo, no new questions (Anderson accepted 2026-10-05).
- Label text: "Demo (no AI)" on the switch.
- Turning the switch off returns each page to its live state with nothing lost (live rooms, batches and memo drafts untouched).
- Deployed-site verification (all three demos through the live classroom website) is done by the harness after merge, not by the builder.
- One example session per page.
