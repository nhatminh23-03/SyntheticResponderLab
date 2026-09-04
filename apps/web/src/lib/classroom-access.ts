export const CLASSROOM_SESSION_COOKIE_NAME = "synthetic_responder_classroom_session";
export const CLASSROOM_AUTH_MODE = "classroom-no-login";

const CLASSROOM_SESSION_ID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

// Keep the variable path segment free of encoded delimiters. Next decodes
// catch-all route params before the proxy rebuilds the backend URL, so a broad
// `[^/]+` here would allow `%2F`, `%3F`, or dot-segment path confusion.
const CLASSROOM_INTERVIEW_API_RULES = [
  { method: "GET", pattern: /^\/api\/backend\/api\/v1\/personas\/?$/ },
  { method: "GET", pattern: /^\/api\/backend\/api\/v1\/interview\/models\/?$/ },
  { method: "POST", pattern: /^\/api\/backend\/api\/v1\/studies\/?$/ },
  {
    method: "GET",
    pattern: /^\/api\/backend\/api\/v1\/studies\/[A-Za-z0-9_-]+\/?$/,
  },
  {
    method: "POST",
    pattern:
      /^\/api\/backend\/api\/v1\/studies\/[A-Za-z0-9_-]+\/interview\/(?:chat|compare|export)\/?$/,
  },
] as const;

export function isClassroomNoLoginEnabled(value = process.env.CLASSROOM_NO_LOGIN) {
  return value?.trim().toLowerCase() === "true";
}

export function isClassroomInterviewPage(pathname: string) {
  return pathname === "/interview" || pathname.startsWith("/interview/");
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
