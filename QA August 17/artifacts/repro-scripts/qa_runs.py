import json, sys, time
from src.config.settings import AppSettings
from src.adapters.legacy_backend.domain import execute_simulation_run

S = AppSettings()
MODELS = ["openai/gpt-4o-mini", "google/gemini-2.0-flash-001"]
SURVEY = {"survey_title":"QA Count Survey","questions":[
  {"id":"Q1","text":"Would you consider a backyard studio?","question_type":"single_choice","options":["Yes","No","Maybe"]},
  {"id":"Q2","text":"How interested are you (1-5)?","question_type":"likert","min_value":1,"max_value":5},
  {"id":"Q3","text":"What is your main concern?","question_type":"open_text"}]}
AUD = {"state":"California","age_min":30,"age_max":55,"homeowner_only":True}
PROD= {"business_name":"Neo Smart Living","product_name":"Tahoe Mini","product_type":"Backyard studio"}
MKT = {"category":"Backyard prefab studio","substitutes":["Traditional shed"]}
Q = len(SURVEY["questions"])

def run(mode, n, reruns=1):
    exp = {"sample_size":n,"selected_models":MODELS,"experiment_mode":mode,"reruns_per_persona":reruns}
    t=time.time()
    r = execute_simulation_run(settings=S, audience_payload=AUD, survey_payload=SURVEY,
        experiment_payload=exp, product_payload=PROD, market_payload=MKT, geography_context=None)
    el=time.time()-t
    recs = r["response_records"]
    ids  = {x["respondent_id"] for x in recs}
    dbg  = r.get("run_debug_summary") or {}
    gd   = r.get("generation_debug") or {}
    exec_pairs = len(recs)//Q if Q else 0
    if   mode=="split":     expected_exec = n
    elif mode=="mirror":    expected_exec = n*len(MODELS)
    else:                   expected_exec = n*reruns
    print(f"\n{'='*74}\nMODE={mode}  N={n}  M={len(MODELS)}  R={reruns}  Q={Q}   ({el:.1f}s)\n{'='*74}")
    print(f"  status                       : {r.get('status')}")
    print(f"  EXPECTED executions          : {expected_exec}")
    print(f"  ACTUAL   executions (recs/Q) : {exec_pairs}   {'OK' if exec_pairs==expected_exec else '<<< MISMATCH'}")
    print(f"  EXPECTED q-a records         : {expected_exec*Q}")
    print(f"  ACTUAL   q-a records         : {len(recs)}   {'OK' if len(recs)==expected_exec*Q else '<<< MISMATCH'}")
    print(f"  distinct respondent_id       : {len(ids)}  (UI 'Responses' tile uses THIS)")
    print(f"  total_generated_responses    : {r.get('total_generated_responses')}  (run summary uses THIS)")
    print(f"  models_used                  : {sorted(set(x['model'] for x in recs))}")
    print(f"  -- live vs fallback --")
    for k in ("total_answers","truly_live_answers","fallback_answers","provider_error_count","malformed_json_count","live_answer_rate","primary_live_path"):
        print(f"    {k:24s}: {dbg.get(k)}")
    print(f"    questions_parsed_from_live: {gd.get('questions_parsed_from_live')}  questions_fallback_to_mock: {gd.get('questions_fallback_to_mock')}  request_errors: {gd.get('request_errors')}")
    mock = [x for x in recs if isinstance(x.get('answer'),str) and x['answer'].startswith('Mock response from')]
    print(f"    open-text rows detectably fabricated: {len(mock)}")
    print(f"  warnings ({len(r.get('warnings') or [])}):")
    for w in (r.get("warnings") or []): print(f"    - {w}")
    return r

if __name__ == "__main__":
    out={}
    out["split"]     = run("split", 4)
    out["mirror"]    = run("mirror", 4)
    out["stability"] = run("stability", 4, reruns=3)
    json.dump({k:{"records":len(v["response_records"]),
                  "total_generated_responses":v.get("total_generated_responses"),
                  "distinct_ids":len({x["respondent_id"] for x in v["response_records"]}),
                  "debug":v.get("run_debug_summary")} for k,v in out.items()},
              open("qa_runs_result.json","w"), indent=2)
    print("\nsaved qa_runs_result.json")
