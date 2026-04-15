"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";

import {
  AudiencePayload,
  saveAudience,
} from "@/lib/api";
import { resolveSetupSeedSource } from "@/lib/setup-flow-utils";
import { cn } from "@/lib/utils";
import { useStudy } from "@/providers/study-provider";
import { useSectionRegistry } from "@/providers/section-registry-provider";
import { BadgeChip } from "@/components/ui/badge-chip";
import { Button } from "@/components/ui/button";
import {
  Field,
  SelectInput,
  TextAreaInput,
  TextInput,
  TokenInput,
  ToggleChip,
} from "@/components/ui/form-controls";
import { GlassPanel } from "@/components/ui/glass-panel";
import { RevealOnScroll } from "@/components/ui/reveal-on-scroll";
import { SectionHeader } from "@/components/ui/section-header";
import { SectionWrapper } from "@/components/ui/section-wrapper";

const HOME_TYPE_OPTIONS = [
  "Any",
  "Single-family",
  "Condo",
  "Townhome",
  "Apartment",
  "Multi-family",
  "Other",
];

const US_STATES = [
  "Any",
  "Alabama",
  "Alaska",
  "Arizona",
  "Arkansas",
  "California",
  "Colorado",
  "Connecticut",
  "Delaware",
  "Florida",
  "Georgia",
  "Hawaii",
  "Idaho",
  "Illinois",
  "Indiana",
  "Iowa",
  "Kansas",
  "Kentucky",
  "Louisiana",
  "Maine",
  "Maryland",
  "Massachusetts",
  "Michigan",
  "Minnesota",
  "Mississippi",
  "Missouri",
  "Montana",
  "Nebraska",
  "Nevada",
  "New Hampshire",
  "New Jersey",
  "New Mexico",
  "New York",
  "North Carolina",
  "North Dakota",
  "Ohio",
  "Oklahoma",
  "Oregon",
  "Pennsylvania",
  "Rhode Island",
  "South Carolina",
  "South Dakota",
  "Tennessee",
  "Texas",
  "Utah",
  "Vermont",
  "Virginia",
  "Washington",
  "West Virginia",
  "Wisconsin",
  "Wyoming",
] as const;

type AudienceDraft = {
  state: string;
  metro: string;
  zip_code: string;
  age_min: string;
  age_max: string;
  income_min: string;
  income_max: string;
  household_size_min: string;
  household_size_max: string;
  homeowner_only: boolean;
  renter_only: boolean;
  work_from_home: "Any" | "Yes" | "No";
  home_type: string;
  lifestyle_tags: string[];
  notes: string;
};

type FieldErrors = Partial<Record<keyof AudienceDraft | "form", string>>;

const EMPTY_DRAFT: AudienceDraft = {
  state: "Any",
  metro: "",
  zip_code: "",
  age_min: "",
  age_max: "",
  income_min: "",
  income_max: "",
  household_size_min: "",
  household_size_max: "",
  homeowner_only: false,
  renter_only: false,
  work_from_home: "Any",
  home_type: "Any",
  lifestyle_tags: [],
  notes: "",
};

const NEO_AUDIENCE_DRAFT: AudienceDraft = {
  state: "Any",
  metro: "",
  zip_code: "",
  age_min: "25",
  age_max: "64",
  income_min: "50000",
  income_max: "199999",
  household_size_min: "",
  household_size_max: "",
  homeowner_only: true,
  renter_only: false,
  work_from_home: "Any",
  home_type: "Single-family",
  lifestyle_tags: [
    "remote work",
    "home improvement",
    "wellness",
    "hosting guests",
    "storage",
    "outdoor lifestyle",
  ],
  notes:
    "backyard-space-compatible homeowners, broad geography (not locked to a specific state or metro).",
};

export function AudienceSection() {
  const {
    studyId,
    study,
    createOrLoadStudy,
    isCreatingStudy,
    isHydratingStudy,
    refreshStudy,
  } = useStudy();
  const { scrollToSection } = useSectionRegistry();
  const [draft, setDraft] = useState<AudienceDraft>(EMPTY_DRAFT);
  const [savedSnapshot, setSavedSnapshot] = useState<string>("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [status, setStatus] = useState<{
    tone: "neutral" | "success" | "error";
    message: string;
  }>({
    tone: "neutral",
    message: "No audience saved yet. Save when you're ready.",
  });
  const [isSaving, setIsSaving] = useState(false);
  const [isClearing, setIsClearing] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function hydrateAudience() {
        if (!studyId || !study) {
          if (!cancelled) {
            setDraft(EMPTY_DRAFT);
            setSavedSnapshot("");
            setStatus({
              tone: "neutral",
              message: "No audience saved yet. Save when you're ready.",
          });
        }
        return;
      }

      if (!cancelled) {
        const seedSource = resolveSetupSeedSource({
          sectionStatus: study.audience?.status,
          studyMode: study.study_mode.value,
        });
        const nextDraft =
          seedSource === "saved"
            ? audiencePayloadToDraft(study.audience?.value)
            : seedSource === "neo_default"
              ? {
                  ...NEO_AUDIENCE_DRAFT,
                  lifestyle_tags: [...NEO_AUDIENCE_DRAFT.lifestyle_tags],
                }
              : EMPTY_DRAFT;

        setDraft(nextDraft);
        setSavedSnapshot(
          study.audience?.status === "saved"
            ? JSON.stringify(draftToPayload(nextDraft))
            : ""
        );
        setFieldErrors({});
        setStatus({
          tone: study.audience?.status === "saved" ? "success" : "neutral",
          message:
            seedSource === "saved"
              ? "Loaded your saved audience."
              : seedSource === "neo_default"
                ? "Neo audience defaults loaded. Review and save if you want to keep them."
                : "No audience saved yet. Save when you're ready.",
        });
      }
    }

    void hydrateAudience();

    return () => {
      cancelled = true;
    };
  }, [
    studyId,
    study?.audience?.updated_at,
    study?.audience?.status,
    study?.study_mode?.value,
  ]);

  const draftPayload = useMemo(() => draftToPayload(draft), [draft]);
  const isDirty = JSON.stringify(draftPayload) !== savedSnapshot;

  function updateDraft<K extends keyof AudienceDraft>(key: K, value: AudienceDraft[K]) {
    setDraft((current) => ({
      ...current,
      [key]: value,
    }));
  }

  async function handleSave() {
    const validationErrors = validateDraft(draft);
    setFieldErrors(validationErrors);

    if (Object.keys(validationErrors).length > 0) {
      setStatus({
        tone: "error",
        message: validationErrors.form ?? "Please fix the highlighted audience fields before saving.",
      });
      return;
    }

    setIsSaving(true);
    setStatus({
      tone: "neutral",
      message: "Saving audience...",
    });

    try {
      const resolvedStudyId = (await createOrLoadStudy()) ?? studyId;

      if (!resolvedStudyId) {
        throw new Error("No study is available yet.");
      }

      const result = await saveAudience(resolvedStudyId, draftPayload);
      await refreshStudy(resolvedStudyId);
      setSavedSnapshot(JSON.stringify(draftPayload));
      setFieldErrors({});
      setStatus({
        tone: "success",
        message: "Audience saved.",
      });
      scrollToSection("product");
    } catch (error) {
      setStatus({
        tone: "error",
        message:
          error instanceof Error
            ? error.message
            : "Unable to save audience right now.",
      });
    } finally {
      setIsSaving(false);
    }
  }

  async function handleClear() {
    setIsClearing(true);
    setDraft(EMPTY_DRAFT);
    setFieldErrors({});
    setStatus({
      tone: "neutral",
      message: "Resetting audience...",
    });

    try {
      const resolvedStudyId = (await createOrLoadStudy()) ?? studyId;

      if (!resolvedStudyId) {
        setSavedSnapshot("");
        setStatus({
          tone: "success",
          message: "Audience reset locally. Save if you want to keep this reset.",
        });
        return;
      }

      const emptyPayload = draftToPayload(EMPTY_DRAFT);
      const result = await saveAudience(resolvedStudyId, emptyPayload);
      await refreshStudy(resolvedStudyId);
      setSavedSnapshot(JSON.stringify(emptyPayload));
      setStatus({
        tone: "success",
        message: "Audience reset saved.",
      });
    } catch (error) {
      setStatus({
        tone: "error",
        message:
          error instanceof Error
            ? error.message
            : "Unable to reset saved audience right now.",
      });
    } finally {
      setIsClearing(false);
    }
  }

  return (
    <SectionWrapper
      id="audience"
      scrollable
      contentClassName="relative scrollbar-hidden pr-0"
    >
      <div className="grid gap-8">
        <div className="space-y-8">
          <RevealOnScroll>
            <SectionHeader
              index={2}
              eyebrow="Audience Builder"
              title="Who do you want to hear from?"
              description="Set the audience for your synthetic respondents. These filters define who gets represented in the simulation."
            />
          </RevealOnScroll>

          <RevealOnScroll delay={0.04}>
            <div className="grid gap-5 lg:grid-cols-2">
              <AudienceGroupCard
                title="Geography"
                description="Use location filters only when you need a narrower audience."
              >
                <Field
                  label="State"
                  hint="Select a state to focus results. Keep Any for nationwide coverage."
                >
                  <SelectInput
                    value={draft.state}
                    onChange={(value) => updateDraft("state", value)}
                    options={US_STATES.map((state) => ({
                      label: state,
                      value: state,
                    }))}
                  />
                </Field>
                <Field label="Metro" hint="Optional. Add a metro area to narrow location.">
                  <TextInput
                    value={draft.metro}
                    onChange={(value) => updateDraft("metro", value)}
                    placeholder="San Francisco-Oakland-Berkeley"
                  />
                </Field>
                <Field
                  label="ZIP Code"
                  hint="Optional. Use ZIP code for precise local targeting."
                  error={fieldErrors.zip_code}
                >
                  <TextInput
                    value={draft.zip_code}
                    onChange={(value) => updateDraft("zip_code", value)}
                    placeholder="94105"
                    inputMode="numeric"
                  />
                </Field>
              </AudienceGroupCard>

              <AudienceGroupCard
                title="Demographics"
                description="Leave numeric fields blank to keep the audience broad."
              >
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Age Min" error={fieldErrors.age_min}>
                    <TextInput
                      value={draft.age_min}
                      onChange={(value) => updateDraft("age_min", value)}
                      placeholder="25"
                      inputMode="numeric"
                    />
                  </Field>
                  <Field label="Age Max" error={fieldErrors.age_max}>
                    <TextInput
                      value={draft.age_max}
                      onChange={(value) => updateDraft("age_max", value)}
                      placeholder="64"
                      inputMode="numeric"
                    />
                  </Field>
                  <Field label="Income Min" error={fieldErrors.income_min}>
                    <TextInput
                      value={draft.income_min}
                      onChange={(value) => updateDraft("income_min", value)}
                      placeholder="50000"
                      inputMode="numeric"
                    />
                  </Field>
                  <Field label="Income Max" error={fieldErrors.income_max}>
                    <TextInput
                      value={draft.income_max}
                      onChange={(value) => updateDraft("income_max", value)}
                      placeholder="200000"
                      inputMode="numeric"
                    />
                  </Field>
                  <Field
                    label="Household Size Min"
                    error={fieldErrors.household_size_min}
                  >
                    <TextInput
                      value={draft.household_size_min}
                      onChange={(value) => updateDraft("household_size_min", value)}
                      placeholder="1"
                      inputMode="numeric"
                    />
                  </Field>
                  <Field
                    label="Household Size Max"
                    error={fieldErrors.household_size_max}
                  >
                    <TextInput
                      value={draft.household_size_max}
                      onChange={(value) => updateDraft("household_size_max", value)}
                      placeholder="5"
                      inputMode="numeric"
                    />
                  </Field>
                </div>
              </AudienceGroupCard>

              <AudienceGroupCard
                title="Housing"
                description="Use these only if housing profile matters for this study."
              >
                <div className="flex flex-wrap gap-3">
                  <ToggleChip
                    checked={draft.homeowner_only}
                    onChange={(checked) => updateDraft("homeowner_only", checked)}
                    label="Homeowner Only"
                  />
                  <ToggleChip
                    checked={draft.renter_only}
                    onChange={(checked) => updateDraft("renter_only", checked)}
                    label="Renter Only"
                  />
                </div>
                {fieldErrors.form ? (
                  <p className="text-xs leading-5 text-app-gold">{fieldErrors.form}</p>
                ) : null}
                <Field label="Work From Home">
                  <SelectInput
                    value={draft.work_from_home}
                    onChange={(value) =>
                      updateDraft(
                        "work_from_home",
                        value as AudienceDraft["work_from_home"]
                      )
                    }
                    options={[
                      { label: "Any", value: "Any" },
                      { label: "Yes", value: "Yes" },
                      { label: "No", value: "No" },
                    ]}
                  />
                </Field>
                <Field label="Home Type">
                  <SelectInput
                    value={draft.home_type}
                    onChange={(value) => updateDraft("home_type", value)}
                    options={HOME_TYPE_OPTIONS.map((option) => ({
                      label: option,
                      value: option,
                    }))}
                  />
                </Field>
              </AudienceGroupCard>

              <AudienceGroupCard
                title="Lifestyle & Notes"
                description="Add optional context to describe the people you want to hear from."
              >
                <Field
                  label="Lifestyle Tags"
                  hint="Type a tag and press Enter, or use Add Tag. Remove any tag you do not want."
                >
                  <TokenInput
                    value={draft.lifestyle_tags}
                    onChange={(value) => updateDraft("lifestyle_tags", value)}
                    placeholder="Add a lifestyle tag (for example: remote work)"
                    addLabel="Add Tag"
                  />
                </Field>
                <Field label="Notes">
                  <TextAreaInput
                    value={draft.notes}
                    onChange={(value) => updateDraft("notes", value)}
                    placeholder="Optional notes about inclusions, exclusions, or edge cases."
                    rows={5}
                  />
                </Field>
              </AudienceGroupCard>
            </div>
          </RevealOnScroll>
        </div>

        <RevealOnScroll delay={0.1}>
          <div className="rounded-[1.55rem] border border-app-border [background:var(--status-neutral-bg)] p-5">
            <div
              className={cn(
                "rounded-2xl border px-4 py-3 text-sm leading-6",
                status.tone === "success" &&
                  "[border-color:var(--status-success-border)] [background:var(--status-success-bg)] [color:var(--status-success-text)]",
                status.tone === "error" &&
                  "[border-color:var(--status-warning-border)] [background:var(--status-warning-bg)] [color:var(--status-warning-text)]",
                status.tone === "neutral" &&
                  "border-app-border [background:var(--status-neutral-bg)] text-app-muted"
              )}
            >
              {status.message}
            </div>

            <div className="mt-5 flex flex-col gap-3 sm:flex-row">
              <Button
                onClick={handleSave}
                disabled={isSaving || isCreatingStudy || isHydratingStudy}
              >
                {isSaving ? "Saving Audience..." : "Save Audience"}
              </Button>
              <Button
                variant="secondary"
                onClick={handleClear}
                disabled={isClearing || isSaving || isHydratingStudy}
              >
                {isClearing ? "Resetting..." : "Reset Audience"}
              </Button>
              <BadgeChip tone={isDirty ? "gold" : "cyan"}>
                {isDirty ? "Unsaved edits" : "All changes saved"}
              </BadgeChip>
            </div>
          </div>
        </RevealOnScroll>
      </div>
    </SectionWrapper>
  );
}

function AudienceGroupCard({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <GlassPanel className="p-4 sm:p-5">
      <div className="rounded-[1.45rem] border border-app-border [background:var(--theme-panel-gradient)] p-5">
        <div className="mb-5">
          <div className="text-[0.72rem] uppercase tracking-[0.24em] text-app-gold">
            {title}
          </div>
          <p className="mt-2 text-sm leading-6 text-app-muted">{description}</p>
        </div>
        <div className="space-y-4">{children}</div>
      </div>
    </GlassPanel>
  );
}

function audiencePayloadToDraft(payload?: AudiencePayload | null): AudienceDraft {
  return {
    state: payload?.state ?? "Any",
    metro: payload?.metro ?? "",
    zip_code: payload?.zip_code ?? "",
    age_min: optionalTextFromNumber(payload?.age_min),
    age_max: optionalTextFromNumber(payload?.age_max),
    income_min: optionalTextFromNumber(payload?.income_min),
    income_max: optionalTextFromNumber(payload?.income_max),
    household_size_min: optionalTextFromNumber(payload?.household_size_min),
    household_size_max: optionalTextFromNumber(payload?.household_size_max),
    homeowner_only: payload?.homeowner_only ?? false,
    renter_only: payload?.renter_only ?? false,
    work_from_home:
      payload?.work_from_home === true
        ? "Yes"
        : payload?.work_from_home === false
          ? "No"
          : "Any",
    home_type: payload?.home_type ?? "Any",
    lifestyle_tags: payload?.lifestyle_tags ?? [],
    notes: payload?.notes ?? "",
  };
}

function optionalTextFromNumber(value?: number | null) {
  return value === null || value === undefined ? "" : String(value);
}

function parseOptionalNumber(value: string) {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }

  const numericValue = Number(trimmed);
  if (!Number.isFinite(numericValue) || !Number.isInteger(numericValue)) {
    throw new Error("Please enter whole numbers only.");
  }

  return numericValue;
}

function draftToPayload(draft: AudienceDraft): AudiencePayload {
  return {
    state: draft.state === "Any" ? null : draft.state || null,
    metro: draft.metro.trim() || null,
    zip_code: draft.zip_code.trim() || null,
    age_min: draft.age_min.trim() ? Number(draft.age_min) : null,
    age_max: draft.age_max.trim() ? Number(draft.age_max) : null,
    income_min: draft.income_min.trim() ? Number(draft.income_min) : null,
    income_max: draft.income_max.trim() ? Number(draft.income_max) : null,
    household_size_min: draft.household_size_min.trim()
      ? Number(draft.household_size_min)
      : null,
    household_size_max: draft.household_size_max.trim()
      ? Number(draft.household_size_max)
      : null,
    homeowner_only: draft.homeowner_only,
    renter_only: draft.renter_only,
    work_from_home:
      draft.work_from_home === "Any"
        ? null
        : draft.work_from_home === "Yes",
    home_type: draft.home_type === "Any" ? null : draft.home_type || null,
    lifestyle_tags: draft.lifestyle_tags,
    notes: draft.notes.trim() || null,
  };
}

function validateDraft(draft: AudienceDraft): FieldErrors {
  const errors: FieldErrors = {};

  try {
    parseOptionalNumber(draft.age_min);
  } catch {
    errors.age_min = "Whole numbers only.";
  }
  try {
    parseOptionalNumber(draft.age_max);
  } catch {
    errors.age_max = "Whole numbers only.";
  }
  try {
    parseOptionalNumber(draft.income_min);
  } catch {
    errors.income_min = "Whole numbers only.";
  }
  try {
    parseOptionalNumber(draft.income_max);
  } catch {
    errors.income_max = "Whole numbers only.";
  }
  try {
    parseOptionalNumber(draft.household_size_min);
  } catch {
    errors.household_size_min = "Whole numbers only.";
  }
  try {
    parseOptionalNumber(draft.household_size_max);
  } catch {
    errors.household_size_max = "Whole numbers only.";
  }

  const zip = draft.zip_code.trim();
  if (zip && !/^\d{5}$/.test(zip)) {
    errors.zip_code = "Use a 5-digit US ZIP code.";
  }

  const ageMin = draft.age_min.trim() ? Number(draft.age_min) : null;
  const ageMax = draft.age_max.trim() ? Number(draft.age_max) : null;
  const incomeMin = draft.income_min.trim() ? Number(draft.income_min) : null;
  const incomeMax = draft.income_max.trim() ? Number(draft.income_max) : null;
  const hhMin = draft.household_size_min.trim()
    ? Number(draft.household_size_min)
    : null;
  const hhMax = draft.household_size_max.trim()
    ? Number(draft.household_size_max)
    : null;

  if (ageMin !== null && ageMax !== null && ageMin > ageMax) {
    errors.form = "Age Min cannot be greater than Age Max.";
  }
  if (incomeMin !== null && incomeMax !== null && incomeMin > incomeMax) {
    errors.form = "Income Min cannot be greater than Income Max.";
  }
  if (hhMin !== null && hhMax !== null && hhMin > hhMax) {
    errors.form = "Household Size Min cannot be greater than Household Size Max.";
  }
  if (draft.homeowner_only && draft.renter_only) {
    errors.form = "Homeowner Only and Renter Only cannot both be selected.";
  }

  return errors;
}

function buildAudienceSummary(draft: AudienceDraft) {
  const geographyParts = [
    draft.state !== "Any" ? draft.state : null,
    draft.metro.trim() || null,
    draft.zip_code.trim() ? `ZIP ${draft.zip_code.trim()}` : null,
  ].filter(Boolean);

  return {
    geography:
      geographyParts.length > 0
        ? geographyParts.join(" • ")
        : "All geographies",
    age:
      draft.age_min || draft.age_max
        ? `${draft.age_min || "Any"} to ${draft.age_max || "Any"}`
        : "All ages",
    income:
      draft.income_min || draft.income_max
        ? `${draft.income_min || "Any"} to ${draft.income_max || "Any"}`
        : "All incomes",
    household:
      draft.household_size_min || draft.household_size_max
        ? `${draft.household_size_min || "Any"} to ${
            draft.household_size_max || "Any"
          } people`
        : "All household sizes",
    housing: [
      draft.homeowner_only ? "Homeowners only" : null,
      draft.renter_only ? "Renters only" : null,
      draft.work_from_home !== "Any"
        ? draft.work_from_home === "Yes"
          ? "Work from home"
          : "Not work from home"
        : null,
      draft.home_type !== "Any" ? draft.home_type : null,
    ]
      .filter(Boolean)
      .join(" • ") || "No housing constraints",
    lifestyle:
      draft.lifestyle_tags.length > 0
        ? draft.lifestyle_tags.join(", ")
        : "All lifestyle profiles",
    notes: draft.notes.trim() || "No notes added",
  };
}
