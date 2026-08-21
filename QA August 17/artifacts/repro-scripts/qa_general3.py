import json
from src.config.settings import AppSettings
from src.adapters.legacy_backend.domain import execute_simulation_run, build_insights_view
exec(open('qa_general.py').read().split('def probe')[0])
def build(ids):
    sv=survey(ids)
    run=execute_simulation_run(settings=S,audience_payload=AUD,survey_payload=sv,
        experiment_payload={"sample_size":6,"selected_models":MODELS,"experiment_mode":"split","reruns_per_persona":1},
        product_payload=PROD,market_payload=MKT,geography_context=None)
    return build_insights_view(settings=S, study_mode="general", latest_run_payload=run), run
for label, ids in [("A: non-colliding C1-C4",["C1","C2","C3","C4"]),("B: colliding Q1-Q4",["Q1","Q2","Q3","Q4"])]:
    v,run = build(ids)
    print(f"\n{'='*78}\n{label}\n{'='*78}")
    for k,c in sorted((v.get("charts") or {}).items()):
        av=c.get("available"); msg=(c.get("message") or "").strip()
        rows=c.get("rows"); n=len(rows) if isinstance(rows,list) else "-"
        flag = "" if av else "  <-- unavailable"
        print(f"  {k:20s} available={str(av):5s} rows={str(n):3s} {msg[:72]}{flag}")
    ss=v.get("segment_story") or {}
    print(f"  segment_story: strongest={ss.get('strongest_segment')!r} weakest={ss.get('weakest_segment')!r} heatmap_available={ss.get('heatmap_available')}")
    tf=v.get("top_findings") or []
    print(f"  top_findings: {len(tf)}")
    for f in tf[:4]:
        print(f"     - [{f.get('confidence_label')}/{f.get('agreement_label')}] {str(f.get('title'))[:70]}")
    ev=(v.get("evidence_package") or {}).get("items") or []
    print(f"  evidence items: {len(ev)}  ids={[i.get('id') for i in ev][:9]}")
    seg_ev=[i for i in ev if 'segment' in str(i.get('id'))]
    for i in seg_ev: print(f"     SEGMENT EVIDENCE -> {i.get('id')}: {str(i.get('detail') or i.get('value'))[:110]}")
