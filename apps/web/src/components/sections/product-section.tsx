"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";

import {
  ProductEnrichmentSummary,
  ProductPayload,
  runProductImageAnalysis,
  runProductUrlAutofill,
  saveProduct,
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
  industry: "Backyard modular studios",
  product_name: "Tahoe Mini",
  product_type: "Fast-install modular backyard studio",
  product_description:
    "Tahoe Mini is a compact ~117 sq ft backyard unit delivered as flat-pack panels and usually installed in about a day. It is positioned as a non-habitable accessory structure, with no plumbing and no kitchen.",
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
  notes: "Demo preset based on Neo Smart Living materials.",
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
  const [status, setStatus] = useState<ProductStatusState>({
    tone: "neutral",
    message: "No product details saved yet. Save when you're ready.",
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
          setLatestUrlAutofill(null);
          setUrlAutofillPreview(null);
          setLatestImageAnalysis(null);
          setVisualSummary(null);
          setStatus({
            tone: "neutral",
            message: "No product details saved yet. Save when you're ready.",
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
              ? "Loaded your saved product details."
              : seedSource === "neo_default"
                ? "Neo demo defaults loaded. Review and save if you want to keep them."
                : "No product details saved yet. Save when you're ready.",
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
      message: "Saving product details...",
    });

    try {
      const resolvedStudyId = (await createOrLoadStudy()) ?? studyId;

      if (!resolvedStudyId) {
        throw new Error("No study is available yet.");
      }

      await saveProduct(resolvedStudyId, draftPayload);
      await refreshStudy(resolvedStudyId);
      setSavedSnapshot(JSON.stringify(draftPayload));
      setStatus({
        tone: "success",
        message: "Product details saved.",
      });
      scrollToSection("market");
    } catch (error) {
      setStatus({
        tone: "error",
        message:
          error instanceof Error
            ? error.message
            : "Unable to save product details right now.",
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
        "Product details were reset locally. Save new details if you want to replace what is currently saved.",
    });
  }

  function handleResetToNeoDefaults() {
    setDraft(NEO_PRODUCT_DEFAULTS);
    setStatus({
      tone: "neutral",
      message: "Neo demo defaults loaded. Review and save if you want to keep them.",
    });
  }

  async function handleRunUrlAutofill() {
    if (!urlInput.trim()) {
      setStatus({
        tone: "error",
        message: "Add a product page URL first.",
      });
      return;
    }

    setIsRunningUrlAutofill(true);
    setStatus({
      tone: "neutral",
      message: "Generating draft details from URL...",
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
        message: "Autofill draft is ready. Review it and apply what you want.",
      });
    } catch (error) {
      setStatus({
        tone: "error",
        message:
          error instanceof Error
            ? error.message
            : "Unable to generate details from URL right now.",
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
      message: "Autofill details added to your draft. Save when you're ready.",
    });
  }

  async function handleAnalyzeImage() {
    if (!uploadedImageFile) {
      setStatus({
        tone: "error",
        message: "Upload a product image first.",
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
        message: "Image analysis is ready. Review the details before applying them.",
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
        message: "Run image analysis before generating a visual summary.",
      });
      return;
    }

    setVisualSummary(generateVisualSummaryFromSignals(imageSignals));
    setStatus({
      tone: "neutral",
      message: "Visual summary generated. Use it as a draft and refine as needed.",
    });
  }

  function handleApplyVisualDetailsToDraft() {
    if (!imagePatch) {
      return;
    }

    setDraft((current) => mergeProductPatchIntoDraft(current, imagePatch));
    setStatus({
      tone: "success",
      message: "Visual details added to your draft. Save to keep them.",
    });
  }

  return (
    <SectionWrapper
      id="product"
      scrollable
      contentClassName="relative scrollbar-hidden pr-0"
    >
      <div className="grid gap-8">
        <div className="min-w-0 space-y-8">
          <RevealOnScroll>
            <SectionHeader
              index={3}
              eyebrow="Business & Product Context"
              title="What are people reacting to?"
              description="Describe your product, who it is for, and why it matters. This gives respondents the context they need to give useful feedback."
            />
          </RevealOnScroll>

          <RevealOnScroll delay={0.04}>
            <div className="flex flex-wrap gap-3">
              <Button variant="secondary" onClick={handleClearSavedContext}>
                Reset Product Details
              </Button>
              {studyMode === "neo_smart" ? (
                <Button variant="secondary" onClick={handleResetToNeoDefaults}>
                  Load Neo Demo Defaults
                </Button>
              ) : null}
            </div>
          </RevealOnScroll>

          <RevealOnScroll delay={0.06}>
            <GlassPanel className="p-4 sm:p-5">
              <div className="rounded-[1.45rem] border border-app-border [background:var(--theme-panel-gradient)] p-5">
                <div className="flex flex-wrap items-center gap-3">
                    <BadgeChip tone="cyan">Website Autofill</BadgeChip>
                    <BadgeChip>Review before applying</BadgeChip>
                </div>
                <p className="mt-4 max-w-2xl text-sm leading-6 text-app-muted">
                    Paste a product page URL to draft product details automatically.
                    Review everything before applying it to your draft.
                </p>

                <div className="mt-5 grid gap-3 md:grid-cols-[minmax(0,1fr)_auto]">
                  <TextInput
                    value={urlInput}
                    onChange={setUrlInput}
                    placeholder="https://example.com/product"
                  />
                  <Button onClick={handleRunUrlAutofill} disabled={isRunningUrlAutofill}>
                    {isRunningUrlAutofill ? "Generating..." : "Autofill from URL"}
                  </Button>
                </div>

                {urlAutofillPreview ? (
                  <div className="mt-5 rounded-[1.3rem] border border-app-border [background:var(--status-neutral-bg)] p-4">
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
                    <div className="mt-4 grid gap-3 md:grid-cols-2">
                      <PreviewField
                        label="Business"
                        value={
                          urlAutofillPreview.business_name ||
                          urlAutofillPreview.industry ||
                          "No business details found"
                        }
                      />
                      <PreviewField
                        label="Product"
                        value={
                          urlAutofillPreview.product_name ||
                          urlAutofillPreview.product_type ||
                          "No product name or type found"
                        }
                      />
                      <PreviewField
                        label="Customer"
                        value={
                          urlAutofillPreview.target_customer ||
                          "No target audience found"
                        }
                      />
                      <PreviewField
                        label="Price / Goal"
                        value={
                          [urlAutofillPreview.price_range, urlAutofillPreview.primary_goal]
                            .filter(Boolean)
                            .join(" • ") || "No pricing or goal details found"
                        }
                      />
                    </div>
                  </div>
                ) : null}
              </div>
            </GlassPanel>
          </RevealOnScroll>

          <div className="grid gap-5">
              <ProductGroupCard
                title="Business"
                description="Basic company context behind this product."
              >
                <div className="grid gap-4 md:grid-cols-2">
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
                      placeholder="Backyard modular studios"
                    />
                  </Field>
                </div>
              </ProductGroupCard>

              <ProductGroupCard
                title="Product"
                description="The main product respondents will evaluate."
              >
                <div className="grid gap-4 md:grid-cols-2">
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
                      placeholder="Fast-install modular backyard studio"
                    />
                  </Field>
                </div>
                <Field label="Product Description">
                  <TextAreaInput
                    value={draft.product_description}
                    onChange={(value) => updateDraft("product_description", value)}
                    placeholder="Describe what it is, what is included, and why people choose it."
                    rows={6}
                  />
                </Field>
              </ProductGroupCard>

              <ProductGroupCard
                title="Customer & Positioning"
                description="Who this is for and how you position it."
              >
                <div className="grid gap-4">
                  <Field label="Target Customer">
                    <TextInput
                      value={draft.target_customer}
                      onChange={(value) => updateDraft("target_customer", value)}
                      placeholder="Homeowners with usable backyard/property space"
                    />
                  </Field>
                  <div className="grid gap-4 md:grid-cols-2">
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
                        placeholder="Understand demand, concerns, and strongest positioning"
                      />
                    </Field>
                  </div>
                </div>
              </ProductGroupCard>

              <ProductGroupCard
                title="Key Lists"
                description="Capture the points respondents are most likely to react to."
              >
                <div className="grid gap-5">
                  <Field label="Key Features">
                    <TokenInput
                      value={draft.key_features}
                      onChange={(value) => updateDraft("key_features", value)}
                      placeholder="Add a feature"
                    />
                  </Field>
                  <Field label="Top Use Cases">
                    <TokenInput
                      value={draft.main_use_cases}
                      onChange={(value) => updateDraft("main_use_cases", value)}
                      placeholder="Add a use case"
                    />
                  </Field>
                  <Field label="Problems Solved">
                    <TokenInput
                      value={draft.main_pain_points_solved}
                      onChange={(value) =>
                        updateDraft("main_pain_points_solved", value)
                      }
                      placeholder="Add a problem you solve"
                    />
                  </Field>
                  <Field label="Likely Concerns">
                    <TokenInput
                      value={draft.main_barriers_or_concerns}
                      onChange={(value) =>
                        updateDraft("main_barriers_or_concerns", value)
                      }
                      placeholder="Add a likely concern"
                    />
                  </Field>
                </div>
              </ProductGroupCard>

              <GlassPanel className="p-5 sm:p-6">
                <div className="rounded-[1.55rem] border border-app-border [background:var(--theme-panel-gradient)] p-5">
                  <div className="flex flex-wrap items-center gap-3">
                    <BadgeChip tone="gold">Visual Details</BadgeChip>
                    <BadgeChip>Optional</BadgeChip>
                    <BadgeChip tone="cyan">AI image analysis</BadgeChip>
                    {imageAppliedToSaved ? (
                      <BadgeChip tone="cyan">Applied to Context</BadgeChip>
                    ) : imageAppliedToDraft ? (
                      <BadgeChip tone="cyan">Applied to Draft</BadgeChip>
                    ) : latestImageAnalysis ? (
                      <BadgeChip>Ready to apply</BadgeChip>
                    ) : null}
                  </div>

                  <p className="mt-4 max-w-2xl text-sm leading-6 text-app-muted">
                    Optional. Upload a product image to extract labels, objects,
                    colors, and text. Review everything before applying it to
                    your draft.
                  </p>

                  {(draft.product_image_labels.length > 0 ||
                    draft.product_image_objects.length > 0 ||
                    draft.product_image_colors.length > 0) ? (
                    <div className="mt-5 rounded-[1.35rem] border border-app-border [background:var(--status-neutral-bg)] p-4">
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

                  {!uploadedImagePreviewUrl && !latestImageAnalysis ? (
                    <label className="mt-5 flex cursor-pointer flex-col items-center justify-center rounded-[1.45rem] border border-dashed border-app-border [background:var(--status-neutral-bg)] px-6 py-10 text-center transition hover:border-app-cyan/25 hover:[background:var(--button-secondary-bg-hover)]">
                      <div className="text-sm font-medium text-app-text">
                        Upload Product Image
                      </div>
                      <p className="mt-2 max-w-xs text-sm leading-6 text-app-muted">
                        Upload a product image when you want Google Vision to add
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
                      <div className="grid gap-4 lg:grid-cols-[minmax(0,0.88fr)_minmax(0,1.12fr)]">
                        <div className="overflow-hidden rounded-[1.35rem] border border-app-border [background:var(--status-neutral-bg)]">
                          {uploadedImagePreviewUrl ? (
                            <img
                              src={uploadedImagePreviewUrl}
                              alt="Uploaded product preview"
                              className="h-full w-full object-cover"
                            />
                          ) : (
                            <div className="flex h-full min-h-56 items-center justify-center px-6 text-center text-sm text-app-muted">
                              Previous analysis is available below. Upload the
                              image again if you want to preview it here.
                            </div>
                          )}
                        </div>

                        <div className="space-y-4">
                          <div className="flex flex-wrap gap-3">
                            <label className="cursor-pointer">
                              <span className="inline-flex items-center justify-center rounded-2xl border border-app-border [background:var(--status-neutral-bg)] px-4 py-3 text-sm font-medium text-app-text transition hover:border-app-cyan/30 hover:text-app-cyan">
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
                                <details className="rounded-2xl border border-app-border [background:var(--status-neutral-bg)] p-4 text-sm text-app-muted">
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
                            <div className="rounded-2xl border border-app-border [background:var(--status-neutral-bg)] p-4 text-sm text-app-muted">
                              Run image analysis to extract visual details.
                            </div>
                          )}
                        </div>
                      </div>

                      <div className="grid gap-3 md:grid-cols-2">
                        <Button
                          variant="secondary"
                          onClick={handleGenerateVisualSummary}
                          disabled={!imageSignals}
                        >
                          Draft Visual Summary
                        </Button>
                        <Button
                          variant="secondary"
                          onClick={handleApplyVisualDetailsToDraft}
                          disabled={!imagePatch}
                        >
                          Apply Visual Details to Draft
                        </Button>
                      </div>

                      {visualSummary ? (
                        <div className="rounded-[1.35rem] border border-app-border [background:var(--status-neutral-bg)] p-4">
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

              <ProductGroupCard
                title="Notes"
                description="Optional notes, caveats, or special context for this study."
              >
                <Field label="Notes">
                  <TextAreaInput
                    value={draft.notes}
                    onChange={(value) => updateDraft("notes", value)}
                    placeholder="Optional notes about assumptions, exclusions, or edge cases."
                    rows={5}
                  />
                </Field>
              </ProductGroupCard>

              <div className="rounded-[1.55rem] border border-app-border [background:var(--status-neutral-bg)] p-5">
                <div
                  className={cn(
                    "rounded-2xl border px-4 py-3 text-sm leading-6",
                    status.tone === "success" &&
                      "[border-color:var(--status-success-border)] [background:var(--status-success-bg)] [color:var(--status-success-text)]",
                    status.tone === "error" &&
                      "[border-color:var(--status-warning-border)] [background:var(--status-warning-bg)] [color:var(--status-warning-text)]",
                    status.tone === "warning" &&
                      "[border-color:var(--status-warning-border)] [background:var(--status-warning-bg)] [color:var(--status-warning-text)]",
                    status.tone === "neutral" &&
                      "border-app-border [background:var(--status-neutral-bg)] text-app-muted"
                  )}
                >
                  {status.message}
                </div>

                <div className="mt-5 flex flex-col gap-3 sm:flex-row">
                  <Button
                    onClick={handleSaveProduct}
                    disabled={isSaving || isCreatingStudy || isHydratingStudy}
                  >
                    {isSaving ? "Saving Product..." : "Save Product Details"}
                  </Button>
                  <BadgeChip tone={isDirty ? "gold" : "cyan"}>
                    {isDirty ? "Unsaved edits" : "All changes saved"}
                  </BadgeChip>
                </div>
              </div>
            </div>
        </div>
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

function PreviewField({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-app-border [background:var(--status-neutral-bg)] p-4">
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
            className="flex items-center gap-3 rounded-2xl border border-app-border [background:var(--status-neutral-bg)] px-3 py-2"
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
    <span className="inline-flex items-center gap-2 rounded-full border border-app-border [background:var(--status-neutral-bg)] px-3 py-1.5 text-sm text-app-text">
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
