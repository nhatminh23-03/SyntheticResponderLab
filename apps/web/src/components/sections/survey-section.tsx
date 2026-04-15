"use client";

import {
  DragEvent,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

import {
  loadNeoSurveyPreset,
  SurveyQuestionPayload,
  SurveySchemaPayload,
  uploadSurvey,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { useStudy } from "@/providers/study-provider";
import { BadgeChip } from "@/components/ui/badge-chip";
import { Button } from "@/components/ui/button";
import { GlassPanel } from "@/components/ui/glass-panel";
import { RevealOnScroll } from "@/components/ui/reveal-on-scroll";
import { SectionHeader } from "@/components/ui/section-header";
import { SectionWrapper } from "@/components/ui/section-wrapper";

type UploadPhase =
  | "idle"
  | "selected"
  | "uploading"
  | "success"
  | "warning"
  | "error";

type SurveyStatusState = {
  tone: "neutral" | "success" | "warning" | "error";
  message: string;
};

type SurveySavedState = {
  status: string;
  source_filename?: string | null;
  source_format?: string | null;
  question_count?: number | null;
  parse_warnings: string[];
  schema?: SurveySchemaPayload | null;
  saved_at?: string | null;
  updated_at?: string | null;
};

const ACCEPTED_SURVEY_EXTENSIONS = [".md", ".docx", ".pdf"];
const INITIAL_PREVIEW_COUNT = 4;

export function SurveySection() {
  const {
    studyId,
    study,
    createOrLoadStudy,
    isCreatingStudy,
    isHydratingStudy,
    refreshStudy,
  } = useStudy();
  const [studyMode, setStudyMode] = useState<string | null>(null);
  const [savedSurvey, setSavedSurvey] = useState<SurveySavedState | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragActive, setIsDragActive] = useState(false);
  const [uploadPhase, setUploadPhase] = useState<UploadPhase>("idle");
  const [status, setStatus] = useState<SurveyStatusState>({
    tone: "neutral",
    message: "Choose a survey instrument, then upload it to validate the schema the simulation will use.",
  });
  const [isUploading, setIsUploading] = useState(false);
  const [isLoadingNeoPreset, setIsLoadingNeoPreset] = useState(false);
  const [isParserReviewOpen, setIsParserReviewOpen] = useState(false);
  const [previewMode, setPreviewMode] = useState<"form" | "table">("form");
  const [showAllQuestions, setShowAllQuestions] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function hydrateSurvey() {
      if (!studyId || !study) {
        if (!cancelled) {
          setStudyMode(null);
          setSavedSurvey(null);
          setStatus({
            tone: "neutral",
            message:
              "Choose a survey instrument, then upload it to validate the schema the simulation will use.",
          });
        }
        return;
      }

      const survey = study.survey;

      if (!cancelled) {
        setStudyMode(study.study_mode.value ?? null);
        setSavedSurvey(
          survey?.status === "saved"
            ? {
                status: survey.status,
                source_filename: survey.source_filename ?? null,
                source_format: survey.source_format ?? null,
                question_count: survey.question_count ?? null,
                parse_warnings: survey.parse_warnings ?? [],
                schema: survey.schema ?? null,
                saved_at: survey.saved_at ?? null,
                updated_at: survey.updated_at ?? null,
              }
            : null
        );
        setStatus({
          tone:
            survey?.status === "saved"
              ? classifyWarningTone(survey.parse_warnings ?? [])
              : "neutral",
          message:
            survey?.status === "saved"
              ? buildSavedSurveyMessage(survey.parse_warnings ?? [])
              : study.study_mode.value === "neo_smart"
                ? "Neo Smart mode is active. Load the bundled Tahoe Mini survey or upload a different instrument."
                : "No survey is saved yet. Upload the exact instrument you want synthetic respondents to answer.",
        });
      }
    }

    void hydrateSurvey();

    return () => {
      cancelled = true;
    };
  }, [studyId, study?.survey?.updated_at, study?.survey?.status, study?.study_mode?.value]);

  const surveySchema = savedSurvey?.schema ?? null;
  const surveyQuestions = surveySchema?.questions ?? [];
  const previewQuestions = showAllQuestions
    ? surveyQuestions
    : surveyQuestions.slice(0, INITIAL_PREVIEW_COUNT);
  const warningTone = classifyWarningTone(savedSurvey?.parse_warnings ?? []);

  function handleBrowseClick() {
    fileInputRef.current?.click();
  }

  function handleFileSelection(file: File | null) {
    if (!file) {
      return;
    }

    const extension = `.${file.name.split(".").pop()?.toLowerCase() ?? ""}`;
    if (!ACCEPTED_SURVEY_EXTENSIONS.includes(extension)) {
      setSelectedFile(null);
      setUploadPhase("error");
      setStatus({
        tone: "error",
        message: "Unsupported survey file type. Upload Markdown (.md), DOCX (.docx), or PDF (.pdf).",
      });
      return;
    }

    setSelectedFile(file);
    setUploadPhase("selected");
    setStatus({
      tone: "neutral",
      message:
        "File selected locally. Upload it when you are ready to validate and save the normalized survey schema.",
    });
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setIsDragActive(false);
    handleFileSelection(event.dataTransfer.files?.[0] ?? null);
  }

  async function handleUploadSurvey() {
    if (!selectedFile) {
      setStatus({
        tone: "warning",
        message: "Select a survey file first.",
      });
      return;
    }

    setIsUploading(true);
    setUploadPhase("uploading");
    setStatus({
      tone: "neutral",
      message: "Uploading and validating the survey instrument...",
    });

    try {
      const resolvedStudyId = (await createOrLoadStudy()) ?? studyId;

      if (!resolvedStudyId) {
        throw new Error("No study is available yet.");
      }

      const result = await uploadSurvey(resolvedStudyId, selectedFile);
      await refreshStudy(resolvedStudyId);
      const warnings = result.survey?.parse_warnings ?? [];

      setSavedSurvey(
        result.survey
          ? {
              status: result.survey.status ?? "saved",
              source_filename: result.survey.source_filename ?? selectedFile.name,
              source_format: result.survey.source_format ?? null,
              question_count: result.survey.question_count ?? null,
              parse_warnings: warnings,
              schema: result.survey.schema ?? null,
              saved_at: result.survey.saved_at ?? null,
              updated_at: result.survey.updated_at ?? null,
            }
          : null
      );
      setUploadPhase(warnings.length > 0 ? "warning" : "success");
      setStatus({
        tone: classifyWarningTone(warnings),
        message: buildSavedSurveyMessage(warnings),
      });
      setSelectedFile(null);
      setShowAllQuestions(false);
    } catch (error) {
      setUploadPhase("error");
      setStatus({
        tone: "error",
        message:
          error instanceof Error
            ? error.message
            : "Unable to upload and parse the survey right now.",
      });
    } finally {
      setIsUploading(false);
    }
  }

  function handleClearSurvey() {
    setSelectedFile(null);
    setUploadPhase("idle");
    setStatus({
      tone: "warning",
      message:
        "The backend does not expose a clear-survey endpoint yet. Local file selection was cleared, but any saved survey remains in backend study state.",
    });
  }

  async function handleLoadNeoPreset() {
    setIsLoadingNeoPreset(true);
    setStatus({
      tone: "neutral",
      message: "Loading the bundled Neo survey preset from the backend...",
    });

    try {
      const resolvedStudyId = (await createOrLoadStudy()) ?? studyId;

      if (!resolvedStudyId) {
        throw new Error("No study is available yet.");
      }

      const result = await loadNeoSurveyPreset(resolvedStudyId);
      await refreshStudy(resolvedStudyId);
      const warnings = result.survey?.parse_warnings ?? [];

      setSavedSurvey(
        result.survey
          ? {
              status: result.survey.status ?? "saved",
              source_filename: result.survey.source_filename ?? "Neo Smart Living — Survey_HighPriority.md",
              source_format: result.survey.source_format ?? null,
              question_count: result.survey.question_count ?? null,
              parse_warnings: warnings,
              schema: result.survey.schema ?? null,
              saved_at: result.survey.saved_at ?? null,
              updated_at: result.survey.updated_at ?? null,
            }
          : null
      );
      setUploadPhase(warnings.length > 0 ? "warning" : "success");
      setStatus({
        tone: classifyWarningTone(warnings),
        message:
          warnings.length > 0
            ? "Neo survey preset loaded with parser notes. Review the normalized schema below."
            : "Neo survey preset loaded and saved successfully.",
      });
      setSelectedFile(null);
      setShowAllQuestions(false);
    } catch (error) {
      setUploadPhase("error");
      setStatus({
        tone: "error",
        message:
          error instanceof Error
            ? error.message
            : "Unable to load the Neo survey preset right now.",
      });
    } finally {
      setIsLoadingNeoPreset(false);
    }
  }

  return (
    <SectionWrapper id="survey" scrollable contentClassName="relative scrollbar-hidden pr-0">
      <div className="space-y-8">
        <RevealOnScroll>
          <SectionHeader
            index={5}
            eyebrow="Survey Upload"
            title="Validate the exact survey instrument the system will use downstream."
            description="Upload the source survey, let the parser translate it into the normalized internal schema, and review what the simulation will actually ask synthetic respondents."
          />
        </RevealOnScroll>

        <RevealOnScroll delay={0.04}>
          <GlassPanel className="p-5 sm:p-6">
            <div className="rounded-[1.55rem] border border-white/5 bg-[linear-gradient(180deg,rgba(12,18,22,0.84),rgba(12,18,22,0.6))] p-5">
              <div className="flex flex-wrap items-center gap-3">
                <BadgeChip tone="cyan">Supported Formats</BadgeChip>
                <BadgeChip>.md</BadgeChip>
                <BadgeChip>.docx</BadgeChip>
                <BadgeChip>.pdf</BadgeChip>
              </div>

              <div className="mt-5 flex flex-wrap gap-3">
                <Button variant="secondary" onClick={handleClearSurvey}>
                  Clear Saved Survey
                </Button>
                {studyMode === "neo_smart" ? (
                  <Button
                    variant="secondary"
                    onClick={handleLoadNeoPreset}
                    disabled={isLoadingNeoPreset || isUploading || isCreatingStudy || isHydratingStudy}
                  >
                    {isLoadingNeoPreset
                      ? "Loading Neo Survey Preset..."
                      : savedSurvey
                        ? "Reset to Neo Survey Preset"
                        : "Load Neo Survey Preset"}
                  </Button>
                ) : null}
              </div>

              <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-white/6 pt-6">
                <div>
                  <div className="text-[0.72rem] uppercase tracking-[0.24em] text-app-muted">
                    Upload &amp; Validate
                  </div>
                  <p className="mt-2 max-w-2xl text-sm leading-6 text-app-muted">
                    Give the system the exact file you want parsed. The upload endpoint stores the source asset and saves the normalized schema in one backend step.
                  </p>
                </div>
                <BadgeChip tone={uploadPhaseToBadgeTone(uploadPhase)}>
                  {uploadPhaseLabel(uploadPhase)}
                </BadgeChip>
              </div>

              <label
                onDragEnter={(event) => {
                  event.preventDefault();
                  setIsDragActive(true);
                }}
                onDragOver={(event) => {
                  event.preventDefault();
                  setIsDragActive(true);
                }}
                onDragLeave={(event) => {
                  event.preventDefault();
                  setIsDragActive(false);
                }}
                onDrop={handleDrop}
                className={cn(
                  "mt-5 flex cursor-pointer flex-col items-center justify-center rounded-[1.6rem] border border-dashed px-6 py-12 text-center transition",
                  isDragActive
                    ? "border-app-cyan/35 bg-[rgba(15,216,255,0.08)] shadow-[0_0_0_4px_rgba(15,216,255,0.08)]"
                    : "border-white/12 bg-white/[0.03] hover:border-app-cyan/25 hover:bg-white/[0.05]"
                )}
              >
                <div className="text-base font-medium text-app-text">
                  Drag and drop a survey file
                </div>
                <p className="mt-3 max-w-md text-sm leading-6 text-app-muted">
                  Markdown, DOCX, and PDF are accepted. Markdown is best for reliable parsing; PDF is supported but may produce review-worthy warnings.
                </p>
                <div className="mt-4 flex flex-wrap justify-center gap-2">
                  {ACCEPTED_SURVEY_EXTENSIONS.map((extension) => (
                    <BadgeChip key={extension}>{extension}</BadgeChip>
                  ))}
                </div>
                <Button
                  className="mt-6"
                  type="button"
                  onClick={(event) => {
                    event.preventDefault();
                    handleBrowseClick();
                  }}
                >
                  Browse Files
                </Button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".md,.docx,.pdf"
                  className="hidden"
                  onChange={(event) =>
                    handleFileSelection(event.target.files?.[0] ?? null)
                  }
                />
              </label>

              <div className="mt-5 rounded-[1.35rem] border border-white/6 bg-white/[0.03] p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-[0.72rem] uppercase tracking-[0.24em] text-app-muted">
                      Local file selection
                    </div>
                    <div className="mt-2 text-sm text-app-text">
                      {selectedFile
                        ? selectedFile.name
                        : "No local file selected yet."}
                    </div>
                  </div>
                  {selectedFile ? (
                    <BadgeChip tone="cyan">
                      {formatFileSize(selectedFile.size)}
                    </BadgeChip>
                  ) : null}
                </div>

                <div className="mt-4 flex flex-col gap-3 sm:flex-row">
                  <Button
                    onClick={handleUploadSurvey}
                    disabled={
                      !selectedFile ||
                      isUploading ||
                      isCreatingStudy ||
                      isHydratingStudy
                    }
                  >
                    {isUploading ? "Uploading & Parsing..." : "Upload & Parse Survey"}
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => setSelectedFile(null)}
                    disabled={!selectedFile || isUploading || isHydratingStudy}
                  >
                    Clear Local File
                  </Button>
                </div>
              </div>
            </div>
          </GlassPanel>
        </RevealOnScroll>

        <RevealOnScroll delay={0.08}>
          <GlassPanel className="p-5 sm:p-6">
            <div className="rounded-[1.55rem] border border-white/5 bg-[linear-gradient(180deg,rgba(12,18,22,0.84),rgba(12,18,22,0.6))] p-5">
              <div className="rounded-[1.35rem] border border-white/6 bg-white/[0.03] p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-[0.72rem] uppercase tracking-[0.24em] text-app-muted">
                      Parser review
                    </div>
                    <p className="mt-2 text-sm leading-6 text-app-muted">
                      {isParserReviewOpen
                        ? "Upload status and parser interpretation are visible below."
                        : "Hidden by default to keep the survey preview focused."}
                    </p>
                  </div>
                  <Button
                    variant="secondary"
                    onClick={() => setIsParserReviewOpen((current) => !current)}
                  >
                    {isParserReviewOpen ? "Hide" : "Show"}
                  </Button>
                </div>

                {isParserReviewOpen ? (
                  <div className="mt-5 space-y-5 border-t border-white/6 pt-5">
                    <div
                      className={cn(
                        "rounded-2xl border px-4 py-3 text-sm leading-6",
                        status.tone === "success" &&
                          "border-app-cyan/20 bg-[rgba(15,216,255,0.08)] text-app-cyan",
                        status.tone === "warning" &&
                          "border-app-gold/20 bg-[rgba(216,186,103,0.08)] text-app-gold",
                        status.tone === "error" &&
                          "border-app-gold/20 bg-[rgba(216,186,103,0.08)] text-app-gold",
                        status.tone === "neutral" &&
                          "border-white/8 bg-white/[0.03] text-app-muted"
                      )}
                    >
                      {status.message}
                    </div>

                    <div className="grid gap-5 lg:grid-cols-[minmax(0,0.88fr)_minmax(0,1.12fr)]">
                      <ParseStatusCard
                        hasSurvey={Boolean(savedSurvey)}
                        tone={warningTone}
                        warnings={savedSurvey?.parse_warnings ?? []}
                      />
                      <WarningInterpretationCard
                        hasSurvey={Boolean(savedSurvey)}
                        warnings={savedSurvey?.parse_warnings ?? []}
                      />
                    </div>
                  </div>
                ) : null}
              </div>

              <div className="mt-5 border-t border-white/6 pt-5">
                <div className="flex flex-wrap gap-2">
                  <BadgeChip tone="cyan">Normalized Survey Schema</BadgeChip>
                  <BadgeChip tone={savedSurvey ? "cyan" : "gold"}>
                    {savedSurvey ? "Saved to backend" : "No saved survey"}
                  </BadgeChip>
                </div>
              </div>

              <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <MetaCard
                  label="Title"
                  value={surveySchema?.survey_title || "Untitled survey"}
                />
                <MetaCard
                  label="Source Format"
                  value={savedSurvey?.source_format || "Not available"}
                />
                <MetaCard
                  label="Question Count"
                  value={String(savedSurvey?.question_count ?? 0)}
                />
                <MetaCard
                  label="Saved Status"
                  value={savedSurvey?.status === "saved" ? "Saved" : "Not saved"}
                />
              </div>

              <div className="mt-5 rounded-[1.35rem] border border-white/6 bg-white/[0.03] p-4">
                <div className="text-[0.72rem] uppercase tracking-[0.24em] text-app-muted">
                  Parse quality
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <BadgeChip tone={savedSurvey ? (warningTone === "success" ? "cyan" : "gold") : "neutral"}>
                    {savedSurvey
                      ? buildWarningSummaryLabel(savedSurvey.parse_warnings ?? [])
                      : "Awaiting upload"}
                  </BadgeChip>
                  {savedSurvey?.source_filename ? (
                    <BadgeChip>{savedSurvey.source_filename}</BadgeChip>
                  ) : null}
                </div>
              </div>

              <div className="mt-5">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="text-[0.72rem] uppercase tracking-[0.24em] text-app-muted">
                    Preview Mode
                  </div>
                  <div className="inline-flex rounded-full border border-white/8 bg-white/[0.03] p-1">
                    <PreviewModeButton
                      active={previewMode === "form"}
                      onClick={() => setPreviewMode("form")}
                    >
                      Form-style
                    </PreviewModeButton>
                    <PreviewModeButton
                      active={previewMode === "table"}
                      onClick={() => setPreviewMode("table")}
                    >
                      Table
                    </PreviewModeButton>
                  </div>
                </div>

                <div className="mt-4 text-sm text-app-muted">
                  {savedSurvey?.question_count
                    ? `Showing ${previewQuestions.length} of ${savedSurvey.question_count} questions`
                    : "Upload a survey to preview the normalized schema."}
                </div>

                <div className="mt-4 space-y-3">
                  {previewMode === "form" ? (
                    <QuestionFormPreview questions={previewQuestions} />
                  ) : (
                    <QuestionTablePreview questions={previewQuestions} />
                  )}
                </div>
              </div>

              <div className="mt-5 flex flex-wrap gap-3">
                <Button
                  variant="secondary"
                  onClick={() => setShowAllQuestions((current) => !current)}
                  disabled={!surveyQuestions.length}
                >
                  {showAllQuestions ? "Show Fewer Questions" : "View Full Survey Details"}
                </Button>
              </div>
            </div>
          </GlassPanel>
        </RevealOnScroll>
      </div>
    </SectionWrapper>
  );
}

function classifyWarningTone(warnings: string[]) {
  if (warnings.length === 0) {
    return "success" as const;
  }

  const parserNotesOnly = warnings.every(isParserNote);
  return parserNotesOnly ? ("success" as const) : ("warning" as const);
}

function buildSavedSurveyMessage(warnings: string[]) {
  if (warnings.length === 0) {
    return "Survey uploaded, parsed, and saved successfully.";
  }

  const parserNotesOnly = warnings.every(isParserNote);

  return parserNotesOnly
    ? "Survey parsed successfully. The parser added interpretation notes, but the normalized schema is saved and ready for review."
    : "Survey parsed and saved with warnings. Review the normalized schema before moving on.";
}

function buildWarningSummaryLabel(warnings: string[]) {
  if (warnings.length === 0) {
    return "Parsed cleanly";
  }

  const parserNotesOnly = warnings.every(isParserNote);

  return parserNotesOnly ? "Parser notes" : `${warnings.length} warnings`;
}

function isParserNote(warning: string) {
  const normalized = warning.trim().toLowerCase();
  return normalized.startsWith("inferred ") || normalized.startsWith("expanded matrix question ");
}

function uploadPhaseToBadgeTone(phase: UploadPhase) {
  if (phase === "success") {
    return "cyan" as const;
  }
  if (phase === "warning" || phase === "error") {
    return "gold" as const;
  }
  return undefined;
}

function uploadPhaseLabel(phase: UploadPhase) {
  switch (phase) {
    case "selected":
      return "File selected";
    case "uploading":
      return "Uploading";
    case "success":
      return "Saved";
    case "warning":
      return "Saved with warnings";
    case "error":
      return "Upload issue";
    default:
      return "Awaiting file";
  }
}

function formatFileSize(bytes: number) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function ParseStatusCard({
  hasSurvey,
  tone,
  warnings,
}: {
  hasSurvey: boolean;
  tone: "success" | "warning";
  warnings: string[];
}) {
  return (
    <div className="rounded-[1.35rem] border border-white/6 bg-white/[0.03] p-4">
      <div className="flex flex-wrap items-center gap-2">
        <BadgeChip tone={hasSurvey ? (tone === "success" ? "cyan" : "gold") : "neutral"}>
          {hasSurvey ? buildWarningSummaryLabel(warnings) : "Awaiting upload"}
        </BadgeChip>
        <BadgeChip>
          {hasSurvey
            ? `${warnings.length} parser note${warnings.length === 1 ? "" : "s"}`
            : "No schema yet"}
        </BadgeChip>
      </div>
      <p className="mt-3 text-sm leading-6 text-app-muted">
        {!hasSurvey
          ? "Upload a survey file to generate the normalized schema and parser notes."
          : warnings.length === 0
          ? "The parser returned a clean normalized schema with no warnings."
          : tone === "success"
            ? "The parser added lightweight interpretation notes, which is normal for many survey formats."
            : "The parser succeeded, but there are warnings you should review before moving forward."}
      </p>
    </div>
  );
}

function WarningInterpretationCard({
  hasSurvey,
  warnings,
}: {
  hasSurvey: boolean;
  warnings: string[];
}) {
  return (
    <div className="rounded-[1.35rem] border border-white/6 bg-white/[0.03] p-4">
      <div className="text-[0.72rem] uppercase tracking-[0.24em] text-app-muted">
        Parser interpretation
      </div>
      {!hasSurvey ? (
        <p className="mt-3 text-sm leading-6 text-app-muted">
          Once a survey is uploaded, parser warnings and inference notes will appear here.
        </p>
      ) : warnings.length > 0 ? (
        <ul className="mt-3 space-y-2 text-sm leading-6 text-app-text">
          {warnings.map((warning) => (
            <li key={warning} className="rounded-xl border border-white/6 bg-black/10 px-3 py-2">
              {warning}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-sm leading-6 text-app-muted">
          No parser warnings were returned for the current saved survey.
        </p>
      )}
    </div>
  );
}

function PreviewModeButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-full px-4 py-2 text-sm transition",
        active
          ? "bg-[rgba(15,216,255,0.14)] text-app-cyan"
          : "text-app-muted hover:text-app-text"
      )}
    >
      {children}
    </button>
  );
}

function QuestionFormPreview({ questions }: { questions: SurveyQuestionPayload[] }) {
  if (questions.length === 0) {
    return (
      <div className="rounded-[1.35rem] border border-dashed border-white/10 bg-white/[0.02] px-5 py-8 text-sm leading-6 text-app-muted">
        Upload a survey to preview normalized questions here.
      </div>
    );
  }

  return (
    <>
      {questions.map((question) => (
        <div
          key={question.id}
          className="rounded-[1.35rem] border border-white/6 bg-white/[0.03] p-4"
        >
          <div className="flex flex-wrap items-center gap-2">
            <BadgeChip tone="cyan">{question.id}</BadgeChip>
            <BadgeChip>{humanizeQuestionType(question.question_type)}</BadgeChip>
            {question.required ? <BadgeChip>Required</BadgeChip> : null}
          </div>
          <div className="mt-3 text-sm leading-6 text-app-text">{question.text}</div>
          {question.help_text ? (
            <div className="mt-2 text-sm leading-6 text-app-muted">
              {question.help_text}
            </div>
          ) : null}
          <div className="mt-4">
            {renderQuestionResponseShape(question)}
          </div>
        </div>
      ))}
    </>
  );
}

function QuestionTablePreview({ questions }: { questions: SurveyQuestionPayload[] }) {
  if (questions.length === 0) {
    return (
      <div className="rounded-[1.35rem] border border-dashed border-white/10 bg-white/[0.02] px-5 py-8 text-sm leading-6 text-app-muted">
        Upload a survey to preview normalized table rows here.
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-[1.35rem] border border-white/6 bg-white/[0.03]">
      <div className="grid grid-cols-[6.5rem_7.5rem_minmax(0,1fr)_6.5rem] gap-3 border-b border-white/6 px-4 py-3 text-[0.68rem] uppercase tracking-[0.22em] text-app-muted">
        <div>ID</div>
        <div>Type</div>
        <div>Prompt</div>
        <div>Options</div>
      </div>
      {questions.map((question) => (
        <div
          key={question.id}
          className="grid grid-cols-[6.5rem_7.5rem_minmax(0,1fr)_6.5rem] gap-3 border-b border-white/6 px-4 py-3 text-sm text-app-text last:border-b-0"
        >
          <div>{question.id}</div>
          <div className="text-app-muted">{humanizeQuestionType(question.question_type)}</div>
          <div className="min-w-0 truncate">{question.text}</div>
          <div className="text-app-muted">
            {question.question_type === "likert"
              ? `${question.min_value ?? "?"}-${question.max_value ?? "?"}`
              : String(question.options?.length ?? 0)}
          </div>
        </div>
      ))}
    </div>
  );
}

function renderQuestionResponseShape(question: SurveyQuestionPayload) {
  if (question.question_type === "single_choice") {
    return (
      <ul className="space-y-2 text-sm text-app-muted">
        {(question.options ?? []).map((option) => (
          <li key={option} className="flex items-center gap-3">
            <span className="h-3 w-3 rounded-full border border-white/20" />
            <span>{option}</span>
          </li>
        ))}
      </ul>
    );
  }

  if (question.question_type === "multi_choice") {
    return (
      <ul className="space-y-2 text-sm text-app-muted">
        {(question.options ?? []).map((option) => (
          <li key={option} className="flex items-center gap-3">
            <span className="h-3.5 w-3.5 rounded-[0.35rem] border border-white/20" />
            <span>{option}</span>
          </li>
        ))}
      </ul>
    );
  }

  if (question.question_type === "likert") {
    const min = question.min_value ?? 1;
    const max = question.max_value ?? 5;
    return (
      <div className="flex flex-wrap gap-2">
        {Array.from({ length: Math.max(max - min + 1, 0) }, (_, index) => min + index).map(
          (value) => (
            <div
              key={value}
              className="inline-flex h-9 min-w-9 items-center justify-center rounded-full border border-white/10 bg-black/10 px-3 text-sm text-app-muted"
            >
              {value}
            </div>
          )
        )}
      </div>
    );
  }

  if (question.question_type === "numeric") {
    return (
      <div className="rounded-xl border border-white/10 bg-black/10 px-4 py-3 text-sm text-app-muted">
        Numeric response
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-white/10 bg-black/10 px-4 py-3 text-sm text-app-muted">
      Open-text response
    </div>
  );
}

function humanizeQuestionType(questionType: SurveyQuestionPayload["question_type"]) {
  switch (questionType) {
    case "single_choice":
      return "Single choice";
    case "multi_choice":
      return "Multi choice";
    case "open_text":
      return "Open text";
    default:
      return questionType;
  }
}

function MetaCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.15rem] border border-white/6 bg-white/[0.03] p-4">
      <div className="text-[0.68rem] uppercase tracking-[0.22em] text-app-muted">
        {label}
      </div>
      <div className="mt-2 text-sm leading-6 text-app-text">{value}</div>
    </div>
  );
}
