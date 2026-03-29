"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";

import {
  ProductEnrichmentSummary,
  ProductPayload,
  runProductImageAnalysis,
  runProductUrlAutofill,
  saveProduct,
  WorkflowReadiness,
} from "@/lib/api";
import { resolveSetupSeedSource } from "@/lib/setup-flow-utils";
import { cn } from "@/lib/utils";
import { useStudy } from "@/providers/study-provider";
import { useSectionRegistry } from "@/providers/section-registry-provider";
import { BadgeChip } from "@/components/ui/badge-chip";
import { Button } from "@/components/ui/button";
import {
  Field,
  TextAreaInput,
  TextInput,
  TokenInput,
} from "@/components/ui/form-controls";
import { GlassPanel } from "@/components/ui/glass-panel";
import { RevealOnScroll } from "@/components/ui/reveal-on-scroll";
import { SectionHeader } from "@/components/ui/section-header";
import { SectionWrapper } from "@/components/ui/section-wrapper";

type ProductDraft = {
  business_name: string;
  industry: string;
  product_name: string;
  product_type: string;
  product_description: string;
  target_customer: string;
  price_range: string;
  primary_goal: string;
  key_features: string[];
  main_use_cases: string[];
  main_pain_points_solved: string[];
  main_barriers_or_concerns: string[];
  product_image_labels: string[];
  product_image_objects: string[];
  product_image_colors: string[];
  notes: string;
};

type ProductStatusState = {
  tone: "neutral" | "success" | "error" | "warning";
  message: string;
};

const EMPTY_PRODUCT_DRAFT: ProductDraft = {
  business_name: "",
  industry: "",
  product_name: "",
  product_type: "",
  product_description: "",
  target_customer: "",
  price_range: "",
  primary_goal: "",
  key_features: [],
  main_use_cases: [],
  main_pain_points_solved: [],
  main_barriers_or_concerns: [],
  product_image_labels: [],
  product_image_objects: [],
  product_image_colors: [],
  notes: "",
};

const NEO_PRODUCT_DEFAULTS: ProductDraft = {
  business_name: "Neo Smart Living",
  industry: "Factory-built modular backyard structures",
  product_name: "Tahoe Mini",
  product_type: "Permit-light modular backyard studio",
  product_description:
    "Tahoe Mini is a compact ~117 sq ft factory-built backyard unit delivered as flat-pack panels and typically installed in about one day. It is positioned as a non-habitable accessory structure, with no plumbing and no kitchen.",
  target_customer: "Homeowners with usable backyard/property space",
  price_range: "$23,000 delivered and installed",
  primary_goal: "Validate demand, barriers, and strongest positioning for Tahoe Mini.",
  key_features: [
    "~117 sq ft compact footprint",
    "Flat-pack delivery and fast install",
    "Modular interchangeable wall system",
    "Pre-wired electrical",
    "Smart entry lock",
    "Dual-pane floor-to-ceiling glass",
    "Pitched roof with drainage",
    "Optional sound insulation and HVAC",
  ],
  main_use_cases: [
    "Home office",
    "Guest suite / short-term stay",
    "Wellness studio",
    "Adventure gear basecamp",
    "General storage / premium speed shed",
    "Creative studio",
  ],
  main_pain_points_solved: [
    "Need extra functional space without full remodel",
    "Desire simpler and faster setup versus traditional construction",
    "Need flexible backyard use cases",
  ],
  main_barriers_or_concerns: [
    "Upfront cost",
    "HOA restrictions",
    "Permit uncertainty",
    "Space and access constraints",
    "Financing options",
    "Quality and durability concerns",
    "Resale uncertainty",
  ],
  product_image_labels: ["Prefabricated building", "Modular structure", "Glass door"],
  product_image_objects: [],
  product_image_colors: [],
  notes: "Preset from Neo Smart Living challenge docs for demo mode.",
};

export function ProductSection() {
  const {
    studyId,
    study,
    createOrLoadStudy,
    isCreatingStudy,
    isHydratingStudy,
    refreshStudy,
  } = useStudy();
  const { scrollToSection } = useSectionRegistry();
  const [draft, setDraft] = useState<ProductDraft>(EMPTY_PRODUCT_DRAFT);
  const [savedSnapshot, setSavedSnapshot] = useState<string>("");
  const [studyMode, setStudyMode] = useState<string | null>(null);
  const [workflow, setWorkflow] = useState<WorkflowReadiness | null>(null);
  const [audienceSummary, setAudienceSummary] = useState("Audience not configured yet.");
  const [status, setStatus] = useState<ProductStatusState>({
    tone: "neutral",
    message: "Product context is local until you save it.",
  });
  const [isSaving, setIsSaving] = useState(false);
  const [urlInput, setUrlInput] = useState("");
  const [isRunningUrlAutofill, setIsRunningUrlAutofill] = useState(false);
  const [latestUrlAutofill, setLatestUrlAutofill] =
    useState<ProductEnrichmentSummary | null>(null);
  const [urlAutofillPreview, setUrlAutofillPreview] = useState<ProductPayload | null>(
    null
  );
  const [uploadedImageFile, setUploadedImageFile] = useState<File | null>(null);
  const [uploadedImagePreviewUrl, setUploadedImagePreviewUrl] = useState<string | null>(
    null
  );
  const [isAnalyzingImage, setIsAnalyzingImage] = useState(false);
  const [latestImageAnalysis, setLatestImageAnalysis] =
    useState<ProductEnrichmentSummary | null>(null);
  const [visualSummary, setVisualSummary] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function hydrateProduct() {
      if (!studyId || !study) {
        if (!cancelled) {
          setDraft(EMPTY_PRODUCT_DRAFT);
          setSavedSnapshot("");
          setStudyMode(null);
          setWorkflow(null);
          setAudienceSummary("Audience not configured yet.");
          setLatestUrlAutofill(null);
          setUrlAutofillPreview(null);
          setLatestImageAnalysis(null);
          setVisualSummary(null);
          setStatus({
            tone: "neutral",
            message: "Product context is local until you save it.",
          });
        }
        return;
      }

      const seedSource = resolveSetupSeedSource({
        sectionStatus: study.product?.status,
        studyMode: study.study_mode.value,
      });
      const nextDraft =
        seedSource === "saved"
          ? productPayloadToDraft(study.product?.value)
          : seedSource === "neo_default"
            ? { ...NEO_PRODUCT_DEFAULTS }
            : EMPTY_PRODUCT_DRAFT;

      if (!cancelled) {
        setDraft(nextDraft);
        setSavedSnapshot(
          study.product?.status === "saved"
            ? JSON.stringify(productDraftToPayload(nextDraft))
            : ""
        );
        setStudyMode(study.study_mode.value);
        setWorkflow(study.derived?.workflow ?? null);
        setAudienceSummary(buildAudienceContextSummary(study.audience?.value));
        setLatestUrlAutofill(study.product_enrichments?.latest_url_autofill ?? null);
        setUrlAutofillPreview(
          study.product_enrichments?.latest_url_autofill?.proposed_product_patch ??
            null
        );
        setLatestImageAnalysis(
          study.product_enrichments?.latest_image_analysis ?? null
        );
        setVisualSummary(null);
        setStatus({
          tone: seedSource === "saved" ? "success" : "neutral",
          message:
            seedSource === "saved"
              ? "Saved product context loaded from the current study."
              : seedSource === "neo_default"
                ? "Neo defaults loaded locally. Review them and save to persist canonical product state."
                : "Product context is local until you save it.",
        });
      }
    }

    void hydrateProduct();

    return () => {
      cancelled = true;
    };
  }, [
    studyId,
    study?.product?.updated_at,
    study?.product?.status,
    study?.study_mode?.value,
  ]);

  useEffect(() => {
    setWorkflow(study?.derived?.workflow ?? null);
    setAudienceSummary(buildAudienceContextSummary(study?.audience?.value));
  }, [study?.derived?.workflow, study?.audience?.updated_at]);

  useEffect(() => {
    setLatestUrlAutofill(study?.product_enrichments?.latest_url_autofill ?? null);
    setUrlAutofillPreview(
      study?.product_enrichments?.latest_url_autofill?.proposed_product_patch ??
        null
    );
    setLatestImageAnalysis(study?.product_enrichments?.latest_image_analysis ?? null);
  }, [
    study?.product_enrichments?.latest_url_autofill?.completed_at,
    study?.product_enrichments?.latest_image_analysis?.completed_at,
  ]);

  useEffect(() => {
    if (!uploadedImageFile) {
      if (uploadedImagePreviewUrl) {
        URL.revokeObjectURL(uploadedImagePreviewUrl);
      }
      setUploadedImagePreviewUrl(null);
      return;
    }

    const nextPreviewUrl = URL.createObjectURL(uploadedImageFile);
    setUploadedImagePreviewUrl(nextPreviewUrl);

    return () => URL.revokeObjectURL(nextPreviewUrl);
  }, [uploadedImageFile]);

  const draftPayload = useMemo(() => productDraftToPayload(draft), [draft]);
  const isDirty = JSON.stringify(draftPayload) !== savedSnapshot;
  const previewDescription =
    draft.product_description.trim() ||
    "Define the product clearly so respondents react to a concrete offer instead of a vague concept.";
  const visibleFeatureHighlights = draft.key_features.slice(0, 6);
  const imageSignals = latestImageAnalysis?.analysis as
    | ProductImageAnalysisSignals
    | undefined;
  const imagePatch = latestImageAnalysis?.proposed_product_patch ?? null;
  const imageAppliedToDraft = imagePatch
    ? isPatchAppliedToDraft(imagePatch, draftPayload)
    : false;
  const imageAppliedToSaved = imagePatch
    ? isPatchAppliedToSaved(imagePatch, savedSnapshot)
    : false;
  const urlPatchAppliedToDraft = urlAutofillPreview
    ? isPatchAppliedToDraft(urlAutofillPreview, draftPayload)
    : false;
  const urlPatchAppliedToSaved = urlAutofillPreview
    ? isPatchAppliedToSaved(urlAutofillPreview, savedSnapshot)
    : false;

  function updateDraft<K extends keyof ProductDraft>(key: K, value: ProductDraft[K]) {
    setDraft((current) => ({
      ...current,
      [key]: value,
    }));
  }

  async function handleSaveProduct() {
    const validationMessage = validateProductDraft(draft);
    if (validationMessage) {
      setStatus({
        tone: "error",
        message: validationMessage,
      });
      return;
    }

    setIsSaving(true);
    setStatus({
      tone: "neutral",
      message: "Saving business and product context...",
    });

    try {
      const resolvedStudyId = (await createOrLoadStudy()) ?? studyId;

      if (!resolvedStudyId) {
        throw new Error("No study is available yet.");
      }

      const result = await saveProduct(resolvedStudyId, draftPayload);
      await refreshStudy(resolvedStudyId);
      setSavedSnapshot(JSON.stringify(draftPayload));
      setWorkflow(result.workflow ?? null);
      setStatus({
        tone: "success",
        message: "Business & Product Context saved successfully.",
      });
      scrollToSection("market");
    } catch (error) {
      setStatus({
        tone: "error",
        message:
          error instanceof Error
            ? error.message
            : "Unable to save the product context right now.",
      });
    } finally {
      setIsSaving(false);
    }
  }

  function handleClearSavedContext() {
    setDraft(EMPTY_PRODUCT_DRAFT);
    setStatus({
      tone: "warning",
      message:
        "The form has been reset locally. The backend does not yet support clearing saved product context because a saved product requires at least a name or description.",
    });
  }

  function handleResetToNeoDefaults() {
    setDraft(NEO_PRODUCT_DEFAULTS);
    setStatus({
      tone: "neutral",
      message: "Neo defaults loaded locally. Review and save to persist them.",
    });
  }

  async function handleRunUrlAutofill() {
    if (!urlInput.trim()) {
      setStatus({
        tone: "error",
        message: "Enter a product page URL before running autofill.",
      });
      return;
    }

    setIsRunningUrlAutofill(true);
    setStatus({
      tone: "neutral",
      message: "Running product URL autofill...",
    });

    try {
      const resolvedStudyId = (await createOrLoadStudy()) ?? studyId;
      if (!resolvedStudyId) {
        throw new Error("No study is available yet.");
      }

      const result = await runProductUrlAutofill(resolvedStudyId, urlInput.trim());
      await refreshStudy(resolvedStudyId);
      setLatestUrlAutofill(result.enrichment);
      setUrlAutofillPreview(result.enrichment?.proposed_product_patch ?? null);
      setStatus({
        tone: "success",
        message:
          "Autofill preview generated. Review it carefully before applying it to your draft.",
      });
    } catch (error) {
      setStatus({
        tone: "error",
        message:
          error instanceof Error
            ? error.message
            : "Unable to run product URL autofill right now.",
      });
    } finally {
      setIsRunningUrlAutofill(false);
    }
  }

  function handleApplyUrlAutofillToDraft() {
    if (!urlAutofillPreview) {
      return;
    }

    setDraft((current) => mergeProductPatchIntoDraft(current, urlAutofillPreview));
    setStatus({
      tone: "success",
      message:
        "URL autofill preview applied to the draft. Save when you are ready to persist it.",
    });
  }

  async function handleAnalyzeImage() {
    if (!uploadedImageFile) {
      setStatus({
        tone: "error",
        message: "Upload a product image before starting analysis.",
      });
      return;
    }

    setIsAnalyzingImage(true);
    setVisualSummary(null);
    setStatus({
      tone: "neutral",
      message: "Analyzing product image...",
    });

    try {
      const resolvedStudyId = (await createOrLoadStudy()) ?? studyId;
      if (!resolvedStudyId) {
        throw new Error("No study is available yet.");
      }

      const result = await runProductImageAnalysis(resolvedStudyId, uploadedImageFile);
      await refreshStudy(resolvedStudyId);
      setLatestImageAnalysis(result.enrichment);
      setStatus({
        tone: "success",
        message:
          "Image analysis complete. Review the extracted signals before applying them to context.",
      });
    } catch (error) {
      setStatus({
        tone: "error",
        message:
          error instanceof Error
            ? error.message
            : "Unable to analyze the product image right now.",
      });
    } finally {
      setIsAnalyzingImage(false);
    }
  }

  function handleGenerateVisualSummary() {
    if (!imageSignals) {
      setStatus({
        tone: "error",
        message: "Analyze an image before generating a visual summary.",
      });
      return;
    }

    setVisualSummary(generateVisualSummaryFromSignals(imageSignals));
    setStatus({
      tone: "neutral",
      message:
        "Visual summary generated from the extracted signals. Review it as a guide, not as source truth.",
    });
  }

  function handleApplyVisualDetailsToDraft() {
    if (!imagePatch) {
      return;
    }

    setDraft((current) => mergeProductPatchIntoDraft(current, imagePatch));
    setStatus({
      tone: "success",
      message:
        "Visual details applied to the draft. Save the product context to persist them.",
    });
  }

  return (
    <SectionWrapper id="product" scrollable contentClassName="relative">
      <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_20rem] xl:grid-cols-[minmax(0,1.02fr)_22rem] 2xl:grid-cols-[minmax(0,1.04fr)_28rem]">
        <div className="min-w-0 space-y-8">
          <RevealOnScroll>
            <SectionHeader
              index={3}
              eyebrow="Business & Product Context"
              title="Define what respondents are reacting to."
              description="This chapter frames the object of reaction: the business, the product, the customer promise, and the visual cues that make the product feel concrete instead of abstract."
            />

            <div className="mt-6 flex flex-wrap gap-3">
              <BadgeChip tone="gold">Audience Anchor</BadgeChip>
              <BadgeChip>{audienceSummary}</BadgeChip>
            </div>
          </RevealOnScroll>

          <RevealOnScroll delay={0.04}>
            <div className="flex flex-wrap gap-3">
              <Button variant="secondary" onClick={handleClearSavedContext}>
                Clear Saved Business & Product Context
              </Button>
              {studyMode === "neo_smart" ? (
                <Button variant="secondary" onClick={handleResetToNeoDefaults}>
                  Reset to Neo Defaults
                </Button>
              ) : null}
            </div>
          </RevealOnScroll>

          <RevealOnScroll delay={0.06}>
            <GlassPanel className="p-4 sm:p-5">
              <div className="rounded-[1.45rem] border border-white/5 bg-[linear-gradient(180deg,rgba(12,18,22,0.84),rgba(12,18,22,0.58))] p-5">
                <div className="flex flex-wrap items-center gap-3">
                  <BadgeChip tone="cyan">URL Autofill</BadgeChip>
                  <BadgeChip>
                    Review before applying
                  </BadgeChip>
                </div>
                <p className="mt-4 max-w-2xl text-sm leading-6 text-app-muted">
                  Paste a product page URL to generate a proposed product context.
                  The result is AI-assisted from scraped page content and should
                  always be reviewed before saving.
                </p>

                <div className="mt-5 grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto]">
                  <TextInput
                    value={urlInput}
                    onChange={setUrlInput}
                    placeholder="https://example.com/product"
                  />
                  <Button onClick={handleRunUrlAutofill} disabled={isRunningUrlAutofill}>
                    {isRunningUrlAutofill ? "Generating..." : "Auto-fill from URL"}
                  </Button>
                </div>

                {urlAutofillPreview ? (
                  <div className="mt-5 rounded-[1.3rem] border border-white/6 bg-white/[0.03] p-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <div className="text-[0.72rem] uppercase tracking-[0.24em] text-app-muted">
                          Autofill preview
                        </div>
                        <div className="mt-1 text-sm text-app-text">
                          {urlAutofillPreview.product_name || "Untitled product"}
                        </div>
                      </div>
                      <Button variant="secondary" onClick={handleApplyUrlAutofillToDraft}>
                        Apply Autofill to Draft
                      </Button>
                    </div>
                    <div className="mt-4 grid gap-3 sm:grid-cols-2">
                      <PreviewField
                        label="Business"
                        value={
                          urlAutofillPreview.business_name ||
                          urlAutofillPreview.industry ||
                          "No business metadata returned"
                        }
                      />
                      <PreviewField
                        label="Product"
                        value={
                          urlAutofillPreview.product_name ||
                          urlAutofillPreview.product_type ||
                          "No product identity returned"
                        }
                      />
                      <PreviewField
                        label="Customer"
                        value={
                          urlAutofillPreview.target_customer ||
                          "No target customer returned"
                        }
                      />
                      <PreviewField
                        label="Price / Goal"
                        value={
                          [urlAutofillPreview.price_range, urlAutofillPreview.primary_goal]
                            .filter(Boolean)
                            .join(" • ") || "No positioning fields returned"
                        }
                      />
                    </div>
                  </div>
                ) : null}
              </div>
            </GlassPanel>
          </RevealOnScroll>

          <RevealOnScroll delay={0.08}>
            <div className="grid gap-5">
              <ProductGroupCard
                title="Business"
                description="Context that grounds the business behind the product."
              >
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Business Name">
                    <TextInput
                      value={draft.business_name}
                      onChange={(value) => updateDraft("business_name", value)}
                      placeholder="Neo Smart Living"
                    />
                  </Field>
                  <Field label="Industry">
                    <TextInput
                      value={draft.industry}
                      onChange={(value) => updateDraft("industry", value)}
                      placeholder="Factory-built modular backyard structures"
                    />
                  </Field>
                </div>
              </ProductGroupCard>

              <ProductGroupCard
                title="Product"
                description="The core object respondents will evaluate."
              >
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Product Name">
                    <TextInput
                      value={draft.product_name}
                      onChange={(value) => updateDraft("product_name", value)}
                      placeholder="Tahoe Mini"
                    />
                  </Field>
                  <Field label="Product Type">
                    <TextInput
                      value={draft.product_type}
                      onChange={(value) => updateDraft("product_type", value)}
                      placeholder="Permit-light modular backyard studio"
                    />
                  </Field>
                </div>
                <Field label="Product Description">
                  <TextAreaInput
                    value={draft.product_description}
                    onChange={(value) => updateDraft("product_description", value)}
                    placeholder="Describe what the product is, what it includes, and what makes it distinctive."
                    rows={6}
                  />
                </Field>
              </ProductGroupCard>

              <ProductGroupCard
                title="Customer & Positioning"
                description="Who the product is for and how it is positioned."
              >
                <div className="grid gap-4">
                  <Field label="Target Customer">
                    <TextInput
                      value={draft.target_customer}
                      onChange={(value) => updateDraft("target_customer", value)}
                      placeholder="Homeowners with usable backyard/property space"
                    />
                  </Field>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <Field label="Price Range">
                      <TextInput
                        value={draft.price_range}
                        onChange={(value) => updateDraft("price_range", value)}
                        placeholder="$23,000 delivered and installed"
                      />
                    </Field>
                    <Field label="Primary Goal">
                      <TextInput
                        value={draft.primary_goal}
                        onChange={(value) => updateDraft("primary_goal", value)}
                        placeholder="Validate demand, barriers, and strongest positioning"
                      />
                    </Field>
                  </div>
                </div>
              </ProductGroupCard>

              <ProductGroupCard
                title="Key Lists"
                description="Capture the recurring ideas respondents are likely to react to."
              >
                <div className="grid gap-5">
                  <Field label="Key Features">
                    <TokenInput
                      value={draft.key_features}
                      onChange={(value) => updateDraft("key_features", value)}
                      placeholder="Add a feature"
                    />
                  </Field>
                  <Field label="Main Use Cases">
                    <TokenInput
                      value={draft.main_use_cases}
                      onChange={(value) => updateDraft("main_use_cases", value)}
                      placeholder="Add a use case"
                    />
                  </Field>
                  <Field label="Main Pain Points Solved">
                    <TokenInput
                      value={draft.main_pain_points_solved}
                      onChange={(value) =>
                        updateDraft("main_pain_points_solved", value)
                      }
                      placeholder="Add a pain point solved"
                    />
                  </Field>
                  <Field label="Main Barriers or Concerns">
                    <TokenInput
                      value={draft.main_barriers_or_concerns}
                      onChange={(value) =>
                        updateDraft("main_barriers_or_concerns", value)
                      }
                      placeholder="Add a barrier or concern"
                    />
                  </Field>
                </div>
              </ProductGroupCard>

              <ProductGroupCard
                title="Notes"
                description="Optional guidance, caveats, or framing for the study."
              >
                <Field label="Notes">
                  <TextAreaInput
                    value={draft.notes}
                    onChange={(value) => updateDraft("notes", value)}
                    placeholder="Add any product framing notes, exclusions, or researcher context."
                    rows={5}
                  />
                </Field>
              </ProductGroupCard>

              <RevealOnScroll delay={0.1}>
                <div className="rounded-[1.55rem] border border-white/8 bg-[rgba(255,255,255,0.03)] p-5">
                  <div
                    className={cn(
                      "rounded-2xl border px-4 py-3 text-sm leading-6",
                      status.tone === "success" &&
                        "border-app-cyan/20 bg-[rgba(15,216,255,0.08)] text-app-cyan",
                      status.tone === "error" &&
                        "border-app-gold/20 bg-[rgba(216,186,103,0.08)] text-app-gold",
                      status.tone === "warning" &&
                        "border-app-gold/20 bg-[rgba(216,186,103,0.08)] text-app-gold",
                      status.tone === "neutral" &&
                        "border-white/8 bg-white/[0.03] text-app-muted"
                    )}
                  >
                    {status.message}
                  </div>

                  <div className="mt-5 flex flex-col gap-3 sm:flex-row">
                    <Button
                      onClick={handleSaveProduct}
                      disabled={isSaving || isCreatingStudy || isHydratingStudy}
                    >
                      {isSaving ? "Saving Product..." : "Save Business & Product Context"}
                    </Button>
                    <BadgeChip tone={isDirty ? "gold" : "cyan"}>
                      {isDirty ? "Unsaved changes" : "Saved state"}
                    </BadgeChip>
                  </div>
                </div>
              </RevealOnScroll>
            </div>
          </RevealOnScroll>
        </div>

        <RevealOnScroll
          delay={0.08}
          className="min-w-0 lg:sticky lg:top-6 lg:w-full lg:max-w-[20rem] lg:justify-self-end xl:max-w-[22rem] 2xl:max-w-[28rem]"
        >
          <div className="space-y-5">
            <GlassPanel className="p-5 sm:p-6">
              <div className="rounded-[1.55rem] border border-white/5 bg-[linear-gradient(180deg,rgba(12,18,22,0.84),rgba(12,18,22,0.6))] p-5">
                <div className="flex flex-wrap gap-2">
                  <BadgeChip tone="cyan">Manual</BadgeChip>
                  {latestUrlAutofill ? (
                    <BadgeChip tone={urlPatchAppliedToDraft || urlPatchAppliedToSaved ? "cyan" : "gold"}>
                      {urlPatchAppliedToSaved
                        ? "URL Autofill Saved"
                        : urlPatchAppliedToDraft
                          ? "URL Autofill Applied"
                          : "URL Autofill Ready"}
                    </BadgeChip>
                  ) : null}
                  {latestImageAnalysis ? (
                    <BadgeChip tone={imageAppliedToDraft || imageAppliedToSaved ? "cyan" : "gold"}>
                      {imageAppliedToSaved
                        ? "Image Analysis Saved"
                        : imageAppliedToDraft
                          ? "Image Analysis Applied"
                          : "Image Analysis Ready"}
                    </BadgeChip>
                  ) : null}
                </div>

                <div className="mt-5">
                  <div className="text-[0.72rem] uppercase tracking-[0.24em] text-app-muted">
                    Product Identity
                  </div>
                  <h3 className="mt-2 font-display text-3xl font-medium tracking-[-0.05em] text-app-text">
                    {draft.product_name.trim() || "Unnamed Product"}
                  </h3>
                  <div className="mt-3 flex flex-wrap gap-2 text-sm text-app-muted">
                    {draft.business_name ? <span>{draft.business_name}</span> : null}
                    {draft.industry ? <span>• {draft.industry}</span> : null}
                    {draft.product_type ? <span>• {draft.product_type}</span> : null}
                  </div>
                </div>

                <div className="mt-5 rounded-[1.35rem] border border-white/6 bg-white/[0.03] p-4">
                  <div className="text-[0.72rem] uppercase tracking-[0.24em] text-app-muted">
                    Respondent Reaction Model
                  </div>
                  <p className="mt-3 text-sm leading-7 text-app-text">
                    {previewDescription}
                  </p>
                </div>

                <div className="mt-5 grid gap-3 sm:grid-cols-2">
                  <MetaCard label="Target Customer" value={draft.target_customer || "Not defined"} />
                  <MetaCard label="Price Range" value={draft.price_range || "Not defined"} />
                  <MetaCard label="Primary Goal" value={draft.primary_goal || "Not defined"} />
                  <MetaCard
                    label="Workflow"
                    value={
                      workflow?.ready_for_persona_preview
                        ? "Core setup aligned"
                        : "More setup still required"
                    }
                  />
                </div>

                <div className="mt-5">
                  <div className="text-[0.72rem] uppercase tracking-[0.24em] text-app-muted">
                    Key Feature Highlights
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {visibleFeatureHighlights.length > 0 ? (
                      visibleFeatureHighlights.map((feature) => (
                        <BadgeChip key={feature}>{feature}</BadgeChip>
                      ))
                    ) : (
                      <span className="text-sm text-app-muted">
                        Add features on the left to build the respondent reaction model.
                      </span>
                    )}
                  </div>
                </div>

                {(draft.product_image_labels.length > 0 ||
                  draft.product_image_objects.length > 0 ||
                  draft.product_image_colors.length > 0) ? (
                  <div className="mt-5 rounded-[1.35rem] border border-white/6 bg-white/[0.03] p-4">
                    <div className="text-[0.72rem] uppercase tracking-[0.24em] text-app-muted">
                      Saved Visual Details
                    </div>
                    <div className="mt-3 space-y-3">
                      {draft.product_image_labels.length > 0 ? (
                        <ChipRow title="Labels" items={draft.product_image_labels} />
                      ) : null}
                      {draft.product_image_objects.length > 0 ? (
                        <ChipRow title="Objects" items={draft.product_image_objects} />
                      ) : null}
                      {draft.product_image_colors.length > 0 ? (
                        <ColorRow colors={draft.product_image_colors} />
                      ) : null}
                    </div>
                  </div>
                ) : null}
              </div>
            </GlassPanel>

            <GlassPanel className="p-5 sm:p-6">
              <div className="rounded-[1.55rem] border border-white/5 bg-[linear-gradient(180deg,rgba(12,18,22,0.84),rgba(12,18,22,0.6))] p-5">
                <div className="flex flex-wrap items-center gap-3">
                  <BadgeChip tone="gold">Visual Details</BadgeChip>
                  {imageAppliedToSaved ? (
                    <BadgeChip tone="cyan">Applied to Context</BadgeChip>
                  ) : imageAppliedToDraft ? (
                    <BadgeChip tone="cyan">Applied to Draft</BadgeChip>
                  ) : latestImageAnalysis ? (
                    <BadgeChip>Not yet applied</BadgeChip>
                  ) : null}
                </div>

                {!uploadedImagePreviewUrl && !latestImageAnalysis ? (
                  <label className="mt-5 flex cursor-pointer flex-col items-center justify-center rounded-[1.45rem] border border-dashed border-white/12 bg-white/[0.03] px-6 py-10 text-center transition hover:border-app-cyan/25 hover:bg-white/[0.05]">
                    <div className="text-sm font-medium text-app-text">
                      Upload Product Image
                    </div>
                    <p className="mt-2 max-w-xs text-sm leading-6 text-app-muted">
                      Upload a product image to enrich the product context with
                      visual cues like labels, objects, colors, and text.
                    </p>
                    <div className="mt-3 text-xs uppercase tracking-[0.22em] text-app-muted">
                      JPG, JPEG, PNG
                    </div>
                    <input
                      type="file"
                      accept=".jpg,.jpeg,.png,image/png,image/jpeg"
                      className="hidden"
                      onChange={(event) =>
                        setUploadedImageFile(event.target.files?.[0] ?? null)
                      }
                    />
                  </label>
                ) : (
                  <div className="mt-5 space-y-5">
                    <div className="grid gap-4 md:grid-cols-[minmax(0,0.88fr)_minmax(0,1.12fr)]">
                      <div className="overflow-hidden rounded-[1.35rem] border border-white/8 bg-white/[0.03]">
                        {uploadedImagePreviewUrl ? (
                          <img
                            src={uploadedImagePreviewUrl}
                            alt="Uploaded product preview"
                            className="h-full w-full object-cover"
                          />
                        ) : (
                          <div className="flex h-full min-h-56 items-center justify-center px-6 text-center text-sm text-app-muted">
                            Previously analyzed image data is available, but the
                            backend does not yet expose asset retrieval for image
                            preview reloads.
                          </div>
                        )}
                      </div>

                      <div className="space-y-4">
                        <div className="flex flex-wrap gap-3">
                          <label className="cursor-pointer">
                            <span className="inline-flex items-center justify-center rounded-2xl border border-app-border bg-white/[0.03] px-4 py-3 text-sm font-medium text-app-text transition hover:border-app-cyan/30 hover:text-app-cyan">
                              Upload Product Image
                            </span>
                            <input
                              type="file"
                              accept=".jpg,.jpeg,.png,image/png,image/jpeg"
                              className="hidden"
                              onChange={(event) =>
                                setUploadedImageFile(event.target.files?.[0] ?? null)
                              }
                            />
                          </label>
                          <Button
                            variant="secondary"
                            onClick={handleAnalyzeImage}
                            disabled={!uploadedImageFile || isAnalyzingImage}
                          >
                            {isAnalyzingImage ? "Analyzing..." : "Analyze Image"}
                          </Button>
                        </div>

                        {imageSignals ? (
                          <div className="space-y-4">
                            <ChipRow
                              title="Labels"
                              items={toStringArray(imageSignals.labels)}
                            />
                            <ChipRow
                              title="Objects"
                              items={toStringArray(imageSignals.objects)}
                            />
                            <ColorSwatchGrid colors={toColorItems(imageSignals.colors)} />
                            {String(imageSignals.text ?? "").trim() ? (
                              <details className="rounded-2xl border border-white/6 bg-white/[0.03] p-4 text-sm text-app-muted">
                                <summary className="cursor-pointer text-app-text">
                                  Detected Text
                                </summary>
                                <p className="mt-3 whitespace-pre-wrap leading-6">
                                  {String(imageSignals.text)}
                                </p>
                              </details>
                            ) : null}
                          </div>
                        ) : (
                          <div className="rounded-2xl border border-white/6 bg-white/[0.03] p-4 text-sm text-app-muted">
                            Analyze the uploaded image to extract raw visual signals.
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="grid gap-3 sm:grid-cols-2">
                      <Button
                        variant="secondary"
                        onClick={handleGenerateVisualSummary}
                        disabled={!imageSignals}
                      >
                        Generate Visual Summary
                      </Button>
                      <Button
                        variant="secondary"
                        onClick={handleApplyVisualDetailsToDraft}
                        disabled={!imagePatch}
                      >
                        Apply Visual Details to Context
                      </Button>
                    </div>

                    {visualSummary ? (
                      <div className="rounded-[1.35rem] border border-white/6 bg-white/[0.03] p-4">
                        <div className="text-[0.72rem] uppercase tracking-[0.24em] text-app-muted">
                          Visual Summary
                        </div>
                        <p className="mt-3 text-sm leading-7 text-app-text">
                          {visualSummary}
                        </p>
                      </div>
                    ) : null}
                  </div>
                )}
              </div>
            </GlassPanel>
          </div>
        </RevealOnScroll>
      </div>
    </SectionWrapper>
  );
}

type ProductImageAnalysisSignals = {
  labels?: unknown[];
  objects?: unknown[];
  colors?: Array<{ hex?: string; percentage?: number }>;
  text?: string;
  logos?: unknown[];
  web_entities?: unknown[];
};

function ProductGroupCard({
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
      <div className="rounded-[1.45rem] border border-white/5 bg-[linear-gradient(180deg,rgba(12,18,22,0.84),rgba(12,18,22,0.58))] p-5">
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

function PreviewField({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-white/6 bg-white/[0.03] p-4">
      <div className="text-[0.68rem] uppercase tracking-[0.22em] text-app-muted">
        {label}
      </div>
      <div className="mt-2 text-sm leading-6 text-app-text">{value}</div>
    </div>
  );
}

function MetaCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-white/6 bg-white/[0.03] p-4">
      <div className="text-[0.68rem] uppercase tracking-[0.22em] text-app-muted">
        {label}
      </div>
      <div className="mt-2 text-sm leading-6 text-app-text">{value}</div>
    </div>
  );
}

function ChipRow({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) {
    return null;
  }

  return (
    <div>
      <div className="text-[0.68rem] uppercase tracking-[0.22em] text-app-muted">
        {title}
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        {items.map((item) => (
          <BadgeChip key={`${title}-${item}`}>{item}</BadgeChip>
        ))}
      </div>
    </div>
  );
}

function ColorRow({ colors }: { colors: string[] }) {
  return (
    <div>
      <div className="text-[0.68rem] uppercase tracking-[0.22em] text-app-muted">
        Colors
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        {colors.map((color) => (
          <ColorBadge key={color} label={color} />
        ))}
      </div>
    </div>
  );
}

function ColorSwatchGrid({
  colors,
}: {
  colors: Array<{ hex: string; label: string }>;
}) {
  if (colors.length === 0) {
    return null;
  }

  return (
    <div>
      <div className="text-[0.68rem] uppercase tracking-[0.22em] text-app-muted">
        Dominant Colors
      </div>
      <div className="mt-2 grid gap-2">
        {colors.map((color) => (
          <div
            key={`${color.hex}-${color.label}`}
            className="flex items-center gap-3 rounded-2xl border border-white/6 bg-white/[0.03] px-3 py-2"
          >
            <span
              className="inline-flex h-4 w-4 rounded-full border border-white/20"
              style={{ backgroundColor: color.hex }}
            />
            <span className="text-sm text-app-text">{color.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ColorBadge({ label }: { label: string }) {
  const hex = extractHexColor(label);

  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-white/8 bg-white/[0.04] px-3 py-1.5 text-sm text-app-text">
      {hex ? (
        <span
          className="inline-flex h-3 w-3 rounded-full border border-white/20"
          style={{ backgroundColor: hex }}
        />
      ) : null}
      {label}
    </span>
  );
}

function productPayloadToDraft(payload?: ProductPayload | null): ProductDraft {
  return {
    business_name: payload?.business_name ?? "",
    industry: payload?.industry ?? "",
    product_name: payload?.product_name ?? "",
    product_type: payload?.product_type ?? "",
    product_description: payload?.product_description ?? "",
    target_customer: payload?.target_customer ?? "",
    price_range: payload?.price_range ?? "",
    primary_goal: payload?.primary_goal ?? "",
    key_features: payload?.key_features ?? [],
    main_use_cases: payload?.main_use_cases ?? [],
    main_pain_points_solved: payload?.main_pain_points_solved ?? [],
    main_barriers_or_concerns: payload?.main_barriers_or_concerns ?? [],
    product_image_labels: payload?.product_image_labels ?? [],
    product_image_objects: payload?.product_image_objects ?? [],
    product_image_colors: payload?.product_image_colors ?? [],
    notes: payload?.notes ?? "",
  };
}

function productDraftToPayload(draft: ProductDraft): ProductPayload {
  return {
    business_name: draft.business_name.trim() || null,
    industry: draft.industry.trim() || null,
    product_name: draft.product_name.trim() || null,
    product_type: draft.product_type.trim() || null,
    product_description: draft.product_description.trim() || null,
    target_customer: draft.target_customer.trim() || null,
    price_range: draft.price_range.trim() || null,
    primary_goal: draft.primary_goal.trim() || null,
    key_features: draft.key_features,
    main_use_cases: draft.main_use_cases,
    main_pain_points_solved: draft.main_pain_points_solved,
    main_barriers_or_concerns: draft.main_barriers_or_concerns,
    product_image_labels: draft.product_image_labels,
    product_image_objects: draft.product_image_objects,
    product_image_colors: draft.product_image_colors,
    notes: draft.notes.trim() || null,
  };
}

function mergeProductPatchIntoDraft(
  current: ProductDraft,
  patch: ProductPayload
): ProductDraft {
  const nextPayload = {
    ...productDraftToPayload(current),
    ...patch,
  };

  return productPayloadToDraft(nextPayload);
}

function validateProductDraft(draft: ProductDraft) {
  if (!draft.product_name.trim() && !draft.product_description.trim()) {
    return "Provide at least a Product Name or Product Description before saving.";
  }

  return null;
}

function buildAudienceContextSummary(
  payload:
    | {
        state?: string | null;
        metro?: string | null;
        zip_code?: string | null;
        age_min?: number | null;
        age_max?: number | null;
        homeowner_only?: boolean;
        renter_only?: boolean;
      }
    | null
    | undefined
) {
  if (!payload) {
    return "Audience not configured yet.";
  }

  const geography = [payload.state, payload.metro, payload.zip_code ? `ZIP ${payload.zip_code}` : null]
    .filter(Boolean)
    .join(" • ");
  const age =
    payload.age_min || payload.age_max
      ? `Age ${payload.age_min ?? "Any"}-${payload.age_max ?? "Any"}`
      : "All ages";
  const housing = payload.homeowner_only
    ? "Homeowners"
    : payload.renter_only
      ? "Renters"
      : "Mixed housing";

  return [geography || "All geographies", age, housing].filter(Boolean).join(" • ");
}

function isPatchAppliedToDraft(patch: ProductPayload, payload: ProductPayload) {
  return Object.entries(patch).every(([key, value]) => {
    const currentValue = payload[key as keyof ProductPayload];

    if (value === undefined || value === null) {
      return true;
    }

    if (Array.isArray(value)) {
      return JSON.stringify(value) === JSON.stringify(currentValue ?? []);
    }

    return value === currentValue;
  });
}

function isPatchAppliedToSaved(patch: ProductPayload, savedSnapshot: string) {
  if (!savedSnapshot) {
    return false;
  }

  try {
    const savedPayload = JSON.parse(savedSnapshot) as ProductPayload;
    return isPatchAppliedToDraft(patch, savedPayload);
  } catch {
    return false;
  }
}

function toStringArray(value: unknown) {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.map((item) => String(item)).filter(Boolean);
}

function toColorItems(value: unknown) {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((item) => {
      if (!item || typeof item !== "object") {
        return null;
      }

      const candidate = item as { hex?: string; percentage?: number };
      if (!candidate.hex) {
        return null;
      }

      return {
        hex: candidate.hex,
        label:
          typeof candidate.percentage === "number"
            ? `${candidate.hex} (${candidate.percentage.toFixed(1)}%)`
            : candidate.hex,
      };
    })
    .filter((item): item is { hex: string; label: string } => Boolean(item));
}

function extractHexColor(value: string) {
  const match = value.match(/#(?:[0-9a-fA-F]{3}){1,2}/);
  return match?.[0] ?? null;
}

function generateVisualSummaryFromSignals(signals: ProductImageAnalysisSignals) {
  const labels = toStringArray(signals.labels).slice(0, 4);
  const objects = toStringArray(signals.objects).slice(0, 4);
  const colors = toColorItems(signals.colors)
    .slice(0, 3)
    .map((color) => color.label);
  const text = String(signals.text ?? "").trim();

  const firstSentenceParts = [
    labels.length > 0 ? `The image suggests ${labels.join(", ")}` : null,
    objects.length > 0 ? `with visible elements like ${objects.join(", ")}` : null,
  ].filter(Boolean);

  const secondSentenceParts = [
    colors.length > 0 ? `The dominant palette reads as ${colors.join(", ")}` : null,
    text ? `Visible text includes “${text.slice(0, 120)}${text.length > 120 ? "..." : ""}”` : null,
  ].filter(Boolean);

  return [firstSentenceParts.join(" "), secondSentenceParts.join(". ")].filter(Boolean).join(". ") + ".";
}
