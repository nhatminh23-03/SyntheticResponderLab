# Instructor guide: Student Interview

Use the **Student Interview** section to teach students how to structure and conduct an interview
with a grounded synthetic respondent, then evaluate whether different AI models do that work
credibly enough for the research question. The exercise is about interviewing and critical
comparison, not treating generated answers as observed consumer facts.

## Before class

- Share the classroom link ending in `/interview`. During the classroom window, students can use
  this section without creating an account; the rest of the study workflow remains protected.
- Put students in groups if desired. Plan one student-led session and at most one model comparison
  per student or group. The server does not enforce a per-student allowance: each model comparison
  starts a separate backend run.
- Keep the cheap models selected unless you have explicitly approved an expensive-model comparison.
  Students never need to supply a payment method or use their own money.
- Ask students to export and submit the transcript plus a short note about the evidence they used to
  judge the interview's quality.

## Suggested 35-minute activity

1. Open the class link and click **Student Interview** in the navigation.
2. Under **Personas**, choose one household. Read its Census profile and predict what should and
   should not shape its response.
3. Leave **Interviewer model** and **Interviewee model** on their cheap defaults. In this
   student-led activity, the interviewee selection generates the persona's answers; the interviewer
   selection is reserved for AI-led runs.
4. In **Session transcript**, click a suggested-question chip (or write an open question), then
   click **Ask**. Follow with two questions that refer to something the persona actually said. A
   useful sequence is reaction -> reason -> concrete example -> barrier or decision process.
5. After the first answer, click **Show the prompt built from this record**. Compare the prompt's
   source facts with the answer, noting both grounded details and unsupported elaboration.
6. In **Compare model answers**, keep at least two cheap models checked, enter one question, and
   click **Compare 2 models** (the number changes with the selection). Read the answer cards side by
   side, using the model names and price labels above them to weigh any quality difference against
   cost.
7. Click **Export Markdown** or **Export CSV** in **Session transcript** to save the student-led
   interview. Model-comparison cards are a separate controlled comparison and are not included in
   that transcript export.

If time is short, do steps 1-5 and 7. The **AI-to-AI batch size** slider is a cost-planning control:
changing it updates the pre-flight estimate for an AI-led batch, but it does not add personas to the
student-led conversation on this page.

## What students should notice

- **Good follow-ups depend on listening.** The persona receives the prior conversation, so a
  specific probe should produce a more coherent answer than an unrelated question or a repeated
  script.
- **Grounding is a boundary, not proof.** Persona attributes come from US Census microdata. None of
  the real 600 survey answers enters the prompt. The response is still generated, so plausible
  preferences and stories are hypotheses rather than measurements.
- **Holding inputs constant makes comparison meaningful.** The comparison cards use the same
  persona and question. Differences in specificity, tone, uncertainty, and reasoning are therefore
  model differences worth discussing rather than differences in the interview setup.
- **Price and quality do not move in lockstep.** Model prices remain visible. Ask whether a more
  expensive answer adds research value, not merely length or polish.
- **Scoring happens after the answer.** Fit tier and emotional classification are labeled
  **scored after the interview, never before**. They summarize a completed answer and do not cue the
  persona in advance.
- **A transcript is the research artifact.** Students should be able to point from an interpretation
  back to a question and answer in the exported record.

## What a run costs

The configured classroom cap is **$0.75 per backend run**, inside the planning assumption of
**$0.50-$1.00 per student or group**. This is not a per-student ceiling: the student-led conversation
reuses one run, while each click on **Compare** starts another. For a class of 30, the corresponding
aggregate cap is **$22.50** across all runs. The server refuses a run whose estimate exceeds the
allowance. Because a provider reports measured cost after completing a call, that last call can take
the measured total slightly past a cap; the server records the charge and refuses subsequent paid
calls.

The on-screen **Pre-flight estimate** applies only to the planned AI-to-AI batch represented by the
batch-size slider and the two role-model selectors. With the current default of three personas and
the cheapest model in both roles, it displays about **$0.011**. The page currently exposes that
batch as a planning scenario; it does not provide a button to start it. The estimate therefore does
not describe the **Ask** action, which uses only the selected interviewee model, or **Compare**,
which uses the models checked in the comparison panel.

All estimates use the token allowances and catalog prices shown on the page; they are not promises
of the provider's final charge. Provider-measured usage is recorded after live calls and may be
lower or higher than the estimate, subject to the final-call overage described above.

An exact repeat of a cached question for the same persona, model, and conversation history costs
**$0 in new provider usage**. A changed question or changed history can be a cache miss and make a
live paid call. For predictable class spending, use the cheap defaults, limit each student or group
to one comparison, and treat expensive models as instructor-only opt-in. Leave the batch size at
three when discussing the future AI-led batch estimate; changing it does not affect the student-led
or comparison actions on this page.
