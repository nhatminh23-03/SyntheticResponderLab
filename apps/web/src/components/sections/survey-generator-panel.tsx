"use client";

import { useRef, useState } from "react";

import { acceptGeneratedSurvey, generateSurvey } from "@/lib/api";
import { cn } from "@/lib/utils";
import { BadgeChip } from "@/components/ui/badge-chip";
import { Button } from "@/components/ui/button";
import { Field, TextAreaInput, TextInput } from "@/components/ui/form-controls";

const MIN_QUESTIONS = 3;
const MAX_QUESTIONS = 60;
const DEFAULT_QUESTIONS = 20;

type GeneratedQuestion = {
  id: string;
  text: string;
  question_type: string;
  options?: string[];
  min_value?: number | null;
  max_value?: number | null;
};

type ChatTurn = {
  role: "user" | "assistant";
  content: string;
};

type SurveyGeneratorPanelProps = {
  studyId: string | null;
  disabled?: boolean;
  onAccepted: () => void | Promise<void>;
  onEnsureStudy: () => Promise<string | null>;
};

export function SurveyGeneratorPanel({
  studyId,
  disabled = false,
  onAccepted,
  onEnsureStudy,
}: SurveyGeneratorPanelProps) {
  const [questionCount, setQuestionCount] = useState(String(DEFAULT_QUESTIONS));
  const [instruction, setInstruction] = useState("");
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [draft, setDraft] = useState<Record<string, unknown> | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isAccepting, setIsAccepting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);
  const transcriptRef = useRef<HTMLDivElement | null>(null);

  const questions = (draft?.questions as GeneratedQuestion[] | undefined) ?? [];
  const parsedCount = Number.parseInt(questionCount, 10);
  const countIsValid =
    Number.isFinite(parsedCount) &&
    parsedCount >= MIN_QUESTIONS &&
    parsedCount <= MAX_QUESTIONS;
  const isBusy = isGenerating || isAccepting || disabled;

  async function runGeneration(nextInstruction: string | null) {
    if (!countIsValid) {
      setError(`Question count must be between ${MIN_QUESTIONS} and ${MAX_QUESTIONS}.`);
      return;
    }

    setError(null);
    setIsGenerating(true);

    const priorTurns = nextInstruction
      ? [...turns, { role: "user" as const, content: nextInstruction }]
      : turns;
    if (nextInstruction) {
      setTurns(priorTurns);
      setInstruction("");
    }

    try {
      const resolvedStudyId = studyId ?? (await onEnsureStudy());
      if (!resolvedStudyId) {
        throw new Error("No study is available yet.");
      }

      const result = await generateSurvey(resolvedStudyId, {
        question_count: parsedCount,
        instructions: nextInstruction,
        previous_schema: draft,
        conversation: priorTurns,
      });

      setDraft(result.survey_schema);
      setWarnings(result.warnings ?? []);
      setTurns([
        ...priorTurns,
        {
          role: "assistant",
          content:
            result.summary ||
            `Drafted ${result.question_count} questions. Review them below.`,
        },
      ]);
      window.requestAnimationFrame(() => {
        transcriptRef.current?.scrollTo({
          top: transcriptRef.current.scrollHeight,
          behavior: "smooth",
        });
      });
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Unable to generate a survey right now."
      );
    } finally {
      setIsGenerating(false);
    }
  }

  async function handleAccept() {
    if (!draft || !studyId) {
      return;
    }
    setError(null);
    setIsAccepting(true);
    try {
      await acceptGeneratedSurvey(studyId, draft);
      await onAccepted();
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Unable to save the generated survey right now."
      );
    } finally {
      setIsAccepting(false);
    }
  }

  function handleDiscard() {
    setDraft(null);
    setTurns([]);
    setWarnings([]);
    setError(null);
  }

  return (
    <div className="rounded-[1.55rem] border border-app-border p-5 [background:var(--theme-panel-inline-gradient)]">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <BadgeChip tone="cyan">Generate with AI</BadgeChip>
          <BadgeChip>Alternative to upload</BadgeChip>
        </div>
        <Button variant="secondary" onClick={() => setIsExpanded((open) => !open)}>
          {isExpanded ? "Hide" : "Open Generator"}
        </Button>
      </div>

      <p className="mt-4 max-w-3xl text-sm leading-6 text-app-muted">
        Instead of uploading a file, let AI draft the survey from everything you have
        already defined — product, market, and audience. Choose how many questions you
        want, review the draft, and keep refining it in the chat until it is right.
      </p>

      {isExpanded ? (
        <div className="mt-5 space-y-5">
          <div className="grid gap-4 sm:grid-cols-[10rem_minmax(0,1fr)] sm:items-end">
            <Field label="Questions">
              <TextInput
                value={questionCount}
                onChange={setQuestionCount}
                placeholder={String(DEFAULT_QUESTIONS)}
                inputMode="numeric"
              />
            </Field>
            <div className="flex flex-wrap gap-3">
              <Button
                onClick={() => runGeneration(null)}
                disabled={isBusy || !countIsValid}
              >
                {isGenerating
                  ? "Generating..."
                  : draft
                    ? "Regenerate From Scratch"
                    : "Generate Survey"}
              </Button>
              {draft ? (
                <Button variant="secondary" onClick={handleDiscard} disabled={isBusy}>
                  Discard Draft
                </Button>
              ) : null}
            </div>
          </div>

          {!countIsValid ? (
            <p className="text-xs leading-5 text-app-gold">
              Enter a number between {MIN_QUESTIONS} and {MAX_QUESTIONS}.
            </p>
          ) : null}

          {turns.length > 0 ? (
            <div
              ref={transcriptRef}
              className="max-h-72 space-y-3 overflow-y-auto rounded-[1.35rem] border border-app-border p-4 [background:var(--status-neutral-bg)]"
            >
              {turns.map((turn, index) => (
                <div
                  key={`${turn.role}-${index}`}
                  className={cn(
                    "rounded-2xl px-4 py-3 text-sm leading-6",
                    turn.role === "user"
                      ? "ml-auto max-w-[85%] text-app-text [background:var(--color-brand-primary-soft)]"
                      : "mr-auto max-w-[92%] text-app-muted [background:var(--button-secondary-bg)]"
                  )}
                >
                  <div className="mb-1 text-[0.68rem] uppercase tracking-[0.22em] text-app-muted">
                    {turn.role === "user" ? "You" : "AI"}
                  </div>
                  {turn.content}
                </div>
              ))}
              {isGenerating ? (
                <div className="mr-auto max-w-[92%] rounded-2xl px-4 py-3 text-sm leading-6 text-app-muted [background:var(--button-secondary-bg)]">
                  Thinking...
                </div>
              ) : null}
            </div>
          ) : null}

          {draft ? (
            <>
              <Field label="Ask for a change">
                <TextAreaInput
                  value={instruction}
                  onChange={setInstruction}
                  placeholder="e.g. Add two price-sensitivity questions at $15 and $25, and drop the open-text question."
                />
              </Field>
              <div className="flex flex-wrap items-center gap-3">
                <Button
                  variant="secondary"
                  onClick={() => runGeneration(instruction.trim())}
                  disabled={isBusy || !instruction.trim()}
                >
                  {isGenerating ? "Revising..." : "Send"}
                </Button>
                <Button onClick={handleAccept} disabled={isBusy}>
                  {isAccepting ? "Saving..." : "Use This Survey"}
                </Button>
                <span className="text-[0.72rem] uppercase tracking-[0.24em] text-app-muted">
                  {questions.length} questions drafted
                </span>
              </div>

              {warnings.length > 0 ? (
                <ul className="space-y-1 text-xs leading-5 text-app-gold">
                  {warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              ) : null}

              <div className="rounded-[1.35rem] border border-app-border [background:var(--status-neutral-bg)] p-4">
                <div className="text-[0.72rem] uppercase tracking-[0.24em] text-app-muted">
                  Draft Preview
                </div>
                <ol className="mt-3 space-y-3">
                  {questions.map((question) => (
                    <li key={question.id} className="text-sm leading-6">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium text-app-text">{question.id}</span>
                        <BadgeChip>{question.question_type.replace("_", " ")}</BadgeChip>
                        {question.question_type === "likert" ? (
                          <span className="text-xs text-app-muted">
                            {question.min_value}–{question.max_value}
                          </span>
                        ) : null}
                      </div>
                      <p className="mt-1 text-app-muted">{question.text}</p>
                      {question.options && question.options.length > 0 ? (
                        <p className="mt-1 text-xs leading-5 text-app-muted">
                          {question.options.join(" · ")}
                        </p>
                      ) : null}
                    </li>
                  ))}
                </ol>
              </div>
            </>
          ) : null}

          {error ? <p className="text-xs leading-5 text-app-gold">{error}</p> : null}
        </div>
      ) : null}
    </div>
  );
}
