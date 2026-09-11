# Brief — fold Dr. Lin's 2026-09-10 app feedback into the student interview section

Source: AYTM call 2026-09-10, Dr. Yufan Lin present. Full notes with timestamp anchors:
`~/ai-harness/vault/shared/meetings/2026-09-10-aytm-wang-lin-yaza-minh.md`

Lin owns the class that will test this app at the end of September. His feedback is about
**what a student experiences**, not about the research pipeline. Four things he asked for,
plus one Anderson agreed to on the call.

## What he asked for

1. **Theme extraction after an interview run** [36:35]–[37:30] — the direct pedagogical payload.
   His teaching flow: students hand-code (or ChatGPT-code) the transcripts themselves, then compare
   against what the app produced. Without this the interview section does not connect to his lesson.
   *This capability already exists* — `get_interview_insights()` in `apps/api/src/services/interview_service.py:366`
   extracts 3–6 themes with a representative quote and sentiment, cached per run. It only reads
   `_latest_interview_job`, i.e. the main gated workflow. The work is pointing it at the standalone
   interview section, not building theme extraction.

2. **Expensive models must take a deliberate extra step** [37:53]–[38:30]. Lin: *"not make the pricey
   feature that easy to just slide all the way down… they have a kind of box need to check, that's just
   one little step."* A checkbox, not a role system. The existing `allow_expensive_models` opt-in is the
   right mechanism; the slider must not be able to reach an expensive configuration without it.

3. **The full-batch run should not be a casual click** [37:53]. Anderson's own words on the call:
   a student sliding to 30 personas and picking expensive models is about a dollar. The student should
   see what a run will cost and confirm it before it starts.

4. **Break the page up** [29:20], [30:28]. Lin: students *"need more hand-holding… each step kind of is
   clear, they feel concrete, and not be too intimidated."* Anderson agreed on the call: *"this might seem
   like a lot to somebody that's literally just landing on it."* The `/interview` page currently shows
   personas, model pickers, batch dialer, cost estimate, comparison cards, follow-up chat, prompt inspector
   and pre-recorded interviews all at once.

5. **A back button** [35:30] — Anderson noted it missing while demoing.

## Explicitly NOT in scope

- **AI-to-AI and AI-to-human interviews, and multi-persona focus groups.** Anderson offered; Lin said
  finish what exists first — *"those are more optional, nice add-ons."* [42:04], [43:08]
- **The research pipeline** — re-drawing the 600 personas, the question-by-question distribution
  comparison, subset hypothesis testing, the hypothesis registry, headless experiment runs. That is
  Yaza and Minh's track, due Sept 17.
- **A teacher/student role system.** Lin asked for a checkbox, not permissions. Do not build roles.
- Anything in the main gated workflow, `prerecord_interviews.py`, the budget constants, or the cost
  report and its tests.

## Ordering

The `interview-batch-and-regenerate` build is in flight in the same worktree and is editing
`apps/web/src/app/interview/page.tsx`. This build starts only after that one merges.
