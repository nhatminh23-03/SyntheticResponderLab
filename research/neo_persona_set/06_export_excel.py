"""Stage 6 — export the persona set and the model bake-off to a formatted Excel workbook.

Usage:
    python 06_export_excel.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import documentation  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "out"

HEADER_FILL = PatternFill("solid", fgColor="1F3864")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
TITLE_FONT = Font(bold=True, size=14, color="1F3864")
LABEL_FONT = Font(bold=True, size=10)
WRAP = Alignment(wrap_text=True, vertical="top")
TOP = Alignment(vertical="top")

RESPONSE_FILL = {
    "accept": PatternFill("solid", fgColor="C6EFCE"),
    "unsure": PatternFill("solid", fgColor="FFEB9C"),
    "reject": PatternFill("solid", fgColor="FFC7CE"),
}
THIN = Border(*[Side(style="thin", color="D0D0D0")] * 4)
NOTE_FILL = PatternFill("solid", fgColor="FFF2CC")
FORMULA_FONT = Font(name="Consolas", size=10)


def annotate_headers(worksheet, notes: dict[str, str], row: int = 1) -> None:
    """Attach an explanatory comment to each header cell, and mark it so readers know to hover."""
    for cell in worksheet[row]:
        note = notes.get(str(cell.value))
        if not note:
            continue
        comment = Comment(note, "Persona pipeline")
        # openpyxl sizes comment boxes in pixels; the default is too small for these notes.
        comment.width = 460
        comment.height = 15 * (note.count("\n") + note.count(". ") + 8)
        cell.comment = comment


def fit_row_height(worksheet, row: int, text: str, width_chars: int, point_size: float = 13.0) -> None:
    """Set an explicit row height for wrapped text.

    Excel auto-fits wrapped rows on render, but only when the height was never set, and other
    spreadsheet apps are less consistent. Computing it here keeps long formula blocks readable
    everywhere rather than showing a single clipped line.
    """
    lines = 0
    for logical_line in str(text).split("\n"):
        lines += max(1, -(-len(logical_line) // width_chars))
    worksheet.row_dimensions[row].height = min(lines * point_size + 4, 409)


def style_header(worksheet, row: int = 1) -> None:
    for cell in worksheet[row]:
        if cell.value is not None:
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = Alignment(wrap_text=True, vertical="center")
    # Set freeze_panes from a coordinate string. Using worksheet.cell() here would materialise that
    # cell, advancing max_row and leaving a blank row between the header and the first appended row.
    worksheet.freeze_panes = f"A{row + 1}"


def autosize(worksheet, widths: dict[str, int] | None = None, default: int = 18, cap: int = 60) -> None:
    widths = widths or {}
    for column_cells in worksheet.columns:
        letter = get_column_letter(column_cells[0].column)
        if letter in widths:
            worksheet.column_dimensions[letter].width = widths[letter]
            continue
        longest = max((len(str(c.value)) for c in column_cells if c.value is not None), default=0)
        worksheet.column_dimensions[letter].width = min(max(longest + 2, default), cap)


def sheet_personas(workbook: Workbook, personas: list[dict]) -> None:
    worksheet = workbook.create_sheet("Personas")
    columns = [
        ("persona_id", "Persona ID"), ("name", "Name"), ("headline", "Headline"),
        ("occupation", "Occupation"), ("segment_label", "Segment"),
        ("likely_response", "Likely Response"), ("response_score", "Score"),
        ("householder_age", "Age"), ("household_size", "Household"),
        ("annual_income_usd", "Household Income"), ("income_bucket", "Income Bracket"),
        ("price_pct_of_income", "$23k as % of Income"), ("owner_cost_burden", "Housing Cost Burden %"),
        ("work_mode", "Work Mode"), ("home_type", "Home Type"), ("puma", "PUMA"),
        ("quote", "Quote"),
    ]
    worksheet.append([label for _, label in columns])

    for persona in personas:
        narrative = persona.get("narrative", {})
        row = []
        for key, _ in columns:
            value = narrative.get(key, persona.get(key))
            row.append(value)
        worksheet.append(row)

    style_header(worksheet)
    response_column = [k for k, _ in columns].index("likely_response") + 1
    for row_index in range(2, len(personas) + 2):
        cell = worksheet.cell(row=row_index, column=response_column)
        fill = RESPONSE_FILL.get(str(cell.value))
        if fill:
            cell.fill = fill
        worksheet.cell(row=row_index, column=10).number_format = '"$"#,##0'
        worksheet.cell(row=row_index, column=12).number_format = "0.0"
        worksheet.cell(row=row_index, column=13).number_format = "0"
        for column_index in range(1, len(columns) + 1):
            worksheet.cell(row=row_index, column=column_index).alignment = TOP
        worksheet.cell(row=row_index, column=17).alignment = WRAP

    annotate_headers(worksheet, documentation.PERSONAS_NOTES)
    autosize(worksheet, widths={"C": 34, "D": 26, "E": 26, "Q": 60})


def sheet_detail(workbook: Workbook, personas: list[dict]) -> None:
    worksheet = workbook.create_sheet("Persona_Detail")

    # This sheet is a stack of cards rather than a table, so the "columns" are Field and Value.
    # Each recurring field label carries its own note, since that is where the meaning lives.
    worksheet.cell(row=1, column=1, value="Field")
    worksheet.cell(row=1, column=2, value="Value")
    style_header(worksheet, 1)
    annotate_headers(worksheet, documentation.FIELD_VALUE_HEADERS, 1)
    row = 3

    for persona in personas:
        narrative = persona.get("narrative", {})
        header = f"{persona['persona_id']} — {narrative.get('name', 'Unnamed')} ({persona['likely_response'].upper()})"
        worksheet.cell(row=row, column=1, value=header).font = TITLE_FONT
        fill = RESPONSE_FILL.get(persona["likely_response"])
        if fill:
            worksheet.cell(row=row, column=1).fill = fill
        row += 1

        def field(label: str, value) -> None:
            nonlocal row
            if isinstance(value, list):
                value = "\n".join(f"• {item}" for item in value)
            label_cell = worksheet.cell(row=row, column=1, value=label)
            label_cell.font = LABEL_FONT
            note = documentation.DETAIL_NOTES.get(label)
            if note:
                comment = Comment(note, "Persona pipeline")
                comment.width = 440
                comment.height = 15 * (note.count("\n") + note.count(". ") + 7)
                label_cell.comment = comment
            cell = worksheet.cell(row=row, column=2, value=value)
            cell.alignment = WRAP
            if value:
                fit_row_height(worksheet, row, value, width_chars=98)
            row += 1

        field("Headline", narrative.get("headline"))
        field("Occupation", narrative.get("occupation"))
        field("Segment", persona.get("segment_label"))
        field(
            "Census profile",
            f"Age {persona['householder_age']} · household of {persona['household_size']} · "
            f"${persona['annual_income_usd']:,.0f}/yr · owner-occupied detached house · "
            f"{persona['work_mode'].replace('_', ' ')} · PUMA {persona['puma']}",
        )
        field("$23,000 is", f"{persona['price_pct_of_income']:.1f}% of annual household income")
        field("Backstory", narrative.get("backstory"))
        field("Typical weekday", narrative.get("daily_routine"))
        field("Motivations", narrative.get("motivations"))
        field("Objections", narrative.get("objections"))
        field("Reaction to Tahoe Mini", narrative.get("reaction"))
        field("Quote", narrative.get("quote"))
        field("Why this response", f"score {persona['response_score']:+.1f}")
        if persona.get("reasons_for"):
            field("  Factors in favour", persona["reasons_for"])
        if persona.get("reasons_against"):
            field("  Factors against", persona["reasons_against"])

        row += 1

    worksheet.column_dimensions["A"].width = 24
    worksheet.column_dimensions["B"].width = 100


def sheet_rejectors(workbook: Workbook, personas: list[dict]) -> None:
    worksheet = workbook.create_sheet("Rejectors")
    worksheet.cell(row=1, column=1, value="Personas who would decline the Tahoe Mini").font = TITLE_FONT
    worksheet.cell(
        row=2,
        column=1,
        value=(
            "The survey screener terminates anyone without outdoor space, so these are people who "
            "PASS screening and still say no. Their objections are therefore about cost and value, "
            "not about space. Every label below is reproducible from the Census fields alone."
        ),
    ).alignment = WRAP
    worksheet.merge_cells(start_row=2, start_column=1, end_row=3, end_column=7)

    headers = ["Persona ID", "Name", "Age", "Income", "$23k as % of Income",
               "Housing Cost Burden %", "Why they decline"]
    worksheet.append([])
    worksheet.append(headers)
    header_row = worksheet.max_row
    style_header(worksheet, header_row)

    rejectors = [p for p in personas if p["likely_response"] == "reject"]
    for persona in rejectors:
        narrative = persona.get("narrative", {})
        worksheet.append(
            [
                persona["persona_id"],
                narrative.get("name"),
                persona["householder_age"],
                persona["annual_income_usd"],
                persona["price_pct_of_income"],
                persona.get("owner_cost_burden"),
                "\n".join(f"• {r}" for r in persona.get("reasons_against", [])),
            ]
        )
        current = worksheet.max_row
        worksheet.cell(row=current, column=4).number_format = '"$"#,##0'
        worksheet.cell(row=current, column=5).number_format = "0.0"
        worksheet.cell(row=current, column=6).number_format = "0"
        worksheet.cell(row=current, column=7).alignment = WRAP
        worksheet.cell(row=current, column=1).fill = RESPONSE_FILL["reject"]
        reasons = worksheet.cell(row=current, column=7).value
        if reasons:
            fit_row_height(worksheet, current, reasons, width_chars=68)

    annotate_headers(worksheet, documentation.REJECTORS_NOTES, header_row)
    autosize(worksheet, widths={"B": 24, "G": 70})


def sheet_model_comparison(workbook: Workbook, comparison: dict) -> None:
    worksheet = workbook.create_sheet("Model_Comparison")
    worksheet.cell(row=1, column=1, value="Persona-generation model bake-off").font = TITLE_FONT
    worksheet.cell(
        row=2,
        column=1,
        value=(
            "Each model was fit on 75% of Southern California ACS households (weighted by WGTP) and "
            "scored on how well the population it generates reproduces the joint structure of the "
            "held-out 25%. Lower is better for every fidelity metric."
        ),
    ).alignment = WRAP
    worksheet.merge_cells(start_row=2, start_column=1, end_row=3, end_column=8)

    summary = pd.DataFrame(comparison["summary"])
    display = pd.DataFrame(
        {
            "Model": summary["model"],
            "Marginal TVD": summary["marginal_tvd_mean"],
            "Association Error": summary["association_error_mean"],
            "Purchase-Triple TVD": summary["purchase_triple_tvd_mean"],
            "Full Joint TVD": summary["full_joint_tvd_mean"],
            "C2ST Gap": summary["c2st_gap_mean"],
            "Held-out LogLik": summary["held_out_loglik_mean"],
            "Composite Rank": summary["composite_rank"],
            "Fit Seconds": summary["fit_seconds_mean"],
        }
    )

    worksheet.append([])
    worksheet.append(list(display.columns))
    header_row = worksheet.max_row
    style_header(worksheet, header_row)

    for _, row in display.iterrows():
        worksheet.append(list(row.values))
        current = worksheet.max_row
        for column_index in range(2, 8):
            worksheet.cell(row=current, column=column_index).number_format = "0.0000"
        worksheet.cell(row=current, column=8).number_format = "0.0"
        worksheet.cell(row=current, column=9).number_format = "0.0"
        model_name = worksheet.cell(row=current, column=1).value
        if model_name == comparison["selected_model"]:
            worksheet.cell(row=current, column=1).fill = RESPONSE_FILL["accept"]
            worksheet.cell(row=current, column=1).font = Font(bold=True)
        elif model_name == comparison["reference_ceiling"]:
            worksheet.cell(row=current, column=1).fill = PatternFill("solid", fgColor="DDEBF7")

    row = worksheet.max_row + 2
    notes = [
        ("SELECTED MODEL", comparison["selected_model"]),
        ("Reference ceiling", f"{comparison['reference_ceiling']} — copies real households, so it is the fidelity ceiling rather than a deployable candidate"),
        ("Baseline", f"{comparison['baseline']} — reproduces what the app does today (independent draws per trait)"),
        ("Improvement", f"{comparison['association_error_improvement_pct']:.1f}% lower association error than the baseline"),
        ("Seeds", comparison["seeds"]),
        ("Synthetic sample size", f"{comparison['sample_size']:,}"),
        ("", ""),
        ("Note", comparison["note"]),
    ]
    for label, value in notes:
        worksheet.cell(row=row, column=1, value=label).font = LABEL_FONT
        cell = worksheet.cell(row=row, column=2, value=value)
        cell.alignment = WRAP
        if value:
            fit_row_height(worksheet, row, str(value), width_chars=93)
        row += 1

    row += 1
    worksheet.cell(row=row, column=1, value="Metric definitions").font = TITLE_FONT
    row += 1
    for key, description in comparison["metrics"].items():
        worksheet.cell(row=row, column=1, value=key).font = LABEL_FONT
        worksheet.cell(row=row, column=2, value=description).alignment = WRAP
        fit_row_height(worksheet, row, description, width_chars=93)
        row += 1

    annotate_headers(worksheet, documentation.MODEL_NOTES, header_row)
    autosize(worksheet, widths={"A": 26, "B": 95})


def sheet_provenance(workbook: Workbook, provenance: dict, payload: dict, comparison: dict) -> None:
    worksheet = workbook.create_sheet("Provenance")

    worksheet.cell(row=1, column=1, value="Item")
    worksheet.cell(row=1, column=2, value="Detail")
    style_header(worksheet, 1)
    annotate_headers(worksheet, documentation.FIELD_VALUE_HEADERS, 1)
    row = 3

    def section(title: str) -> None:
        nonlocal row
        worksheet.cell(row=row, column=1, value=title).font = TITLE_FONT
        row += 1

    def line(label: str, value) -> None:
        nonlocal row
        if isinstance(value, list):
            value = "\n".join(f"• {item}" for item in value)
        worksheet.cell(row=row, column=1, value=label).font = LABEL_FONT
        worksheet.cell(row=row, column=2, value=str(value)).alignment = WRAP
        fit_row_height(worksheet, row, str(value), width_chars=98)
        row += 1

    section("Data source")
    line("Source", provenance["source"])
    line("Geography", f"{provenance['geography']['puma_count']} PUMAs across {', '.join(provenance['geography']['counties'])}")
    line("PUMA definition", provenance["geography"]["puma_source"])
    line("Unit of analysis", provenance["unit_of_analysis"])
    line("Weighting", provenance["weight"])
    line("Income adjustment", provenance["income"])
    row += 1

    section("Filter chain")
    for step in provenance["filters"]:
        detail = f"{step['rows']:,} rows"
        if "weighted_households" in step:
            detail += f"  ({step['weighted_households']:,} weighted)"
        line(step["step"], detail)
    row += 1

    section("Assumptions and caveats")
    for assumption in provenance["assumptions"]:
        line("•", assumption)
    line(
        "•",
        "Model fidelity here is DEMOGRAPHIC realism, measured against held-out Census data. It is "
        "not answer realism: no real survey responses were used, so nothing here claims these "
        "personas answer like real respondents.",
    )
    row += 1

    section("Persona generation")
    line("Model used", payload["generated_by_model"])
    line("Screen applied", payload["screen"])
    line("Seed", payload["seed"])
    line("Selected mix", json.dumps(payload["selected_mix"]))
    line(
        "Natural response rate",
        ", ".join(f"{k}={v:.1%}" for k, v in payload["natural_response_rate_among_eligible"].items()),
    )
    line("Narrative model", payload.get("narrative_model", "n/a"))
    row += 1

    section("Field provenance — where each value comes from")
    for source, fields in payload["field_provenance"].items():
        line(source, ", ".join(fields))
    row += 1

    section("Response scoring rules")
    line("Accept at or above", payload["thresholds"]["accept_at_or_above"])
    line("Reject at or below", payload["thresholds"]["reject_at_or_below"])
    for rule in payload["scoring_rules"]:
        line(f"{rule['weight']:+.1f}", rule["description"])

    autosize(worksheet, widths={"A": 30, "B": 100})


def sheet_formulas(workbook: Workbook) -> None:
    """Every formula the pipeline uses, written out and explained."""
    worksheet = workbook.create_sheet("Formulas")
    row = 1

    worksheet.cell(row=row, column=1, value="Formulas used in this workbook").font = Font(
        bold=True, size=16, color="1F3864"
    )
    row += 1
    worksheet.cell(
        row=row,
        column=1,
        value=(
            "Every calculation behind the Personas, Rejectors, and Model_Comparison sheets, written "
            "out in full. Each block gives the formula, what each symbol means, how to read the "
            "result, a worked example using real numbers from this run, and where the code lives.\n\n"
            "Notation is plain text rather than mathematical typesetting so it stays readable in "
            "Excel. SUM means summation, PRODUCT means repeated multiplication, x means multiply, "
            "and ^ means raise to a power."
        ),
    ).alignment = WRAP
    worksheet.merge_cells(start_row=row, start_column=1, end_row=row + 2, end_column=2)
    row += 4

    labels = [
        ("purpose", "What it is for"),
        ("formula", "Formula"),
        ("symbols", "Symbols"),
        ("reading", "How to read it"),
        ("example", "Worked example"),
        ("code", "Code"),
    ]

    for index, block in enumerate(documentation.FORMULAS, start=1):
        title_cell = worksheet.cell(row=row, column=1, value=f"{index}.  {block['name']}")
        title_cell.font = Font(bold=True, size=12, color="FFFFFF")
        title_cell.fill = HEADER_FILL
        spacer = worksheet.cell(row=row, column=2, value="")
        spacer.fill = HEADER_FILL
        row += 1

        for key, label in labels:
            value = block.get(key)
            if not value:
                continue
            label_cell = worksheet.cell(row=row, column=1, value=label)
            label_cell.font = LABEL_FONT
            label_cell.alignment = TOP
            value_cell = worksheet.cell(row=row, column=2, value=value)
            value_cell.alignment = WRAP
            # Monospace for the parts where alignment carries meaning.
            if key in {"formula", "example"}:
                value_cell.font = FORMULA_FONT
                value_cell.fill = NOTE_FILL
                fit_row_height(worksheet, row, value, width_chars=112, point_size=12.5)
            else:
                fit_row_height(worksheet, row, value, width_chars=100)
            row += 1

        row += 1

    worksheet.column_dimensions["A"].width = 22
    worksheet.column_dimensions["B"].width = 104
    worksheet.freeze_panes = "A2"


def main() -> int:
    provenance = json.loads((OUT_DIR / "frame_provenance.json").read_text())
    comparison = json.loads((OUT_DIR / "model_comparison.json").read_text())
    payload = json.loads((OUT_DIR / "personas_full.json").read_text())
    personas = payload["personas"]

    workbook = Workbook()
    workbook.remove(workbook.active)

    sheet_personas(workbook, personas)
    sheet_detail(workbook, personas)
    sheet_rejectors(workbook, personas)
    sheet_model_comparison(workbook, comparison)
    sheet_formulas(workbook)
    sheet_provenance(workbook, provenance, payload, comparison)

    out_path = OUT_DIR / "neo_smart_personas.xlsx"
    workbook.save(out_path)

    counts = pd.Series([p["likely_response"] for p in personas]).value_counts()
    print(f"Wrote {out_path}")
    print(f"  sheets   : {', '.join(workbook.sheetnames)}")
    print(f"  personas : {len(personas)}")
    print(f"  mix      : {counts.to_dict()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
