export const CLASSROOM_SESSION_COOKIE_NAME = "synthetic_responder_classroom_session";
// The session cookie is httpOnly, so nothing in the browser can see it. This marker rides
// beside it, carries no session value, and is how a client component knows the device is in
// classroom mode — which Clerk being configured or not does not answer.
export const CLASSROOM_MODE_COOKIE_NAME = "synthetic_responder_classroom_mode";
export const CLASSROOM_AUTH_MODE = "classroom-no-login";

const CLASSROOM_SESSION_ID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

// Keep the variable path segment free of encoded delimiters. Next decodes
// catch-all route params before the proxy rebuilds the backend URL, so a broad
// `[^/]+` here would allow `%2F`, `%3F`, or dot-segment path confusion.
const CLASSROOM_INTERVIEW_API_RULES = [
  { method: "GET", pattern: /^\/api\/backend\/api\/v1\/personas\/?$/ },
  { method: "GET", pattern: /^\/api\/backend\/api\/v1\/interview\/models\/?$/ },
  { method: "POST", pattern: /^\/api\/backend\/api\/v1\/studies\/[A-Za-z0-9_-]+\/interview\/demo\/(?:focus-group|batch|you)\/?$/ },
  { method: "POST", pattern: /^\/api\/backend\/api\/v1\/studies\/?$/ },
  {
    method: "GET",
    pattern: /^\/api\/backend\/api\/v1\/studies\/[A-Za-z0-9_-]+\/?$/,
  },
  {
    method: "POST",
    pattern:
      /^\/api\/backend\/api\/v1\/studies\/[A-Za-z0-9_-]+\/interview\/(?:chat|compare|export|batches)\/?$/,
  },
  { method: "GET", pattern: /^\/api\/backend\/api\/v1\/studies\/[A-Za-z0-9_-]+\/interview\/batches(?:\/[A-Za-z0-9_-]+(?:\/themes)?)?\/?$/ },
  { method: "POST", pattern: /^\/api\/backend\/api\/v1\/studies\/[A-Za-z0-9_-]+\/interview\/(?:batches\/[A-Za-z0-9_-]+\/(?:advance|themes)|answers\/[A-Za-z0-9_-]+\/regenerate)\/?$/ },
  // AI interviews you: one POST, its own lane, so it never opens the AI-led persona endpoint.
  { method: "POST", pattern: /^\/api\/backend\/api\/v1\/studies\/[A-Za-z0-9_-]+\/interview\/human\/next-question\/?$/ },
  // Focus group: its own lane here too, so widening it never widens the interview lane.
  { method: "POST", pattern: /^\/api\/backend\/api\/v1\/studies\/[A-Za-z0-9_-]+\/interview\/focus-group\/rooms\/?$/ },
  { method: "GET", pattern: /^\/api\/backend\/api\/v1\/studies\/[A-Za-z0-9_-]+\/interview\/focus-group\/rooms(?:\/[A-Za-z0-9_-]+(?:\/memo)?)?\/?$/ },
  { method: "POST", pattern: /^\/api\/backend\/api\/v1\/studies\/[A-Za-z0-9_-]+\/interview\/focus-group\/rooms\/[A-Za-z0-9_-]+\/(?:ask|cancel|memo|manual-memo|extend|export)\/?$/ },
  { method: "DELETE", pattern: /^\/api\/backend\/api\/v1\/studies\/[A-Za-z0-9_-]+\/interview\/focus-group\/rooms\/[A-Za-z0-9_-]+\/?$/ },
  // Student-created practice personas: list, create, edit. No delete, no other suffix.
  { method: "GET", pattern: /^\/api\/backend\/api\/v1\/studies\/[A-Za-z0-9_-]+\/interview\/focus-group\/personas\/?$/ },
  { method: "POST", pattern: /^\/api\/backend\/api\/v1\/studies\/[A-Za-z0-9_-]+\/interview\/focus-group\/personas(?:\/[A-Za-z0-9_-]+)?\/?$/ },
] as const;

export function isClassroomNoLoginEnabled(value = process.env.CLASSROOM_NO_LOGIN) {
  return value?.trim().toLowerCase() === "true";
}

export function isClassroomInterviewPage(pathname: string) {
  return pathname === "/interview" || pathname.startsWith("/interview/");
}

export function isClassroomFocusGroupPage(pathname: string) {
  return pathname === "/focus-group" || pathname.startsWith("/focus-group/");
}

/** The pages a no-login classroom student is allowed to reach. */
export function isClassroomStudentPage(pathname: string) {
  return isClassroomInterviewPage(pathname) || isClassroomFocusGroupPage(pathname);
}

export function isClassroomInterviewApiRequest(pathname: string, method: string) {
  const normalizedMethod = method.toUpperCase();
  return CLASSROOM_INTERVIEW_API_RULES.some(
    (rule) => rule.method === normalizedMethod && rule.pattern.test(pathname)
  );
}

export function isValidClassroomSessionId(value?: string | null) {
  return CLASSROOM_SESSION_ID_PATTERN.test(value?.trim() || "");
}

export function getClassroomUserId(value?: string | null) {
  const sessionId = value?.trim() || "";
  return isValidClassroomSessionId(sessionId) ? `classroom:${sessionId}` : null;
}
