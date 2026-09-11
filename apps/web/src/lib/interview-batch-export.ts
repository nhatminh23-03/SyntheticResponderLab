import type { Batch } from "./standalone-interview";

export function batchExport(batch: Batch, format: "csv" | "md") {
  const rows = batch.transcripts.flatMap(transcript => transcript.messages.map((message, index) => [
    transcript.persona_id, batch.interviewer_model, batch.interviewee_model,
    String(Math.floor(index / 2) + 1), message.role === "user" ? "Question" : "Answer", message.content,
  ]));
  const quote = (value: string) => `"${value.replace(/"/g, '""')}"`;
  const text = format === "csv"
    ? [["Persona", "Interviewer model", "Interviewee model", "Turn", "Role", "Text"], ...rows].map(row => row.map(quote).join(",")).join("\r\n")
    : `# Batch ${batch.job_id}\n\nStatus: ${batch.status}\nMeasured cost: $${batch.session_usage.cost_usd}\n\n` + rows.map(([persona, interviewer, interviewee, turn, role, content]) =>
      `## ${persona} — Turn ${turn}: ${role}\n\nInterviewer: ${interviewer} · Interviewee: ${interviewee}\n\n${content}\n`).join("\n");
  return { filename: `${batch.job_id}.${format}`, blob: new Blob([text], { type: format === "csv" ? "text/csv;charset=utf-8" : "text/markdown;charset=utf-8" }) };
}
