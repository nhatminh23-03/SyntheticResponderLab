import json
from pathlib import Path
from fastapi.testclient import TestClient
from src.config.settings import AppSettings
from src.api.app import create_app
import src.api.app as appmod
appmod.startup_failures = lambda *a, **k: []
S=AppSettings(); client=TestClient(create_app(S))
PI = Path("/Users/mnd/Desktop/AI Hackathon/SyntheticResponderLab/NeoSmart-Hackathon-App/Provided Info")
sid = client.post("/api/v1/studies", json={}).json()["data"]["study"]["study_id"]
p = PI/"Neo Smart Living — Survey_HighPriority.md"
r = client.post(f"/api/v1/studies/{sid}/survey/upload", files={"file": (p.name, p.read_bytes(), "text/markdown")})
print("TOP-LEVEL data keys:", sorted(r.json()["data"].keys()))
print(json.dumps(r.json()["data"], default=str)[:900])
