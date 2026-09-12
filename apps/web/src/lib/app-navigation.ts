export const standaloneAppLinks = [
  { href: "/interview", label: "Student Interview" },
] as const;

export function canOpenCompactAppMenu(
  workflowNavigationLocked: boolean,
  standaloneDestinationCount: number
) {
  return !workflowNavigationLocked || standaloneDestinationCount > 0;
}
