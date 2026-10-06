"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { TextInput } from "@/components/ui/form-controls";
import { GlassPanel } from "@/components/ui/glass-panel";
import { addSurveyQuestion, removeSurveyQuestion } from "@/lib/api";
import { useDemoMode } from "@/lib/demo-mode";
import { DEMO_ADDED_QUESTIONS_NOTE } from "@/lib/survey-demo-lock";
import {
  DEFAULT_LIKERT_ANCHORS,
  isStudentQuestion,
  toAddQuestionPayload,
  validateAddedQuestion,
  type AddedQuestionType,
} from "@/lib/survey-question-form";

type Question = { id: string; text: string; question_type: string };

const MAX_CHOICE_OPTIONS = 8;

export function AddQuestionCard({
  studyId,
  questions,
  onChanged,
}: {
  studyId: string;
  questions: Question[];
  onChanged: () => Promise<unknown> | void;
}) {
  const [demoOn] = useDemoMode();
  const [text, setText] = useState("");
  const [questionType, setQuestionType] = useState<AddedQuestionType>("likert");
  const [options, setOptions] = useState<string[]>([...DEFAULT_LIKERT_ANCHORS]);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const added = questions.filter((question) => isStudentQuestion(question.id));

  function switchType(next: AddedQuestionType) {
    setQuestionType(next);
    setOptions(next === "likert" ? [...DEFAULT_LIKERT_ANCHORS] : ["", ""]);
  }

  async function submit() {
    const draft = { text, questionType, options };
    const problem = validateAddedQuestion(draft);
    if (problem) {
      setMessage(problem);
      return;
    }
    setBusy(true);
    try {
      await addSurveyQuestion(studyId, toAddQuestionPayload(draft));
      setText("");
      switchType(questionType);
      setMessage("Added. Run live to get answers to it.");
      await onChanged();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not add the question.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    setBusy(true);
    try {
      await removeSurveyQuestion(studyId, id);
      setMessage(null);
      await onChanged();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not remove the question.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <GlassPanel className="p-5 sm:p-6">
      <div className="space-y-3 rounded-[1.55rem] border border-app-border p-5 [background:var(--theme-panel-gradient)]">
        <h3 className="text-lg font-semibold text-app-text">Add your own question</h3>
        <p className="text-sm leading-6 text-app-muted">
          Jev answers questions with listed options: a 1–5 scale or a single choice.
        </p>
        {demoOn ? <p className="text-sm leading-6 text-app-muted">{DEMO_ADDED_QUESTIONS_NOTE}</p> : null}
        <textarea
          aria-label="Question text"
          className="w-full rounded-2xl border px-4 py-3 text-sm text-app-text outline-none transition placeholder:text-app-muted/50 [background:var(--control-bg)] [border-color:var(--control-border)] focus:[border-color:var(--color-border-strong)] focus:[background:var(--control-bg-hover)] focus:[box-shadow:var(--focus-ring-shadow)]"
          rows={2}
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="Question text"
        />
        <div className="flex flex-wrap gap-2">
          <Button
            variant={questionType === "likert" ? "primary" : "secondary"}
            aria-pressed={questionType === "likert"}
            onClick={() => switchType("likert")}
          >
            1–5 scale
          </Button>
          <Button
            variant={questionType === "single_choice" ? "primary" : "secondary"}
            aria-pressed={questionType === "single_choice"}
            onClick={() => switchType("single_choice")}
          >
            Single choice
          </Button>
        </div>
        {questionType === "likert" ? (
          <p className="text-xs leading-5 text-app-muted">
            The five labels below describe 1 to 5. They start as interest wording; edit them so they fit your
            question.
          </p>
        ) : null}
        {options.map((option, index) => {
          const optionLabel = questionType === "likert" ? `Label for ${index + 1}` : `Option ${index + 1}`;
          return (
            <TextInput
              key={index}
              value={option}
              placeholder={optionLabel}
              ariaLabel={optionLabel}
              onChange={(value) => setOptions(options.map((current, i) => (i === index ? value : current)))}
            />
          );
        })}
        {questionType === "single_choice" && options.length < MAX_CHOICE_OPTIONS ? (
          <Button variant="secondary" onClick={() => setOptions([...options, ""])}>
            Add option
          </Button>
        ) : null}
        <div>
          <Button onClick={submit} disabled={busy}>
            Add question
          </Button>
        </div>
        {message ? (
          <p role="status" className="text-sm leading-6 text-app-text">
            {message}
          </p>
        ) : null}
        {added.length > 0 ? (
          <ul className="space-y-2 text-sm text-app-text">
            {added.map((question) => (
              <li key={question.id} className="flex items-center justify-between gap-3">
                <span>
                  {question.id}: {question.text}
                </span>
                <Button
                  variant="secondary"
                  aria-label={`Remove ${question.id}`}
                  onClick={() => remove(question.id)}
                  disabled={busy}
                >
                  Remove
                </Button>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </GlassPanel>
  );
}
