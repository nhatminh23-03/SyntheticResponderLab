import json
from src.config.settings import AppSettings
from src.adapters.legacy_backend.domain import execute_simulation_run, build_insights_view
exec(open('qa_general.py').read().split('def probe')[0])   # reuse setup
def build(ids):
    sv=survey(ids)
    run=execute_simulation_run(settings=S,audience_payload=AUD,survey_payload=sv,
        experiment_payload={"sample_size":6,"selected_models":MODELS,"experiment_mode":"split","reruns_per_persona":1},
        product_payload=PROD,market_payload=MKT,geography_context=None)
    return build_insights_view(settings=S, study_mode="general", latest_run_payload=run)
v = build(["C1","C2","C3","C4"])
print("TOP-LEVEL KEYS of insights view:"); print("  ", sorted(v.keys()))
for k in sorted(v.keys()):
    val=v[k]
    if isinstance(val,dict):
        print(f"\n[{k}] dict keys -> {sorted(val.keys())[:12]}")
        if 'available' in val: print(f"     available={val['available']}  message={str(val.get('message'))[:90]}")
