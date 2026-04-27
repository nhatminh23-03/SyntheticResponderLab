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
