from pathlib import Path
from fastapi.testclient import TestClient
from src.config.settings import AppSettings
from src.api.app import create_app
import src.api.app as appmod
appmod.startup_failures=lambda *a,**k: []
S=AppSettings(); client=TestClient(create_app(S))
for label,p in [("plain markdown (student-style)",Path("/tmp/coffee_survey.md")),
                ("Neo-style markdown",Path("/tmp/coffee_neostyle.md"))]:
    sid=client.post("/api/v1/studies",json={}).json()["data"]["study"]["study_id"]
    r=client.post(f"/api/v1/studies/{sid}/survey/upload",files={"file":(p.name,p.read_bytes(),"text/markdown")})
    sc=r.json()["data"]["survey"]["schema"]; qs=sc["questions"]
    print(f"\n{label}: HTTP {r.status_code}  title={str(sc.get('survey_title'))[:44]!r}")
    for q in qs:
        print(f"   {q['id']:5s} {q['question_type']:14s} opts={len(q.get('options') or [])} min={q.get('min_value')} max={q.get('max_value')}  {str(q.get('text'))[:44]}")
