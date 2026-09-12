import test from "node:test";
import assert from "node:assert/strict";

import {
  getClassroomUserId,
  isClassroomInterviewApiRequest,
  isClassroomInterviewPage,
  isClassroomNoLoginEnabled,
  isValidClassroomSessionId,
} from "../src/lib/classroom-access";

const SESSION_ID = "123e4567-e89b-42d3-a456-426614174000";

test("classroom no-login mode is off unless the flag is explicitly true", () => {
  assert.equal(isClassroomNoLoginEnabled(undefined), false);
  assert.equal(isClassroomNoLoginEnabled("false"), false);
  assert.equal(isClassroomNoLoginEnabled("1"), false);
  assert.equal(isClassroomNoLoginEnabled(" TRUE "), true);
});

test("classroom no-login mode opens only the interview page", () => {
  assert.equal(isClassroomInterviewPage("/interview"), true);
  assert.equal(isClassroomInterviewPage("/interview/"), true);
  assert.equal(isClassroomInterviewPage("/"), false);
  assert.equal(isClassroomInterviewPage("/interviews"), false);
});

test("classroom API allowlist contains only the operations used by the interview page", () => {
  const allowed = [
    ["GET", "/api/backend/api/v1/personas"],
    ["GET", "/api/backend/api/v1/interview/models"],
    ["POST", "/api/backend/api/v1/studies"],
    ["GET", "/api/backend/api/v1/studies/std_123"],
    ["POST", "/api/backend/api/v1/studies/std_123/interview/chat"],
    ["POST", "/api/backend/api/v1/studies/std_123/interview/compare"],
    ["POST", "/api/backend/api/v1/studies/std_123/interview/export"],
    ["POST", "/api/backend/api/v1/studies/std_123/interview/batches"],
    ["GET", "/api/backend/api/v1/studies/std_123/interview/batches/batch_123"],
    ["POST", "/api/backend/api/v1/studies/std_123/interview/batches/batch_123/advance"],
    ["POST", "/api/backend/api/v1/studies/std_123/interview/answers/ans_123/regenerate"],
  ] as const;

  for (const [method, pathname] of allowed) {
    assert.equal(isClassroomInterviewApiRequest(pathname, method), true);
  }

  const protectedRequests = [
    ["GET", "/api/backend/api/v1/studies"],
    ["PATCH", "/api/backend/api/v1/studies/std_123/study-mode"],
    ["POST", "/api/backend/api/v1/studies/std_123/simulation-runs"],
    ["GET", "/api/backend/api/v1/studies/std_123/interview/insights"],
    ["POST", "/api/backend/api/v1/personas"],
    [
      "POST",
      "/api/backend/api/v1/studies/..%2Fstudies%2Fstd_victim%2Fsimulation-runs%3F/interview/chat",
    ],
  ] as const;

  for (const [method, pathname] of protectedRequests) {
    assert.equal(isClassroomInterviewApiRequest(pathname, method), false);
  }
});

test("classroom sessions map valid random ids to isolated backend owners", () => {
  assert.equal(isValidClassroomSessionId(SESSION_ID), true);
  assert.equal(getClassroomUserId(SESSION_ID), `classroom:${SESSION_ID}`);
  assert.equal(isValidClassroomSessionId("student-selected-id"), false);
  assert.equal(getClassroomUserId("student-selected-id"), null);
  assert.equal(getClassroomUserId(null), null);
});
