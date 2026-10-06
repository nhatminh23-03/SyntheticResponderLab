import json, time, collections
from src.config.settings import AppSettings
from src.adapters.legacy_backend.domain import execute_simulation_run
S=AppSettings()
SURVEY={"survey_title":"QA Live","questions":[
 {"id":"Q1","text":"Would you consider a backyard studio?","question_type":"single_choice","options":["Yes","No","Maybe"]},
 {"id":"Q2","text":"How interested are you (1-5)?","question_type":"likert","min_value":1,"max_value":5},
 {"id":"Q3","text":"What is your main concern?","question_type":"open_text"}]}
AUD={"state":"California","age_min":30,"age_max":55,"homeowner_only":True}
PROD={"business_name":"Neo Smart Living","product_name":"Tahoe Mini","product_type":"Backyard studio"}
MKT={"category":"Backyard prefab studio","substitutes":["Traditional shed"]}
Q=3
def run(label, models, mode, n, reruns=1):
    t=time.time()
    r=execute_simulation_run(settings=S,audience_payload=AUD,survey_payload=SURVEY,
      experiment_payload={"sample_size":n,"selected_models":models,"experiment_mode":mode,"reruns_per_persona":reruns},
      product_payload=PROD,market_payload=MKT,geography_context=None)
    el=time.time()-t; recs=r["response_records"]; dbg=r.get("run_debug_summary") or {}
    print(f"\n{'='*78}\n{label}\n  models={models}  mode={mode} N={n} R={reruns}   ({el:.1f}s)\n{'='*78}")
    print(f"  status={r.get('status')}  records={len(recs)}  live_answer_rate={dbg.get('live_answer_rate')}")
    print(f"  truly_live={dbg.get('truly_live_answers')}  fallback={dbg.get('fallback_answers')}  provider_errors={dbg.get('provider_error_count')}  malformed_json={dbg.get('malformed_json_count')}")
    # PER-MODEL fabrication breakdown via the open-text tell
    per=collections.defaultdict(lambda:[0,0])
    for x in recs:
        if x.get("question_type")=="open_text" or x.get("question_id")=="Q3":
            fab = isinstance(x.get("answer"),str) and x["answer"].startswith("Mock response from")
            per[x["model"]][1 if fab else 0]+=1
    print("  per-model open-text (real / fabricated):")
    for m,(real,fab) in sorted(per.items()): print(f"     {m:34s} real={real:3d}  fabricated={fab:3d}")
    # sample answers
    print("  sample open-text answers:")
    seen=set()
    for x in recs:
        if x.get("question_id")=="Q3" and x["model"] not in seen:
            seen.add(x["model"]); print(f"     [{x['model']}] {str(x['answer'])[:96]}")
    print(f"  warnings: {len(r.get('warnings') or [])}")
    for w in (r.get('warnings') or []): print(f"     - {w[:120]}")
    return r

GOOD=["openai/gpt-4o-mini","google/gemini-2.5-flash"]
ASCONFIGURED=["openai/gpt-4o-mini","google/gemini-2.0-flash-001"]   # app's own hardcoded default
run("TEST 1 — both models VALID (clean live baseline)", GOOD, "mirror", 3)
run("TEST 2 — app's HARDCODED DEFAULT pair (one model is dead)", ASCONFIGURED, "mirror", 3)
