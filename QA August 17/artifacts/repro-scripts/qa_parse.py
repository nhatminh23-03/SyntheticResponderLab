import sys, json
from pathlib import Path
from fastapi.testclient import TestClient
from src.config.settings import AppSettings
from src.api.app import create_app
import src.api.app as appmod
appmod.startup_failures = lambda *a, **k: []
S=AppSettings(); client=TestClient(create_app(S))
PI = Path("/Users/mnd/Desktop/AI Hackathon/SyntheticResponderLab/NeoSmart-Hackathon-App/Provided Info")
CASES=[
 ("MD  (Neo preset)",        PI/"Neo Smart Living — Survey_HighPriority.md", "text/markdown"),
 ("MD  (non-Neo coffee)",    Path("/tmp/coffee_survey.md"), "text/markdown"),
 ("DOCX(aytm Neo)",          PI/"aytm Survey #760085  (Neo Smart Living — Tahoe Mini Survey).docx",
                             "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
 ("PDF (Google Forms Neo)",  PI/"Neo Smart Living — Tahoe Mini Survey (High + Medium Priority) - Google Forms.pdf", "application/pdf"),
 ("PDF (prose, not a survey)",PI/"Neo Smart Living Background.pdf", "application/pdf"),
]
for label, path, ctype in CASES:
    sid = client.post("/api/v1/studies", json={}).json()["data"]["study"]["study_id"]
    if not path.exists():
        print(f"{label:28s} SKIP - file missing"); continue
    r = client.post(f"/api/v1/studies/{sid}/survey/upload",
                    files={"file": (path.name, path.read_bytes(), ctype)})
    print(f"\n{'-'*76}\n{label}  [{path.name[:48]}]  ({path.stat().st_size//1024} KB)")
    print(f"  HTTP {r.status_code}")
    if r.status_code != 200:
        print("  error:", json.dumps(r.json())[:260]); continue
    d=r.json()["data"]; sv=d.get("survey") or d.get("survey_schema") or d
    qs=sv.get("questions") or []
    print(f"  title        : {str(sv.get('survey_title'))[:60]}")
    print(f"  source_format: {sv.get('source_format')}")
    print(f"  question_count: {len(qs)}")
    types={}
    for q in qs: types[q.get('question_type')]=types.get(q.get('question_type'),0)+1
    print(f"  types        : {types}")
    print(f"  first ids    : {[q.get('id') for q in qs[:8]]}")
    w=d.get("parse_warnings") or sv.get("parse_warnings") or []
    print(f"  warnings({len(w)}): {[str(x)[:70] for x in w[:4]]}")
