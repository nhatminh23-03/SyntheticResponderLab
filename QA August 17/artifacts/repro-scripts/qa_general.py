import json
from src.config.settings import AppSettings
from src.adapters.legacy_backend.domain import execute_simulation_run, build_insights_view
S=AppSettings(); MODELS=["openai/gpt-4o-mini","google/gemini-2.0-flash-001"]
AUD={"state":"California","age_min":25,"age_max":60}
PROD={"business_name":"Ridgeline Coffee Roasters","product_name":"Single-Origin Subscription",
      "product_type":"Coffee subscription","product_description":"Monthly single-origin beans."}
MKT={"category":"Specialty coffee subscription","substitutes":["Grocery beans","Local cafe"]}

def survey(ids):
    return {"survey_title":"Coffee Subscription Study","questions":[
      {"id":ids[0],"text":"Would you subscribe to a monthly coffee box?","question_type":"single_choice","options":["Yes","No","Maybe"]},
      {"id":ids[1],"text":"How interested are you (1-5)?","question_type":"likert","min_value":1,"max_value":5},
      {"id":ids[2],"text":"How much would you pay per month (USD)?","question_type":"numeric","min_value":0,"max_value":100},
      {"id":ids[3],"text":"What would stop you from subscribing?","question_type":"open_text"}]}

def probe(label, ids):
    sv=survey(ids)
    run=execute_simulation_run(settings=S,audience_payload=AUD,survey_payload=sv,
        experiment_payload={"sample_size":6,"selected_models":MODELS,"experiment_mode":"split","reruns_per_persona":1},
        product_payload=PROD,market_payload=MKT,geography_context=None)
    view=build_insights_view(settings=S, study_mode="general", latest_run_payload=run)
    print(f"\n{'#'*76}\n# {label}   question ids = {ids}\n{'#'*76}")
    print(f"available={view.get('available')}  records={len(run['response_records'])}  segments={sorted({r.get('segment_label') for r in run['response_records']})}")
    ex = view.get("executive_summary") or {}
    print("\n-- executive_summary --")
    for k,v in ex.items(): print(f"   {k:26s}: {v}")
    print("\n-- chart availability --")
    for key in ("barrier_ranking","message_performance","use_case_share","interest_ladder","segment_heatmap","model_difference"):
        c = view.get(key) or {}
        if isinstance(c,dict):
            av=c.get("available"); msg=(c.get("message") or "")[:78]
            rows=c.get("rows"); n=len(rows) if isinstance(rows,list) else "-"
            print(f"   {key:20s} available={str(av):5s} rows={str(n):4s} {msg}")
    # NaN / None scan
    blob=json.dumps(view, default=str)
    print("\n-- integrity scan --")
    print("   contains 'NaN' :", "NaN" in blob)
    print("   contains 'null':", blob.count("null"))
    return view

a = probe("VARIANT A — non-colliding IDs (C1..C4)", ["C1","C2","C3","C4"])
b = probe("VARIANT B — colliding IDs (Q1..Q4, auto-numbered like the normalizer produces)", ["Q1","Q2","Q3","Q4"])
print("\n"+"="*76)
print("STRONGEST/WEAKEST SEGMENT COMPARISON (the fabrication check)")
print("="*76)
for lbl,v in (("A non-colliding",a),("B colliding",b)):
    ex=v.get("executive_summary") or {}
    print(f"  {lbl:16s} strongest={ex.get('strongest_segment')!r:34s} weakest={ex.get('weakest_segment')!r}")
