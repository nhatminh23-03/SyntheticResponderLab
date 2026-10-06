import { workflowSections, type WorkflowSectionId } from "./workflow-sections";

/**
 * Window scroll position that brings a workflow section under the sticky nav.
 * The first section scrolls to the very top, so anything above it (the app-wide
 * Demo (no AI) switch) comes back into view instead of staying hidden above the fold.
 */
export function sectionWindowScrollTop(
  id: WorkflowSectionId,
  elementDocumentTop: number,
  navHeight: number,
  isDesktop: boolean,
): number {
  if (id === workflowSections[0].id) {
    return 0;
  }
  return Math.max(0, elementDocumentTop - navHeight - (isDesktop ? 0 : 12));
}
