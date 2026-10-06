"use client";

import { DemoScreens, DemoNotice, useDemoActivity } from "@/components/demo/demo-mode";
import { isDemoMode } from "@/lib/demo-mode";

import { useEffect, useRef, useState } from "react";

import { interviewOperation } from "@/lib/standalone-interview";
import { Button } from "@/components/ui/button";
import { GlassPanel } from "@/components/ui/glass-panel";
import {
  canSendAnswer,
  describeFailure,
  humanInterviewExport,
  isUnfinished,
  NEW_HUMAN_INTERVIEW,
  nextHumanQuestion,
  withQuestion,
  type HumanInterview,
  type HumanMessage,
} from "@/lib/human-interview";
import { WorkflowNav } from "@/components/ui/workflow-nav";
import { StudyProvider, useStudy } from "@/providers/study-provider";
import { ThemeProvider } from "@/providers/theme-provider";

export default function AiInterviewsYouPage() {
  return (
    <ThemeProvider>
      <StudyProvider>
        <WorkflowNav />
        <DemoScreens>{demo => <AiInterviewsYouContent demoPlayback={demo} />}</DemoScreens>
      </StudyProvider>
    </ThemeProvider>
  );
}

function AiInterviewsYouContent({ demoPlayback = false }: { demoPlayback?: boolean } = {}) {
  const [demoRetry, setDemoRetry] = useState(0);
  const { studyId, studyBootstrapError } = useStudy();
  useEffect(() => {
    if (!demoPlayback || !studyId) return;
    let active = true;
    setError("");
    interviewOperation<{ interview: HumanInterview }>(studyId, "demo/you", {})
      .then(result => {
        if (!active) return;
        setInterview(result.interview);
      })
      .catch((failure: Error) => { if (active) setError(failure.message); });
    return () => { active = false; };
  }, [studyId, demoPlayback, demoRetry]);

  const [interview, setInterview] = useState<HumanInterview>(NEW_HUMAN_INTERVIEW);
  const [answer, setAnswer] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  useDemoActivity(pending, demoPlayback);
  const readOnly = demoPlayback || !!interview.demo;
  const transcriptEnd = useRef<HTMLDivElement | null>(null);
  const started = interview.messages.length > 0 || interview.ended;
  const unfinished = isUnfinished(interview);

  useEffect(() => { transcriptEnd.current?.scrollIntoView({ block: "nearest" }); }, [interview.messages.length]);

  // Answers are never stored, so a refresh or a closed tab loses the interview. Say so first.
  useEffect(() => {
    if (!unfinished) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [unfinished]);

  async function request(answered: HumanMessage[], sentAnswer: string) {
    if (!studyId || readOnly || isDemoMode()) return;
    setPending(true);
    setError("");
    try {
      const reply = await nextHumanQuestion(studyId, interview.sessionId, answered);
      setInterview((current) => withQuestion(current, answered, reply));
      // Only clear the box if it still holds what was sent.
      setAnswer((current) => (current === sentAnswer ? "" : current));
    } catch (failure) {
      const { message, ends } = describeFailure(failure);
      setError(message);
      if (ends) setInterview((current) => ({ ...current, ended: true }));
    } finally {
      setPending(false);
    }
  }

  function send() {
    if (!canSendAnswer(interview, answer, pending)) return;
    void request([...interview.messages, { role: "assistant", content: answer.trim() }], answer);
  }

  function download(format: "csv" | "md") {
    const exported = humanInterviewExport(interview, format);
    const url = URL.createObjectURL(exported.blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = exported.filename;
    link.click();
    URL.revokeObjectURL(url);
  }

  const answeredCount = interview.messages.filter((message) => message.role === "assistant").length;

  return (
    <main className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-6 py-12">
      {readOnly ? <DemoNotice provisional={interview.provisional} /> : null}
      {demoPlayback && interview.messages.length === 0 && !error ? <p role="status">Loading demo…</p> : null}
      {demoPlayback && error ? <Button onClick={() => setDemoRetry(n => n + 1)}>Retry demo load</Button> : null}

      <header className="flex flex-col gap-2">
        <a href="/interview" className="text-sm text-app-muted hover:text-app-text">&larr; Back to interviews</a>
        <h1 className="text-3xl font-semibold">AI interviews you</h1>
        <p className="text-sm text-app-muted">
          The roles flip: the AI moderator interviews you, with the same discussion guide it uses on
          the personas. Answer in your own words; it follows up on what you say. It stops after{" "}
          {interview.turnLimit} questions, or when you click End.
        </p>
        <p className="text-xs text-app-muted">
          Your answers go only to the interviewer model, to write its next question. They are not
          saved anywhere, so export the transcript before you leave this page.
        </p>
      </header>

      {studyBootstrapError ? <p role="alert">{studyBootstrapError}</p> : null}
      {error ? <p role="alert" className="rounded-xl border border-app-border p-4 text-sm">{error}</p> : null}

      {!started ? (
        <div>
          <Button disabled={readOnly || !studyId || pending} onClick={() => void request([], "")}>
            {pending ? "Starting…" : "Start the interview"}
          </Button>
        </div>
      ) : (
        <GlassPanel className="flex flex-col gap-4 p-5" aria-label="Interview transcript">
          <p className="text-xs text-app-muted">
            {interview.ended ? "Interview ended" : `Question ${answeredCount + 1} of ${interview.turnLimit}`}
            {" · "}Measured cost: ${Number(interview.costUsd).toFixed(4)}
          </p>
          <ol className="flex flex-col gap-3">
            {interview.messages.map((message, index) => (
              <li key={index} className={message.role === "user" ? "" : "ml-8 rounded-xl border border-app-border p-3"}>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-app-muted">
                  {message.role === "user" ? "AI interviewer" : "You"}
                </p>
                <p className="whitespace-pre-wrap text-sm">{message.content}</p>
              </li>
            ))}
          </ol>
          <div ref={transcriptEnd} />

          {!interview.ended ? (
            <form className="flex flex-col gap-3" onSubmit={(event) => { event.preventDefault(); send(); }}>
              <label className="text-sm font-semibold" htmlFor="human-answer">Your answer</label>
              <textarea
                id="human-answer"
                value={answer}
                onChange={(event) => setAnswer(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); send(); }
                }}
                maxLength={4000}
                rows={4}
                className="rounded-xl border border-app-border bg-transparent px-4 py-3 text-sm text-app-text outline-none focus:border-app-borderStrong"
              />
              <div className="flex gap-3">
                <Button type="submit" disabled={!canSendAnswer(interview, answer, pending)}>
                  {pending ? "Waiting for the interviewer…" : "Send answer"}
                </Button>
                <Button type="button" variant="secondary" onClick={() => setInterview((current) => ({ ...current, ended: true }))}>
                  End interview
                </Button>
              </div>
            </form>
          ) : (
            <div className="flex flex-wrap gap-3">
              <Button onClick={() => download("md")}>Export Markdown</Button>
              <Button variant="secondary" onClick={() => download("csv")}>Export CSV</Button>
              <Button
                variant="secondary"
                disabled={readOnly || pending}
                onClick={() => {
                  if (window.confirm("Start over? This transcript is not saved anywhere unless you exported it.")) {
                    setInterview(NEW_HUMAN_INTERVIEW);
                    setAnswer("");
                    setError("");
                  }
                }}
              >
                Start over
              </Button>
            </div>
          )}
        </GlassPanel>
      )}
    </main>
  );
}
