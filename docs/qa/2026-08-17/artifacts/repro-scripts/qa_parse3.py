import json
from pathlib import Path
from fastapi.testclient import TestClient
from src.config.settings import AppSettings
from src.api.app import create_app
import src.api.app as appmod
appmod.startup_failures = lambda *a, **k: []
S=AppSettings(); client=TestClient(create_app(S))
PI = Path("/Users/mnd/Desktop/AI Hackathon/SyntheticResponderLab/NeoSmart-Hackathon-App/Provided Info")
CASES=[
 ("MD  Neo preset",            PI/"Neo Smart Living — Survey_HighPriority.md","text/markdown"),
 ("MD  non-Neo coffee",        Path("/tmp/coffee_survey.md"),"text/markdown"),
 ("DOCX aytm Neo",             PI/"aytm Survey #760085  (Neo Smart Living — Tahoe Mini Survey).docx","application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
 ("PDF Google-Forms Neo",      PI/"Neo Smart Living — Tahoe Mini Survey (High + Medium Priority) - Google Forms.pdf","application/pdf"),
 ("PDF prose (NOT a survey)",  PI/"Neo Smart Living Background.pdf","application/pdf"),
 ("PDF aytm joint challenge",  PI/"Aytm_x_Neo_Smart_Living_Joint_Challenge.docx.pdf","application/pdf"),
]
for label,path,ctype in CASES:
    if not path.exists(): print(f"{label:26s} SKIP missing"); continue
    sid=client.post("/api/v1/studies",json={}).json()["data"]["study"]["study_id"]
    r=client.post(f"/api/v1/studies/{sid}/survey/upload",files={"file":(path.name,path.read_bytes(),ctype)})
    print(f"\n{'-'*74}\n{label}   ({path.stat().st_size//1024} KB)   HTTP {r.status_code}")
    if r.status_code!=200:
        print("   ERROR:", r.json()["error"]["message"][:120]); continue
    sv=r.json()["data"]["survey"]; sc=sv.get("schema") or {}
    qs=sc.get("questions") or []
    t={}
    for q in qs: t[q.get("question_type")]=t.get(q.get("question_type"),0)+1
    print(f"   title : {str(sc.get('survey_title'))[:64]}")
    print(f"   format: {sv.get('source_format')}   questions: {len(qs)}   types: {t}")
    print(f"   ids   : {[q.get('id') for q in qs[:10]]}")
    w=sv.get("parse_warnings") or sc.get("parse_warnings") or []
    print(f"   warnings: {len(w)}")
    for x in w[:3]: print(f"      - {str(x)[:88]}")
