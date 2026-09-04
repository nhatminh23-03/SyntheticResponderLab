import { readFile } from "node:fs/promises";
import path from "node:path";

import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

// Demo route for the Sept 3 walkthrough: reads the Census persona CSV directly and asks one
// question. It deliberately bypasses the study workflow, which gates the real interview
// section behind audience/product/market/survey/experiment saves. The student-facing screen
// built in the Sept 4-16 block goes through the FastAPI interview endpoints instead.

const REPO_ROOT = path.resolve(process.cwd(), "../..");
const DEFAULT_CSV =
  process.env.DEMO_PERSONA_CSV ??
  path.join(process.env.HOME ?? "", "dev/aytm-real-data/personas/personas-B.csv");

// Written from the public product concept only. Nothing from the 600 real survey answers may
// appear here — that is the contamination rule the September comparison depends on.
const PRODUCT_CONTEXT = `PRODUCT BEING DISCUSSED:
Name: Tahoe Mini by Neo Smart Living
Price: about $23,000
Description: A compact 117-square-foot factory-built studio that is delivered and installed in a backyard. It is not an ADU and has no kitchen or bathroom.
Intended for: homeowners with usable outdoor space`;

export type DemoPersona = {
  persona_id: string;
  age_bucket: string;
  income_bucket: string;
  ownership: string;
  home_type: string;
  work_mode: string;
  fit_tier: string;
  lifestyle_tags: string[];
  census_profile: string;
  headline: string;
};

/** Minimal RFC-4180 parse: the export quotes any cell containing a comma. */
function parseCsv(text: string): Record<string, string>[] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;

  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    if (quoted) {
      if (char === '"') {
        if (text[i + 1] === '"') {
          cell += '"';
          i += 1;
        } else {
          quoted = false;
        }
      } else {
        cell += char;
      }
      continue;
    }
    if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      row.push(cell);
      cell = "";
    } else if (char === "\n") {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
    } else if (char !== "\r") {
      cell += char;
    }
  }
  if (cell !== "" || row.length > 0) {
    row.push(cell);
    rows.push(row);
  }

  const [header, ...body] = rows;
  if (!header) return [];
  return body
    .filter((entry) => entry.some((value) => value.trim() !== ""))
    .map((entry) => Object.fromEntries(header.map((key, i) => [key.trim(), (entry[i] ?? "").trim()])));
}

/** The bucket columns alone lose occupation, county, household and commute — keep them. */
function censusProfile(row: Record<string, string>): string {
  const parts: string[] = [];
  const push = (value: string | undefined, render: (v: string) => string) => {
    if (value && value.trim()) parts.push(render(value.trim()));
  };

  if (row.exact_age) {
    parts.push(`You are ${row.exact_age}${row.sex ? `, ${row.sex.toLowerCase()}` : ""}`);
  }
  push(row.county, (v) => `You live in ${v} County, California`);
  push(row.marital_status, (v) => `Your marital status is ${v}`);
  push(row.education, (v) => `Your education level is ${v}`);
  push(row.occupation, (v) => `You work as a ${v}`);
  push(row.hours_worked_per_week, (v) => `You work about ${v} hours a week`);
  push(row.commute_mode, (v) =>
    `You get to work by ${v.toLowerCase()}${row.commute_minutes ? `, about ${row.commute_minutes} minutes each way` : ""}`
  );
  if (row.household_size) {
    const kids = row.children_in_household;
    const suffix = kids && kids !== "0" ? `, including ${kids} child${kids === "1" ? "" : "ren"}` : "";
    parts.push(`There are ${row.household_size} people in your household${suffix}`);
  }
  if (/^\d+$/.test(row.exact_household_income ?? "")) {
    parts.push(
      `Your household income is about $${Number(row.exact_household_income).toLocaleString("en-US")} a year`
    );
  }
  // "0 bedrooms" is a studio in ACS terms; saying it out loud reads like missing data.
  if (row.bedrooms && row.bedrooms !== "0") {
    parts.push(`Your home has ${row.bedrooms} bedrooms${row.year_built ? ` and was built ${row.year_built}` : ""}`);
  } else if (row.year_built) {
    parts.push(`Your home was built ${row.year_built}`);
  }
  push(row.housing_cost_pct_of_income, (v) => `Housing costs take about ${v}% of your income`);

  return parts.length ? `${parts.join(". ")}.` : "";
}

function toPersona(row: Record<string, string>): DemoPersona {
  return {
    persona_id: row.persona_id ?? "",
    age_bucket: row.age_bucket ?? "",
    income_bucket: row.income_bucket ?? "",
    ownership: row.ownership ?? "",
    home_type: row.home_type ?? "",
    work_mode: row.work_mode ?? "",
    // Blank on purpose: fit_tier is scored after the interview, never fed into it.
    fit_tier: row.fit_tier ?? "",
    lifestyle_tags: (row.lifestyle_tags ?? "").split(/[;|,]/).map((t) => t.trim()).filter(Boolean),
    census_profile: censusProfile(row),
    headline: row.headline ?? "",
  };
}

async function loadPersonas(): Promise<DemoPersona[]> {
  const text = await readFile(DEFAULT_CSV, "utf8");
  return parseCsv(text).map(toPersona);
}

function buildSystemPrompt(persona: DemoPersona): string {
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

export async function GET() {
  try {
    const personas = await loadPersonas();
    return NextResponse.json({ personas, source: path.basename(DEFAULT_CSV) });
  } catch (error) {
    return NextResponse.json(
      { error: `Could not read persona file at ${DEFAULT_CSV}: ${(error as Error).message}` },
      { status: 500 }
    );
  }
}

export async function POST(request: NextRequest) {
  const { personaId, question, model, history } = (await request.json()) as {
    personaId?: string;
    question?: string;
    model?: string;
    history?: { role: string; text: string }[];
  };

  if (!question?.trim()) {
    return NextResponse.json({ error: "A question is required." }, { status: 400 });
  }

  let personas: DemoPersona[];
  try {
    personas = await loadPersonas();
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 500 });
  }

  const persona = personaId ? personas.find((p) => p.persona_id === personaId) : personas[0];
  if (!persona) {
    return NextResponse.json({ error: `Persona ${personaId} not found.` }, { status: 404 });
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
      model: model || "google/gemini-2.5-flash",
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

  return NextResponse.json({ answer, systemPrompt, persona });
}
