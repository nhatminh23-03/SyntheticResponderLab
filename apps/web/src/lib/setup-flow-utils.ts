export type SetupSeedSource = "saved" | "neo_default" | "empty";
export type StudyModeValue = "neo_smart" | "general";

export function resolveSetupSeedSource({
  sectionStatus,
  studyMode,
}: {
  sectionStatus?: string | null;
  studyMode?: string | null;
}): SetupSeedSource {
  if (sectionStatus === "saved") {
    return "saved";
  }

  if (studyMode === "neo_smart") {
    return "neo_default";
  }

  return "empty";
}

export function buildStudyModeStatusMessage(
  mode: StudyModeValue,
  preservedSavedSections: string[]
) {
  const label =
    mode === "neo_smart"
      ? "Neo Smart Living Demo"
      : "General Custom Study";

  if (preservedSavedSections.length > 0) {
    return `${label} saved. Kept your saved inputs in: ${preservedSavedSections.join(", ")}.`;
  }

  return `${label} saved. Next step: Audience setup.`;
}

export type OwnershipFilter = "any" | "homeowner_only" | "renter_only";

/**
 * Ownership is stored as two independent "only" booleans, but they describe a
 * single three-way choice. Both true is contradictory ("only owners" and "only
 * renters" is the empty set) and the backend rejects it, so the UI drives one
 * selector through these helpers instead of two toggles.
 *
 * Both false is the meaningful "include owners and renters" state: the persona
 * sampler applies no ownership constraint and draws the real population mix.
 */
export function toOwnershipFilter(flags: {
  homeowner_only: boolean;
  renter_only: boolean;
}): OwnershipFilter {
  if (flags.homeowner_only) {
    return "homeowner_only";
  }
  if (flags.renter_only) {
    return "renter_only";
  }
  return "any";
}

export function fromOwnershipFilter(value: OwnershipFilter): {
  homeowner_only: boolean;
  renter_only: boolean;
} {
  return {
    homeowner_only: value === "homeowner_only",
    renter_only: value === "renter_only",
  };
}
