"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";

import {
  MarketCompetitorPayload,
  MarketPayload,
  saveMarket,
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

type MarketCompetitorDraft = {
  client_id: string;
  name: string;
  product_type: string;
  price_range: string;
  key_features: string[];
  strengths: string[];
  weaknesses: string[];
};

type MarketDraft = {
  category: string;
  typical_price_band: string;
  substitutes: string[];
  common_expected_features: string[];
  common_objections: string[];
  direct_competitors: MarketCompetitorDraft[];
  notes: string;
};

type MarketStatusState = {
  tone: "neutral" | "success" | "error" | "warning";
  message: string;
};

const EMPTY_MARKET_DRAFT: MarketDraft = {
  category: "",
  typical_price_band: "",
  substitutes: [],
  common_expected_features: [],
  common_objections: [],
  direct_competitors: [],
  notes: "",
};

const NEO_MARKET_DEFAULT_SEEDS: Array<
  Partial<Omit<MarketCompetitorDraft, "client_id">>
> = [
  {
    name: "Studio Shed",
    product_type: "Premium prefabricated backyard studio",
    price_range: "$25,000-$45,000+",
    key_features: ["Multiple layouts", "High-end finishes", "Design-forward exterior"],
    strengths: ["Strong design appeal", "Recognizable category benchmark"],
    weaknesses: ["Higher cost", "Can feel premium beyond budget fit"],
  },
  {
    name: "Traditional shed conversion",
    product_type: "DIY or contractor-led backyard conversion",
    price_range: "$8,000-$25,000",
    key_features: ["Lower entry cost", "Local builder flexibility", "Incremental upgrades"],
    strengths: ["Budget-friendly starting point", "Familiar alternative"],
    weaknesses: ["Less polished", "Longer and less predictable process"],
  },
];

export function MarketSection() {
  const {
    studyId,
    study,
    createOrLoadStudy,
    isCreatingStudy,
    isHydratingStudy,
    refreshStudy,
  } = useStudy();
  const { scrollToSection } = useSectionRegistry();
  const [draft, setDraft] = useState<MarketDraft>(EMPTY_MARKET_DRAFT);
  const [savedSnapshot, setSavedSnapshot] = useState("");
  const [hasSavedMarket, setHasSavedMarket] = useState(false);
  const [studyMode, setStudyMode] = useState<string | null>(null);
  const [workflow, setWorkflow] = useState<WorkflowReadiness | null>(null);
  const [audienceSummary, setAudienceSummary] = useState("Audience not configured yet.");
  const [productSummary, setProductSummary] = useState("Product not configured yet.");
  const [status, setStatus] = useState<MarketStatusState>({
    tone: "neutral",
    message: "Market context is local until you save it.",
  });
  const [isSaving, setIsSaving] = useState(false);
  const [expandedCompetitorIds, setExpandedCompetitorIds] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;

    async function hydrateMarket() {
      if (!studyId || !study) {
        if (!cancelled) {
          setDraft(EMPTY_MARKET_DRAFT);
          setSavedSnapshot("");
          setHasSavedMarket(false);
          setStudyMode(null);
          setWorkflow(null);
          setAudienceSummary("Audience not configured yet.");
          setProductSummary("Product not configured yet.");
          setExpandedCompetitorIds([]);
          setStatus({
            tone: "neutral",
            message: "Market context is local until you save it.",
          });
        }
        return;
      }

      const nextStudyMode = study.study_mode.value;
      const hasSaved = study.market?.status === "saved" && !!study.market?.value;
      const seedSource = resolveSetupSeedSource({
        sectionStatus: study.market?.status,
        studyMode: nextStudyMode,
      });
      const seededDraft =
        seedSource === "saved"
          ? marketPayloadToDraft(study.market?.value)
          : seedSource === "neo_default"
            ? createNeoMarketDefaults()
            : EMPTY_MARKET_DRAFT;

      if (!cancelled) {
        setDraft(seededDraft);
        setSavedSnapshot(
          hasSaved ? JSON.stringify(marketDraftToPayload(seededDraft)) : ""
        );
        setHasSavedMarket(hasSaved);
        setStudyMode(nextStudyMode ?? null);
        setWorkflow(study.derived?.workflow ?? null);
        setAudienceSummary(buildAudienceAnchor(study.audience?.value));
        setProductSummary(buildProductAnchor(study.product?.value));
        setExpandedCompetitorIds(
          seededDraft.direct_competitors[0]
            ? [seededDraft.direct_competitors[0].client_id]
            : []
        );
        setStatus({
          tone: hasSaved ? "success" : "neutral",
          message: hasSaved
            ? "Saved competitor and market context loaded from the current study."
            : seedSource === "neo_default"
              ? "Showing Neo market defaults as a local preview. Save to persist them."
              : "Market context is local until you save it.",
        });
      }
    }

    void hydrateMarket();

    return () => {
      cancelled = true;
    };
  }, [studyId, study?.market?.updated_at, study?.market?.status, study?.study_mode?.value]);

  useEffect(() => {
    setWorkflow(study?.derived?.workflow ?? null);
    setAudienceSummary(buildAudienceAnchor(study?.audience?.value));
    setProductSummary(buildProductAnchor(study?.product?.value));
  }, [study?.derived?.workflow, study?.audience?.updated_at, study?.product?.updated_at]);

  const draftPayload = useMemo(() => marketDraftToPayload(draft), [draft]);
  const isDirty = JSON.stringify(draftPayload) !== savedSnapshot;
  const marketNarrative = useMemo(() => buildMarketNarrative(draft), [draft]);
  const visibleCompetitors = draft.direct_competitors.filter(hasCompetitorContent);

  function updateDraft<K extends keyof MarketDraft>(key: K, value: MarketDraft[K]) {
    setDraft((current) => ({
      ...current,
      [key]: value,
    }));
  }

  function updateCompetitor<K extends keyof MarketCompetitorDraft>(
    competitorId: string,
    key: K,
    value: MarketCompetitorDraft[K]
  ) {
    setDraft((current) => ({
      ...current,
      direct_competitors: current.direct_competitors.map((competitor) =>
        competitor.client_id === competitorId
          ? { ...competitor, [key]: value }
          : competitor
      ),
    }));
  }

  function handleAddCompetitor() {
    const nextCompetitor = createCompetitorDraft();
    setDraft((current) => ({
      ...current,
      direct_competitors: [...current.direct_competitors, nextCompetitor],
    }));
    setExpandedCompetitorIds((current) => [...current, nextCompetitor.client_id]);
  }

  function handleRemoveCompetitor(competitorId: string) {
    setDraft((current) => ({
      ...current,
      direct_competitors: current.direct_competitors.filter(
        (competitor) => competitor.client_id !== competitorId
      ),
    }));
    setExpandedCompetitorIds((current) =>
      current.filter((entry) => entry !== competitorId)
    );
  }

  function toggleCompetitor(competitorId: string) {
    setExpandedCompetitorIds((current) =>
      current.includes(competitorId)
        ? current.filter((entry) => entry !== competitorId)
        : [...current, competitorId]
    );
  }

  function handleResetLocal() {
    setDraft(EMPTY_MARKET_DRAFT);
    setSavedSnapshot("");
    setHasSavedMarket(false);
    setExpandedCompetitorIds([]);
    setStatus({
      tone: "warning",
      message:
        "The backend does not expose a dedicated market clear endpoint yet. This reset is local until you save a new market frame.",
    });
  }

  function handleResetToNeoDefaults() {
    const seeded = createNeoMarketDefaults();
    setDraft(seeded);
    setExpandedCompetitorIds(
      seeded.direct_competitors.map((competitor) => competitor.client_id)
    );
    setStatus({
      tone: "neutral",
      message: "Neo market defaults loaded locally. Save to persist them.",
    });
  }

  async function handleSaveMarket() {
    const validationMessage = validateMarketDraft(draft);
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
      message: "Saving competitor and market context...",
    });

    try {
      const resolvedStudyId = (await createOrLoadStudy()) ?? studyId;

      if (!resolvedStudyId) {
        throw new Error("No study is available yet.");
      }

      const result = await saveMarket(resolvedStudyId, draftPayload);
      await refreshStudy(resolvedStudyId);
      setSavedSnapshot(JSON.stringify(draftPayload));
      setHasSavedMarket(true);
      setWorkflow(result.workflow ?? null);
      setStatus({
        tone: "success",
        message: "Competitor and market context saved successfully.",
      });
      scrollToSection("survey");
    } catch (error) {
      setStatus({
        tone: "error",
        message:
          error instanceof Error
            ? error.message
            : "Unable to save the market context right now.",
      });
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <SectionWrapper id="market" scrollable contentClassName="relative">
      <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_20rem] xl:grid-cols-[minmax(0,1.02fr)_22rem] 2xl:grid-cols-[minmax(0,1.03fr)_28rem]">
        <div className="min-w-0 space-y-8">
          <RevealOnScroll>
            <SectionHeader
              index={4}
              eyebrow="Competitor & Market Context"
              title="Define the comparison frame respondents carry into the study."
              description="This chapter captures category expectations, likely alternatives, and the objections or price anchors respondents will use when they evaluate the product."
            />

            <div className="mt-6 grid gap-3 sm:grid-cols-2">
              <ContinuityPanel label="Current Audience" value={audienceSummary} />
              <ContinuityPanel label="Current Product" value={productSummary} />
            </div>
          </RevealOnScroll>

          <RevealOnScroll delay={0.04}>
            <div className="flex flex-wrap gap-3">
              <Button variant="secondary" onClick={handleResetLocal}>
                Clear Saved Competitor &amp; Market Context
              </Button>
              {studyMode === "neo_smart" ? (
                <Button variant="secondary" onClick={handleResetToNeoDefaults}>
                  Reset to Neo Defaults
                </Button>
              ) : null}
              <BadgeChip tone={hasSavedMarket ? "cyan" : "gold"}>
                {hasSavedMarket ? "Saved market frame" : "Local draft only"}
              </BadgeChip>
            </div>
          </RevealOnScroll>

          <RevealOnScroll delay={0.06}>
            <div className="grid gap-5">
              <MarketGroupCard
                title="Market Framing"
                description="Define what feels normal in the category and what respondents will compare against."
              >
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Category">
                    <TextInput
                      value={draft.category}
                      onChange={(value) => updateDraft("category", value)}
                      placeholder="Backyard prefab studio / permit-light accessory structure"
                    />
                  </Field>
                  <Field label="Typical Price Band">
                    <TextInput
                      value={draft.typical_price_band}
                      onChange={(value) => updateDraft("typical_price_band", value)}
                      placeholder="$20,000-$35,000"
                    />
                  </Field>
                </div>

                <Field
                  label="Substitutes"
                  hint="Add alternatives respondents may mentally compare against."
                >
                  <TokenInput
                    value={draft.substitutes}
                    onChange={(value) => updateDraft("substitutes", value)}
                    placeholder="Add a substitute"
                  />
                </Field>

                <Field
                  label="Common Expected Features"
                  hint="These become the baseline expectations respondents may carry into the study."
                >
                  <TokenInput
                    value={draft.common_expected_features}
                    onChange={(value) => updateDraft("common_expected_features", value)}
                    placeholder="Add an expected feature"
                  />
                </Field>

                <Field
                  label="Common Objections"
                  hint="Use objections that feel category-wide, not just product-specific."
                >
                  <TokenInput
                    value={draft.common_objections}
                    onChange={(value) => updateDraft("common_objections", value)}
                    placeholder="Add a common objection"
                  />
                </Field>
              </MarketGroupCard>

              <MarketGroupCard
                title="Direct Competitors"
                description="Optional competitor detail helps sharpen how respondents benchmark the product, but the section still works with substitutes alone."
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex flex-wrap gap-2">
                    <BadgeChip tone="cyan">{`${visibleCompetitors.length} competitor${visibleCompetitors.length === 1 ? "" : "s"}`}</BadgeChip>
                    <BadgeChip>Expandable comparison cards</BadgeChip>
                  </div>
                  <Button variant="secondary" onClick={handleAddCompetitor}>
                    Add Competitor
                  </Button>
                </div>

                {draft.direct_competitors.length === 0 ? (
                  <div className="rounded-[1.4rem] border border-dashed border-white/10 bg-white/[0.02] px-5 py-8 text-sm leading-6 text-app-muted">
                    No direct competitors added yet. This chapter can still work with substitutes, expectations, and objections alone.
                  </div>
                ) : (
                  <div className="space-y-4">
                    {draft.direct_competitors.map((competitor, index) => {
                      const isExpanded = expandedCompetitorIds.includes(
                        competitor.client_id
                      );

                      return (
                        <CompetitorEditorCard
                          key={competitor.client_id}
                          index={index}
                          competitor={competitor}
                          expanded={isExpanded}
                          onToggle={() => toggleCompetitor(competitor.client_id)}
                          onRemove={() => handleRemoveCompetitor(competitor.client_id)}
                          onChange={updateCompetitor}
                        />
                      );
                    })}
                  </div>
                )}
              </MarketGroupCard>

              <MarketGroupCard
                title="Notes"
                description="Capture any framing guidance, scope boundaries, or competitor caveats."
              >
                <Field label="Notes">
                  <TextAreaInput
                    value={draft.notes}
                    onChange={(value) => updateDraft("notes", value)}
                    placeholder="Add any market framing notes, category caveats, or comparison guidance for the study."
                    rows={5}
                  />
                </Field>
              </MarketGroupCard>

              <RevealOnScroll delay={0.08}>
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

                  <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
                    <Button
                      onClick={handleSaveMarket}
                      disabled={isSaving || isCreatingStudy || isHydratingStudy}
                    >
                      {isSaving ? "Saving Market..." : "Save Competitor & Market Context"}
                    </Button>
                    <BadgeChip tone={isDirty ? "gold" : "cyan"}>
                      {isDirty ? "Unsaved changes" : "Saved state"}
                    </BadgeChip>
                    <BadgeChip>
                      {workflow?.ready_for_persona_preview
                        ? "Core setup aligned"
                        : "More setup still required"}
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
                  <BadgeChip tone="gold">Comparison Frame</BadgeChip>
                  <BadgeChip tone={hasSavedMarket ? "cyan" : "gold"}>
                    {hasSavedMarket ? "Saved to backend" : "Draft only"}
                  </BadgeChip>
                </div>

                <div className="mt-5 grid gap-3 sm:grid-cols-2">
                  <MetaCard label="Category" value={draft.category || "Not defined"} />
                  <MetaCard
                    label="Typical Price"
                    value={draft.typical_price_band || "Not defined"}
                  />
                </div>

                <div className="mt-5 rounded-[1.35rem] border border-white/6 bg-white/[0.03] p-4">
                  <div className="text-[0.72rem] uppercase tracking-[0.24em] text-app-muted">
                    Mental comparison frame
                  </div>
                  <p className="mt-3 text-sm leading-7 text-app-text">
                    {marketNarrative}
                  </p>
                </div>

                <div className="mt-5 space-y-4">
                  <SummaryChipBlock
                    title="Substitutes"
                    emptyLabel="No substitutes added yet."
                    items={draft.substitutes}
                  />
                  <SummaryChipBlock
                    title="Expected Features"
                    emptyLabel="No expected features added yet."
                    items={draft.common_expected_features}
                  />
                  <SummaryChipBlock
                    title="Common Objections"
                    emptyLabel="No objections added yet."
                    items={draft.common_objections}
                  />
                </div>
              </div>
            </GlassPanel>

            <GlassPanel className="p-5 sm:p-6">
              <div className="rounded-[1.55rem] border border-white/5 bg-[linear-gradient(180deg,rgba(12,18,22,0.84),rgba(12,18,22,0.6))] p-5">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-[0.72rem] uppercase tracking-[0.24em] text-app-muted">
                      Competitor Snapshot
                    </div>
                    <div className="mt-2 text-lg font-medium text-app-text">
                      {visibleCompetitors.length > 0
                        ? `${visibleCompetitors.length} benchmark${visibleCompetitors.length === 1 ? "" : "s"} in view`
                        : "No competitors added yet"}
                    </div>
                  </div>
                  <BadgeChip>{`${visibleCompetitors.length} cards`}</BadgeChip>
                </div>

                <div className="mt-5 space-y-3">
                  {visibleCompetitors.length > 0 ? (
                    visibleCompetitors.map((competitor, index) => (
                      <div
                        key={competitor.client_id}
                        className="rounded-[1.35rem] border border-white/6 bg-white/[0.03] p-4"
                      >
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <div className="text-sm font-medium text-app-text">
                              {competitor.name || `Competitor ${index + 1}`}
                            </div>
                            <div className="mt-1 text-sm text-app-muted">
                              {[
                                competitor.product_type || "Type not defined",
                                competitor.price_range || "Price not defined",
                              ].join(" • ")}
                            </div>
                          </div>
                          <BadgeChip>{`Comp ${index + 1}`}</BadgeChip>
                        </div>

                        <div className="mt-4 space-y-3">
                          <CompactList
                            title="Key features"
                            items={competitor.key_features}
                          />
                          <CompactList title="Strengths" items={competitor.strengths} />
                          <CompactList title="Weaknesses" items={competitor.weaknesses} />
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="rounded-[1.35rem] border border-dashed border-white/10 bg-white/[0.02] px-5 py-8 text-sm leading-6 text-app-muted">
                      Add direct competitors if you want a sharper benchmark. The section remains valid with substitutes and category expectations alone.
                    </div>
                  )}
                </div>
              </div>
            </GlassPanel>
          </div>
        </RevealOnScroll>
      </div>
    </SectionWrapper>
  );
}

function createCompetitorDraft(
  seed?: Partial<Omit<MarketCompetitorDraft, "client_id">>
): MarketCompetitorDraft {
  return {
    client_id: `competitor-${Math.random().toString(36).slice(2, 9)}`,
    name: seed?.name ?? "",
    product_type: seed?.product_type ?? "",
    price_range: seed?.price_range ?? "",
    key_features: seed?.key_features ?? [],
    strengths: seed?.strengths ?? [],
    weaknesses: seed?.weaknesses ?? [],
  };
}

function createNeoMarketDefaults(): MarketDraft {
  return {
    category: "Backyard prefab studio / permit-light accessory structure",
    typical_price_band: "$20,000-$35,000 (varies by install scope and options)",
    substitutes: [
      "Traditional shed",
      "Shed conversion",
      "Garage conversion",
      "Room reallocation / remodel",
      "Home renovation / addition",
      "Full ADU build",
      "Off-site coworking or rented studio",
      "Off-site wellness or fitness alternative",
    ],
    common_expected_features: [
      "Natural light and usable interior layout",
      "Durability and weather resistance",
      "Electrical readiness",
      "Fast installation",
      "Clear permitting guidance",
      "Simple setup",
      "Financing options",
      "Customization options",
    ],
    common_objections: [
      "Price sensitivity",
      "Permit or HOA uncertainty",
      "Backyard access limitations",
      "Financing availability",
      "Durability concerns",
      "Unclear resale value",
      "Quality trust concerns",
    ],
    direct_competitors: NEO_MARKET_DEFAULT_SEEDS.map((competitor) =>
      createCompetitorDraft(competitor)
    ),
    notes: "Preset market frame for Neo Smart Living demo mode.",
  };
}

function cloneMarketDraft(input: MarketDraft): MarketDraft {
  return {
    ...input,
    substitutes: [...input.substitutes],
    common_expected_features: [...input.common_expected_features],
    common_objections: [...input.common_objections],
    direct_competitors: input.direct_competitors.map((competitor) =>
      createCompetitorDraft({
        name: competitor.name,
        product_type: competitor.product_type,
        price_range: competitor.price_range,
        key_features: [...competitor.key_features],
        strengths: [...competitor.strengths],
        weaknesses: [...competitor.weaknesses],
      })
    ),
  };
}

function marketPayloadToDraft(payload?: MarketPayload | null): MarketDraft {
  if (!payload) {
    return cloneMarketDraft(EMPTY_MARKET_DRAFT);
  }

  return {
    category: payload.category ?? "",
    typical_price_band: payload.typical_price_band ?? "",
    substitutes: payload.substitutes ?? [],
    common_expected_features: payload.common_expected_features ?? [],
    common_objections: payload.common_objections ?? [],
    direct_competitors: (payload.direct_competitors ?? []).map((competitor) =>
      createCompetitorDraft({
        name: competitor.name ?? "",
        product_type: competitor.product_type ?? "",
        price_range: competitor.price_range ?? "",
        key_features: competitor.key_features ?? [],
        strengths: competitor.strengths ?? [],
        weaknesses: competitor.weaknesses ?? [],
      })
    ),
    notes: payload.notes ?? "",
  };
}

function marketDraftToPayload(draft: MarketDraft): MarketPayload {
  return {
    category: normalizeString(draft.category),
    typical_price_band: normalizeString(draft.typical_price_band),
    substitutes: cleanTokens(draft.substitutes),
    common_expected_features: cleanTokens(draft.common_expected_features),
    common_objections: cleanTokens(draft.common_objections),
    direct_competitors: draft.direct_competitors
      .map(competitorDraftToPayload)
      .filter(hasCompetitorPayloadContent),
    notes: normalizeString(draft.notes),
  };
}

function competitorDraftToPayload(
  competitor: MarketCompetitorDraft
): MarketCompetitorPayload {
  return {
    name: normalizeString(competitor.name),
    product_type: normalizeString(competitor.product_type),
    price_range: normalizeString(competitor.price_range),
    key_features: cleanTokens(competitor.key_features),
    strengths: cleanTokens(competitor.strengths),
    weaknesses: cleanTokens(competitor.weaknesses),
  };
}

function hasCompetitorPayloadContent(competitor: MarketCompetitorPayload) {
  return Boolean(
    competitor.name ||
      competitor.product_type ||
      competitor.price_range ||
      competitor.key_features?.length ||
      competitor.strengths?.length ||
      competitor.weaknesses?.length
  );
}

function hasCompetitorContent(competitor: MarketCompetitorDraft) {
  return Boolean(
    competitor.name.trim() ||
      competitor.product_type.trim() ||
      competitor.price_range.trim() ||
      competitor.key_features.length ||
      competitor.strengths.length ||
      competitor.weaknesses.length
  );
}

function validateMarketDraft(draft: MarketDraft) {
  const payload = marketDraftToPayload(draft);
  const hasMeaningfulContent = Boolean(
    payload.category ||
      payload.typical_price_band ||
      payload.substitutes?.length ||
      payload.common_expected_features?.length ||
      payload.common_objections?.length ||
      payload.direct_competitors?.length ||
      payload.notes
  );

  if (!hasMeaningfulContent) {
    return "Add at least one meaningful market field before saving.";
  }

  return null;
}

function buildAudienceAnchor(value?: Record<string, unknown> | null) {
  if (!value) {
    return "Audience not configured yet.";
  }

  const geography = [
    toOptionalString(value.state),
    toOptionalString(value.metro),
    toOptionalString(value.zip_code),
  ]
    .filter(Boolean)
    .join(" • ");

  const ageMin = toOptionalNumber(value.age_min);
  const ageMax = toOptionalNumber(value.age_max);
  const ageRange =
    ageMin !== null || ageMax !== null
      ? `Ages ${ageMin ?? "any"}-${ageMax ?? "any"}`
      : "All ages";

  return [geography || "All geographies", ageRange].filter(Boolean).join(" • ");
}

function buildProductAnchor(value?: Record<string, unknown> | null) {
  if (!value) {
    return "Product not configured yet.";
  }

  return (
    [
      toOptionalString(value.product_name),
      toOptionalString(value.product_type),
      toOptionalString(value.price_range),
    ]
      .filter(Boolean)
      .join(" • ") || "Product not configured yet."
  );
}

function buildMarketNarrative(draft: MarketDraft) {
  const substituteLead =
    draft.substitutes.length > 0
      ? summarizeList(draft.substitutes, 2)
      : "broader alternatives in the category";
  const expectationLead =
    draft.common_expected_features.length > 0
      ? summarizeList(draft.common_expected_features, 2)
      : "the expected baseline of the category";
  const objectionLead =
    draft.common_objections.length > 0
      ? summarizeList(draft.common_objections, 2)
      : "uncertainty around the category fit";

  return `Respondents may compare this against ${substituteLead}, expect ${expectationLead}, and hesitate because of ${objectionLead}.`;
}

function summarizeList(items: string[], maxVisible: number) {
  const visible = items.slice(0, maxVisible);
  if (items.length <= maxVisible) {
    return visible.join(" and ");
  }
  return `${visible.join(", ")}, and more`;
}

function cleanTokens(values: string[]) {
  return values.map((value) => value.trim()).filter(Boolean);
}

function normalizeString(value: string) {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function toOptionalString(value: unknown) {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function toOptionalNumber(value: unknown) {
  return typeof value === "number" ? value : null;
}

function MarketGroupCard({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <GlassPanel className="p-5 sm:p-6">
      <div className="rounded-[1.55rem] border border-white/5 bg-[linear-gradient(180deg,rgba(12,18,22,0.84),rgba(12,18,22,0.6))] p-5">
        <div>
          <div className="text-[0.72rem] uppercase tracking-[0.24em] text-app-muted">
            {title}
          </div>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-app-muted">
            {description}
          </p>
        </div>
        <div className="mt-5 space-y-5">{children}</div>
      </div>
    </GlassPanel>
  );
}

function ContinuityPanel({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.35rem] border border-white/8 bg-white/[0.03] p-4">
      <div className="text-[0.72rem] uppercase tracking-[0.22em] text-app-muted">
        {label}
      </div>
      <p className="mt-2 text-sm leading-6 text-app-text">{value}</p>
    </div>
  );
}

function CompetitorEditorCard({
  index,
  competitor,
  expanded,
  onToggle,
  onRemove,
  onChange,
}: {
  index: number;
  competitor: MarketCompetitorDraft;
  expanded: boolean;
  onToggle: () => void;
  onRemove: () => void;
  onChange: <K extends keyof MarketCompetitorDraft>(
    competitorId: string,
    key: K,
    value: MarketCompetitorDraft[K]
  ) => void;
}) {
  return (
    <div className="rounded-[1.45rem] border border-white/8 bg-white/[0.03] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <button
          type="button"
          onClick={onToggle}
          className="min-w-0 flex-1 text-left"
        >
          <div className="flex flex-wrap items-center gap-2">
            <BadgeChip tone="cyan">{`Competitor ${index + 1}`}</BadgeChip>
            <BadgeChip>{expanded ? "Expanded" : "Collapsed"}</BadgeChip>
          </div>
          <div className="mt-3 text-lg font-medium text-app-text">
            {competitor.name.trim() || `Unnamed Competitor ${index + 1}`}
          </div>
          <div className="mt-2 text-sm text-app-muted">
            {[
              competitor.product_type.trim() || "Product type not defined",
              competitor.price_range.trim() || "Price not defined",
            ].join(" • ")}
          </div>
        </button>

        <div className="flex gap-2">
          <Button variant="secondary" className="px-4 py-2" onClick={onToggle}>
            {expanded ? "Collapse" : "Expand"}
          </Button>
          <Button variant="secondary" className="px-4 py-2" onClick={onRemove}>
            Remove
          </Button>
        </div>
      </div>

      {expanded ? (
        <div className="mt-5 grid gap-5">
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Name">
              <TextInput
                value={competitor.name}
                onChange={(value) =>
                  onChange(competitor.client_id, "name", value)
                }
                placeholder="Studio Shed"
              />
            </Field>
            <Field label="Product Type">
              <TextInput
                value={competitor.product_type}
                onChange={(value) =>
                  onChange(competitor.client_id, "product_type", value)
                }
                placeholder="Premium prefabricated backyard studio"
              />
            </Field>
            <Field label="Price Range">
              <TextInput
                value={competitor.price_range}
                onChange={(value) =>
                  onChange(competitor.client_id, "price_range", value)
                }
                placeholder="$25,000-$45,000"
              />
            </Field>
          </div>

          <Field label="Key Features">
            <TokenInput
              value={competitor.key_features}
              onChange={(value) =>
                onChange(competitor.client_id, "key_features", value)
              }
              placeholder="Add a key feature"
            />
          </Field>

          <div className="grid gap-5 lg:grid-cols-2">
            <Field label="Strengths">
              <TokenInput
                value={competitor.strengths}
                onChange={(value) =>
                  onChange(competitor.client_id, "strengths", value)
                }
                placeholder="Add a strength"
              />
            </Field>
            <Field label="Weaknesses">
              <TokenInput
                value={competitor.weaknesses}
                onChange={(value) =>
                  onChange(competitor.client_id, "weaknesses", value)
                }
                placeholder="Add a weakness"
              />
            </Field>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function SummaryChipBlock({
  title,
  items,
  emptyLabel,
}: {
  title: string;
  items: string[];
  emptyLabel: string;
}) {
  return (
    <div className="rounded-[1.35rem] border border-white/6 bg-white/[0.03] p-4">
      <div className="text-[0.72rem] uppercase tracking-[0.24em] text-app-muted">
        {title}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {items.length > 0 ? (
          items.map((item) => <BadgeChip key={item}>{item}</BadgeChip>)
        ) : (
          <span className="text-sm text-app-muted">{emptyLabel}</span>
        )}
      </div>
    </div>
  );
}

function CompactList({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <div className="text-[0.68rem] uppercase tracking-[0.22em] text-app-muted">
        {title}
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        {items.length > 0 ? (
          items.map((item) => <BadgeChip key={`${title}-${item}`}>{item}</BadgeChip>)
        ) : (
          <span className="text-sm text-app-muted">None entered</span>
        )}
      </div>
    </div>
  );
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
