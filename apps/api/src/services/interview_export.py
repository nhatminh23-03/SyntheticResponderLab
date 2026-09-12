from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from typing import Any, Dict, Literal


InterviewTranscriptExportFormat = Literal["csv", "markdown"]


@dataclass(frozen=True)
class InterviewTranscriptExport:
    content: str
    filename: str
    media_type: str


def build_interview_transcript_export(
    payload: Dict[str, Any],
    export_format: InterviewTranscriptExportFormat,
) -> InterviewTranscriptExport:
    """Serialize the student-visible interview transcript as a downloadable file."""
    persona_id = str(payload["persona_id"])
    interviewee_model = str(payload["interviewee_model"])
    turns = list(payload["turns"])
    filename_stem = _safe_filename_stem(persona_id)

    if export_format == "csv":
        output = io.StringIO(newline="")
        writer = csv.writer(output, lineterminator="\r\n")
        writer.writerow(
            ["turn", "role", "speaker", "text", "persona_id", "interviewee_model"]
        )
        for index, turn in enumerate(turns, start=1):
            role = str(turn["role"])
            speaker = "Student" if role == "student" else persona_id
            writer.writerow(
                [
                    index,
                    role,
                    _as_csv_text(speaker),
                    _as_csv_text(str(turn["text"])),
                    _as_csv_text(persona_id),
                    _as_csv_text(interviewee_model),
                ]
            )
        return InterviewTranscriptExport(
            content="\ufeff" + output.getvalue(),
            filename=f"interview-{filename_stem}.csv",
            media_type="text/csv",
        )

    lines = [
        "# Interview transcript",
        "",
        f"- Persona: `{persona_id}`",
        f"- Interviewee model: `{interviewee_model}`",
        "",
        "## Transcript",
        "",
    ]
    for index, turn in enumerate(turns, start=1):
        role = str(turn["role"])
        speaker = "Student" if role == "student" else persona_id
        lines.extend(
            [
                f"### {index}. {speaker}",
                "",
                _as_markdown_quote(str(turn["text"])),
                "",
            ]
        )
    return InterviewTranscriptExport(
        content="\n".join(lines),
        filename=f"interview-{filename_stem}.md",
        media_type="text/markdown",
    )


def _safe_filename_stem(persona_id: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", persona_id).strip(".-")[:64]
    return stem or "transcript"


def _as_csv_text(text: str) -> str:
    # CSV quoting protects delimiters, not spreadsheet users. Excel and similar
    # applications can evaluate formula prefixes, including after whitespace.
    if text.startswith(("\t", "\r", "\n")) or text.lstrip(" \t\r\n").startswith(
        ("=", "+", "-", "@")
    ):
        return "'" + text
    return text


def _as_markdown_quote(text: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in text.split("\n"))
