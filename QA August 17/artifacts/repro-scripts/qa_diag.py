import json, os
from pathlib import Path
from src.config.settings import AppSettings
from src.persistence.session import create_session_factory
from src.services.health_service import build_health_payload
from src.adapters.legacy_backend.runtime import load_module

s = AppSettings()
sf = create_session_factory(s)
p = build_health_payload(s, sf)
print("=== /api/v1/health ===")
print("overall status:", p.status)
for name, c in p.checks.items():
    print(f"  {name:24s} {c.status:8s} {(c.message or '')[:90]}")

print()
print("=== persona grounding reality (NOT patched) ===")
pg = load_module("backend.simulation.persona_generator", s.legacy_app_root)
ps = load_module("backend.grounding.prior_sampler", s.legacy_app_root)
print("grounded_priors_available()      :", pg.grounded_priors_available())
print("cex_affordability_priors_avail() :", getattr(ps,'cex_affordability_priors_available',lambda:None)())
root = Path(ps.__file__).resolve().parents[2]
print("priors_dir resolved to           :", root/"data"/"processed"/"priors")
print("priors_dir exists                :", (root/"data"/"processed"/"priors").exists())

print()
print("=== what mode does a REAL run get? ===")
schemas = load_module("backend.schemas", s.legacy_app_root)
af = schemas.AudienceFilter(state="California", age_min=30, age_max=55, homeowner_only=True)
for flag in (True, False):
    profiles, mode = pg.generate_persona_profiles_with_mode(audience_filter=af, sample_size=3, use_grounded_priors=flag)
    print(f"  use_grounded_priors={str(flag):5s} -> mode={mode!r}  n={len(profiles)}")
