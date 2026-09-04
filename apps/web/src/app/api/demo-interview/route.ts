import { readFile } from "node:fs/promises";
import path from "node:path";

import { NextRequest, NextResponse } from "next/server";

import type { InterviewModelCatalogEntry, InterviewPersona } from "@/lib/api";
import { isInterviewModelSelectable } from "@/lib/interview-models";
import { getDeploymentSharedSecret, getServerApiBaseUrl } from "@/lib/server-env";

export const runtime = "nodejs";

// Demo chat fallback for the Sept 3 walkthrough. It deliberately bypasses the study workflow,
// which gates the real interview section behind audience/product/market/survey/experiment saves.
// Persona discovery and lookup still go through FastAPI and its seeded database records.

const REPO_ROOT = path.resolve(process.cwd(), "../..");

// Written from the public product concept only. Nothing from the 600 real survey answers may
// appear here — that is the contamination rule the September comparison depends on.
const PRODUCT_CONTEXT = `PRODUCT BEING DISCUSSED:
Name: Tahoe Mini by Neo Smart Living
Price: about $23,000
Description: A compact 117-square-foot factory-built studio that is delivered and installed in a backyard. It is not an ADU and has no kitchen or bathroom.
Intended for: homeowners with usable outdoor space`;

async function loadPersonas(): Promise<InterviewPersona[]> {
  const headers = new Headers({ Accept: "application/json" });
  const secret = getDeploymentSharedSecret();
  if (secret) headers.set("X-Deployment-Secret", secret);

  const response = await fetch(`${getServerApiBaseUrl()}/api/v1/personas`, {
    method: "GET",
    headers,
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Could not load personas from the backend (${response.status}).`);
  }

  const payload = (await response.json()) as { data?: { personas?: InterviewPersona[] } };
  if (!Array.isArray(payload.data?.personas)) {
    throw new Error("The backend returned an invalid persona list.");
  }
  return payload.data.personas;
}

type InterviewModelCatalog = {
  defaultModelId: string;
  models: InterviewModelCatalogEntry[];
};

async function loadInterviewModels(): Promise<InterviewModelCatalog> {
  const headers = new Headers({ Accept: "application/json" });
  const secret = getDeploymentSharedSecret();
  if (secret) headers.set("X-Deployment-Secret", secret);

  const response = await fetch(`${getServerApiBaseUrl()}/api/v1/interview/models`, {
    method: "GET",
    headers,
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Could not load interview models from the backend (${response.status}).`);
  }

  const payload = (await response.json()) as {
    data?: { default_model_id?: string; models?: InterviewModelCatalogEntry[] };
  };
  if (!payload.data?.default_model_id || !Array.isArray(payload.data.models)) {
    throw new Error("The backend returned an invalid interview model catalog.");
  }
  return {
    defaultModelId: payload.data.default_model_id,
    models: payload.data.models,
  };
}

function buildSystemPrompt(persona: InterviewPersona): string {
  const description = [
    `You are a ${persona.age_bucket} year-old ${persona.ownership} living in a ${persona.home_type}.`,
    `Your household income is in the ${persona.income_bucket} range.`,
    persona.census_profile,
    persona.lifestyle_tags.length ? `Your lifestyle includes: ${persona.lifestyle_tags.join(", ")}.` : "",
  ]
    .filter(Boolean)
    .join(" ");

  return `You are role-playing as a real person participating in a qualitative depth interview.

YOUR PERSONA:
${description}

${PRODUCT_CONTEXT}

INSTRUCTIONS:
- Stay fully in character. Answer as this person would, in first person.
- Be specific and personal. Share genuine opinions, hesitations, and enthusiasm where warranted.
- No marketing-speak. Reflect the real trade-offs someone in your situation would weigh.
- Keep it conversational, three to six sentences, plain prose.`;
}

async function openRouterKey(): Promise<string> {
  const fromEnv = (process.env.OPENROUTER_API_KEY ?? "").trim();
  if (fromEnv) return fromEnv;
  // The key lives in the API app's .env; the demo reads it rather than duplicating it.
  try {
    const text = await readFile(path.join(REPO_ROOT, "apps/api/.env"), "utf8");
    const line = text.split("\n").find((entry) => entry.startsWith("OPENROUTER_API_KEY="));
    return (line?.split("=")[1] ?? "").trim().replace(/^["']|["']$/g, "");
  } catch {
    return "";
  }
}

export async function POST(request: NextRequest) {
  const {
    personaId,
    question,
    model,
    interviewerModel,
    intervieweeModel,
    allowExpensiveModels,
    history,
  } = (await request.json()) as {
    personaId?: string;
    question?: string;
    model?: string;
    interviewerModel?: string;
    intervieweeModel?: string;
    allowExpensiveModels?: boolean;
    history?: { role: string; text: string }[];
  };

  if (!question?.trim()) {
    return NextResponse.json({ error: "A question is required." }, { status: 400 });
  }

  let personas: InterviewPersona[];
  let modelCatalog: InterviewModelCatalog;
  try {
    [personas, modelCatalog] = await Promise.all([loadPersonas(), loadInterviewModels()]);
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 500 });
  }

  const persona = personaId ? personas.find((p) => p.persona_id === personaId) : personas[0];
  if (!persona) {
    return NextResponse.json({ error: `Persona ${personaId} not found.` }, { status: 404 });
  }

  const selectedInterviewerId = interviewerModel || modelCatalog.defaultModelId;
  const selectedIntervieweeId = intervieweeModel || model || modelCatalog.defaultModelId;
  const selectedInterviewer = modelCatalog.models.find(
    (entry) => entry.id === selectedInterviewerId
  );
  const selectedInterviewee = modelCatalog.models.find(
    (entry) => entry.id === selectedIntervieweeId
  );
  if (!selectedInterviewer || !selectedInterviewee) {
    return NextResponse.json({ error: "Select models from the curated interview catalog." }, { status: 400 });
  }
  if (
    !isInterviewModelSelectable(selectedInterviewer, allowExpensiveModels === true) ||
    !isInterviewModelSelectable(selectedInterviewee, allowExpensiveModels === true)
  ) {
    return NextResponse.json(
      { error: "Expensive interview models require opt-in for this run." },
      { status: 400 }
    );
  }

  const systemPrompt = buildSystemPrompt(persona);
  const key = await openRouterKey();
  if (!key) {
    return NextResponse.json(
      { error: "No OPENROUTER_API_KEY found in apps/api/.env.", systemPrompt },
      { status: 503 }
    );
  }

  const response = await fetch("https://openrouter.ai/api/v1/chat/completions", {
    method: "POST",
    headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      model: selectedInterviewee.id,
      messages: [
        { role: "system", content: systemPrompt },
        // Without the prior turns the model re-answers every follow-up as if it were the first
        // question, so two similar questions come back with the same text.
        ...(history ?? []).map((turn) => ({
          role: turn.role === "persona" ? "assistant" : "user",
          content: turn.text,
        })),
        { role: "user", content: question },
      ],
      temperature: 0.8,
      max_tokens: 700,
    }),
  });

  if (!response.ok) {
    return NextResponse.json(
      { error: `Model call failed (${response.status}): ${await response.text()}`, systemPrompt },
      { status: 502 }
    );
  }

  const payload = await response.json();
  const answer = payload?.choices?.[0]?.message?.content?.trim();
  if (!answer) {
    return NextResponse.json({ error: "Model returned an empty answer.", systemPrompt }, { status: 502 });
  }

  return NextResponse.json({
    answer,
    systemPrompt,
    persona,
    interviewerModel: selectedInterviewer.id,
    intervieweeModel: selectedInterviewee.id,
  });
}
