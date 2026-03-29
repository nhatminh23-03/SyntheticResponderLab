# Frontend Migration First Pass

Updated: 2026-03-28  
Repo analyzed: `NeoSmart-Hackathon-App`  
Reference scope: current checked-out code after the latest pull

This revision supersedes the 2026-03-26 first pass. It is based on a fresh scan of the current Streamlit prototype and focuses on what materially changed for a future Next.js + Python migration.

Legend:
- `Found in code`: directly observed in the repository.
- `Inference`: architectural conclusion based on the observed implementation.

## A. Product Understanding

### What the app does

`Found in code`

The application is a grounded synthetic market research workflow. It lets a user:
- choose a study mode
- define a target audience
- define business and product context
- define competitor and market context
- upload a survey
- configure an experiment
- generate grounded personas
- generate survey responses through AI models as those personas
- analyze outputs
- surface trust, realism, benchmark, calibration, and stability framing
- extend the workflow into interviews, research briefs, and transcript-grounded analysis

### Why it exists

`Inference`

The product thesis is unchanged and still clear in the code:
1. ground personas first,
2. ask AI to respond as those personas second,
3. evaluate realism and trustworthiness after generation.

This is not a generic “AI survey simulator.” The grounding and validation layers are the product.

### What is materially newer than the previous pass

`Found in code`

The current codebase is now broader than a simple setup -> run -> analysis prototype.

Newly important capabilities:
- product-context enrichment from scraped product URLs
- product-context enrichment from uploaded product images analyzed with Google Cloud Vision
- image-derived labels, objects, and colors stored directly on `BusinessProductContext`
- richer interview demo/loading flows through `backend/fixtures.py`
- interview insights upgraded from chat-only to analytics + chat
- interview insights chat can now route through OpenRouter or Anthropic

### Product concepts that are now more explicit in code

`Found in code`

1. Grounded personas still combine:
- audience filters
- geography-aware priors
- affordability priors
- product context
- market context

2. Product context is no longer text-only:
- `app/pages/2_business_product_context.py`
- `backend/vision.py`
- `backend/scraper.py`

3. Interview extension is now a real branch of the product:
- `app/pages/9_interview_synthesis.py`
- `app/pages/10_research_brief.py`
- `app/pages/11_interview_insights.py`

4. Trust framing still matters:
- `backend/analysis/benchmark.py`
- `backend/analysis/realism.py`
- `backend/analysis/stability.py`
- `backend/grounding/calibration.py`

## B. Codebase Map

### Main app entrypoints

`Found in code`

Primary UI entrypoints:
- `app/main.py`
- `app/pages/1_audience_builder.py`
- `app/pages/2_business_product_context.py`
- `app/pages/3_competitor_market_context.py`
- `app/pages/4_survey_upload.py`
- `app/pages/5_experiment_design.py`
- `app/pages/6_run_simulation.py`
- `app/pages/7_analysis.py`
- `app/pages/8_insights.py`
- `app/pages/9_interview_synthesis.py`
- `app/pages/10_research_brief.py`
- `app/pages/11_interview_insights.py`

Important backend entrypoints already used by the UI:
- `backend/survey/parser.py::parse_uploaded_survey`
- `backend/survey/schema_normalizer.py::normalize_survey_payload`
- `backend/survey/validator.py::validate_survey_schema`
- `backend/grounding/geography_context.py::build_geography_context_from_zip`
- `backend/simulation/persona_generator.py::generate_persona_profiles_with_mode`
- `backend/simulation/run_manager.py::generate_response_records`
- `backend/simulation/llm_client.py::{list_openrouter_models, generate_text_with_openrouter}`
- `backend/simulation/interview_runner.py::run_interviews`
- `backend/simulation/interview_insights.py::{build_chatbot_system_prompt, call_chatbot, call_chatbot_anthropic, resolve_chatbot_backend}`
- `backend/vision.py::{extract_full_analysis, generate_full_context_from_image, generate_full_context_from_url}`
- `backend/scraper.py::scrape_product_page`
- `backend/fixtures.py::{load_prototype_personas, load_prototype_transcripts}`

### Directory-level map

`Found in code`

| Area | Current responsibility | Migration note |
|---|---|---|
| `app/` | Streamlit UI shell, page routing, page orchestration | Rebuild in Next.js |
| `app/pages/` | Workflow pages and a lot of orchestration logic | Replace as UI; extract orchestration into backend services |
| `app/ui/` | Streamlit render helpers and page fragments | UI-only; not reusable in Next.js |
| `backend/schemas.py` | Core Pydantic contracts | Strong reuse candidate |
| `backend/survey/` | Parse, normalize, validate survey files | Strong reuse candidate |
| `backend/grounding/` | Geography, priors, calibration | Strong reuse candidate, but dependent on external data assets |
| `backend/simulation/` | Persona generation, prompts, runs, interviews, model calls | Core reusable engine area |
| `backend/analysis/` | Quant analysis, realism, benchmark, findings, stability | Reusable with storage decoupling in places |
| `backend/storage.py` | Session persistence over `st.session_state` | Replace entirely |
| `backend/workflow.py` | Readiness checks using storage | Rewrite as storage-agnostic service |
| `backend/vision.py` | Google Vision + LLM-assisted product enrichment | Reuse with adapter/refactor |
| `backend/scraper.py` | Product URL text extraction | Reuse with adapter |
| `backend/fixtures.py` | Demo persona/transcript loading | Keep only as controlled demo utility |
| `backend/reporting/` | Reporting stubs | Not a migration priority yet |
| `backend/segmentation/` | Segmentation stubs | Not a migration priority yet |

### UI-only vs business logic vs backend/API candidates

`Found in code` + `Inference`

UI-only:
- `app/ui/*`

UI plus orchestration:
- all of `app/pages/*`

Business/domain logic:
- `backend/schemas.py`
- `backend/survey/*`
- `backend/grounding/*`
- `backend/simulation/*`
- `backend/analysis/*`
- `backend/presets.py`
- `backend/vision.py`
- `backend/scraper.py`
- `backend/fixtures.py`

Should become backend/API-layer candidates:
- all business/domain modules above except the pure Streamlit storage pieces

Not API-ready as-is:
- `backend/storage.py`
- `backend/workflow.py`
- `backend/analysis/question_stats.py`
- orchestration embedded in `app/pages/2_business_product_context.py`
- orchestration embedded in `app/pages/6_run_simulation.py`
- orchestration embedded in `app/pages/9_interview_synthesis.py`
- page-local chat/session handling in `app/pages/11_interview_insights.py`

### Module map for the requested capabilities

`Found in code`

| Capability | Main modules |
|---|---|
| Persona generation | `backend/simulation/persona_generator.py` |
| Priors / grounding | `backend/grounding/prior_sampler.py`, `backend/grounding/geography_context.py`, `backend/grounding/geography_prior_filter.py`, `backend/grounding/calibration.py` |
| Survey parsing / schema handling | `backend/survey/parser.py`, `backend/survey/schema_normalizer.py`, `backend/survey/validator.py`, `backend/schemas.py` |
| Simulation execution | `backend/simulation/run_manager.py` |
| LLM calling | `backend/simulation/llm_client.py`, `backend/simulation/interview_runner.py`, `backend/simulation/interview_insights.py`, `backend/vision.py` |
| Response validation | answer coercion is still mainly embedded in `backend/simulation/run_manager.py`; `backend/simulation/response_validator.py` is still placeholder-level |
| Analysis | `backend/analysis/question_stats.py`, `backend/analysis/benchmark.py`, `backend/analysis/realism.py`, `backend/analysis/stability.py`, `backend/analysis/findings.py` |
| Insights / reporting | `backend/analysis/findings.py`; `backend/reporting/*` remains mostly placeholder |
| Interview workflow | `backend/simulation/interview_prompt_builder.py`, `backend/simulation/interview_runner.py`, `backend/simulation/interview_insights.py`, plus `app/pages/9-11_*` |
| Product enrichment | `app/pages/2_business_product_context.py`, `backend/scraper.py`, `backend/vision.py` |
| Demo fixture loading | `backend/fixtures.py` |

## C. Runtime Flow

### Current end-to-end flow in plain English

`Found in code`

1. `app/main.py`
- user selects study mode
- current modes remain `neo_smart` and `general`

2. `app/pages/1_audience_builder.py`
- user defines the audience
- the page validates and stores `AudienceFilter`

3. `app/pages/2_business_product_context.py`
- user defines `BusinessProductContext`
- the page now supports:
  - manual entry
  - scrape + autofill from product URL
  - image upload + vision analysis + optional generated context
- saved business context can now include:
  - `product_image_labels`
  - `product_image_objects`
  - `product_image_colors`

4. `app/pages/3_competitor_market_context.py`
- user defines `MarketContext`

5. `app/pages/4_survey_upload.py`
- user uploads survey input
- backend parse -> normalize -> validate pipeline produces `SurveySchema`

6. `app/pages/5_experiment_design.py`
- user defines `ExperimentPlan`
- page can query model options from OpenRouter

7. `app/pages/6_run_simulation.py`
- loads saved study inputs
- resolves geography from ZIP when available
- checks prior availability
- generates personas
- runs survey-response generation through mock or live path
- stores run result, response records, and personas
- exposes calibration and stability outputs

8. `app/pages/7_analysis.py`
- loads response records and personas
- computes question-level and run-level analytics

9. `app/pages/8_insights.py`
- derives findings, trust framing, and recommendations

10. `app/pages/9_interview_synthesis.py`
- generates interviews through the live path or loads pre-generated demo transcripts/personas
- can load Neo sample data when transcripts are missing

11. `app/pages/10_research_brief.py`
- creates or loads a research brief
- includes a Neo example loader

12. `app/pages/11_interview_insights.py`
- loads research brief, product context, personas, and transcripts
- renders:
  - Overview
  - By Question
  - Demographics
  - Ask the Data
- routes chat requests through OpenRouter or Anthropic depending on environment

### How state is stored and passed

`Found in code`

Primary persistence boundary:
- `backend/storage.py`
- built directly on `st.session_state`

Workflow objects stored there:
- `study_mode`
- `audience_filter`
- `business_product_context`
- `market_context`
- `survey_schema`
- `experiment_plan`
- `geography_context`
- `simulation_result`
- `mock_response_records`
- `persona_profiles`
- `interview_transcripts`
- `research_brief`

Additional page-local state not fully normalized through storage:
- product enrichment scratch state such as `_vision_analysis` and `_vision_summary`
- interview insights chat state:
  - `insights_system_prompt`
  - `insights_messages`

### Important current data-flow coupling

`Found in code`

The new visual product fields are not just decorative.

Observed downstream usage:
- `backend/simulation/run_manager.py`
  - includes `product_image_labels` and `product_image_objects` in the context signals used for simulation prompts
- `backend/simulation/interview_prompt_builder.py`
  - includes labels, objects, and colors in interview prompts
- `app/ui/business_product_snapshot.py`
  - renders those saved visual details back to the user

### What the qualitative branch now looks like

`Found in code`

The qualitative path is now a real sub-workflow:
- `Interview Synthesis` can generate or load transcripts
- `Research Brief` can seed the qualitative analysis frame
- `Interview Insights` can summarize transcripts visually and answer follow-up questions

This means the future frontend should treat qualitative work as a first-class extension, not an afterthought page.

## D. Migration Assessment

### What should stay in Python

`Inference`

Keep these in Python:
- `backend/schemas.py`
- `backend/survey/*`
- `backend/grounding/*`
- `backend/simulation/persona_generator.py`
- `backend/simulation/run_manager.py`
- `backend/simulation/llm_client.py`
- `backend/simulation/interview_prompt_builder.py`
- `backend/simulation/interview_runner.py`
- `backend/simulation/interview_insights.py`
- `backend/analysis/*`
- `backend/scraper.py`
- `backend/vision.py`
- `backend/presets.py`

Reason:
- they already contain the core grounding, simulation, enrichment, analysis, and trust logic
- moving that logic into JavaScript would dilute the backend product moat and duplicate risk

### What can likely be reused unchanged or nearly unchanged

`Found in code` + `Inference`

Strong reuse candidates with thin adapter wrappers:
- `backend/schemas.py`
- `backend/survey/parser.py`
- `backend/survey/schema_normalizer.py`
- `backend/survey/validator.py`
- `backend/presets.py`
- `backend/grounding/prior_sampler.py`
- `backend/grounding/geography_context.py`
- `backend/grounding/geography_prior_filter.py`
- `backend/grounding/calibration.py`
- `backend/simulation/persona_generator.py`
- most of `backend/simulation/run_manager.py`
- `backend/simulation/prompt_builder.py`
- `backend/simulation/llm_client.py`
- `backend/simulation/interview_prompt_builder.py`
- `backend/simulation/interview_runner.py`
- `backend/simulation/interview_insights.py`
- `backend/analysis/benchmark.py`
- `backend/analysis/findings.py`
- `backend/analysis/realism.py`
- `backend/analysis/stability.py`
- `backend/scraper.py`
- most of `backend/vision.py`

### What needs adapters or refactor before API exposure

`Found in code` + `Inference`

- `backend/storage.py`
  - replace with real study/run persistence

- `backend/workflow.py`
  - preserve readiness rules
  - remove Streamlit storage dependency

- `backend/analysis/question_stats.py`
  - stop loading records from session-backed storage
  - accept explicit records or run ids

- `app/pages/2_business_product_context.py`
  - extract URL scrape, image analysis, and generated-context orchestration into backend services

- `app/pages/6_run_simulation.py`
  - split page logic into backend orchestration services and job execution boundaries

- `app/pages/9_interview_synthesis.py`
  - move demo loading and transcript generation orchestration into services

- `app/pages/11_interview_insights.py`
  - keep analytics rendering in the new frontend
  - move provider resolution, context building, and chat invocation behind APIs

- `backend/fixtures.py`
  - remove hard-coded external-path assumptions if demo data is kept

### What should be rebuilt in Next.js

`Inference`

Rebuild everything under `app/`, but do not copy the Streamlit page layout 1:1.

The new frontend should preserve the workflow logic while changing the presentation model:
- move from left-sidebar multipage flow to one-page guided narrative
- keep step ordering meaningful, but not page-shaped
- separate “section UX” from “service orchestration”

### Reusable backend/API candidates by domain

`Inference`

Good API-layer candidates right now:
- study draft save/load
- workflow readiness checks
- survey upload and normalized schema preview
- product URL scrape and autofill
- product image analysis and context enrichment
- geography resolve and grounding status
- persona preview
- run creation/status/results
- analysis summaries
- trust summaries
- research brief persistence
- interview transcript generation/listing
- transcript analytics and chat

## E. Frontend Migration Strategy

### Recommended future section order

`Inference`

- Main
- Study Mode
- Audience
- Product
- Market
- Survey
- Personas
- Experiment
- Run
- Analysis
- Insights
- Trust
- Interview Extension

### How the current app maps into that one-page experience

`Inference`

Main
- explain grounded synthetic research

Study Mode
- `neo_smart` vs `general`

Audience
- current audience builder forms

Product
- manual product context
- product URL autofill
- product image upload
- visual grounding preview

Market
- market and competitor inputs

Survey
- upload
- parsing feedback
- normalized question preview

Personas
- persona preview before run
- grounding notes
- geography and affordability status

Experiment
- simulation mode and model selection

Run
- create and monitor long-running run jobs

Analysis
- question explorer and summary

Insights
- deterministic findings and recommendations

Trust
- realism
- benchmark comparisons
- calibration
- stability

Interview Extension
- research brief
- transcript generation or demo load
- transcript analytics
- ask-the-data chat

### UX translation principles for the migration

`Inference`

Keep:
- clear step ordering
- explicit prerequisites
- debuggable outputs
- visible trust framing
- explicit fallback behavior

Change:
- replace the Streamlit sidebar with sticky top progress navigation
- replace page transitions with scroll-driven section transitions
- treat `Personas`, `Run`, `Trust`, and `Insights` as proof moments, not just forms
- make product enrichment visible as part of the story, not hidden behind widgets

### What not to copy from the Streamlit app

`Inference`

Do not carry over:
- page-level orchestration as frontend code
- `st.session_state` assumptions
- sidebars as the primary navigation model
- page-local service logic mixed into UI components

## F. Risks and Unknowns

### High-confidence risks

`Found in code`

1. Streamlit session-state coupling still dominates persistence.
- `backend/storage.py` remains the actual state boundary.

2. Workflow gating is still storage-coupled.
- `backend/workflow.py` depends on Streamlit-backed storage helpers.

3. Some analysis code still loads from storage instead of explicit inputs.
- `backend/analysis/question_stats.py`

4. Demo interview loading depends on an external file not present in this workspace.
- `backend/fixtures.py` expects `prototype/output/interview_transcripts.csv`
- that file was not found in the current workspace scan

5. Product enrichment adds new external-service dependencies.
- Google Cloud Vision
- URL scraping
- OpenRouter-based generated summaries/context

6. Environment metadata is incomplete.
- `.env.example` includes `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL`, `GOOGLE_CLOUD_API_KEY`, `DATA_ROOT`, `RUNS_DIR`
- code also uses `ANTHROPIC_API_KEY` and `HUD_API_TOKEN`
- those are not both represented in `.env.example`

7. Dependency metadata is incomplete.
- `requirements.txt` now includes `anthropic` and `plotly`
- the code still imports `pandas`
- `backend/vision.py` requires `cryptography` for service-account auth but `cryptography` is not listed in `requirements.txt`

8. The checked-in `data/` directory is still minimal.
- current scan shows only `data/processed/benchmarks/realism_targets_neo_smart_template.json`
- many priors and lookup assets still appear to be external/generated dependencies

9. README is stale relative to the implementation.
- it still describes the project as more scaffold/TODO-oriented than the current code actually is

### Migration-specific risks

`Inference`

1. The Product section is now a service-heavy step.
- a thin migration that only rebuilds text forms would already be behind the current product

2. Interview Insights is no longer just a chat widget.
- it is now a mixed analytics-and-chat surface with more frontend scope

3. Provider routing is split across experiences.
- quant/interview generation still centers on OpenRouter
- interview insights chat can route to Anthropic
- the future API should centralize provider selection and capability reporting

4. `backend/simulation/run_manager.py` remains monolithic.
- it is still the right place to preserve first
- it is not the right place to deeply refactor before the API boundary is stable

## G. Recommended Next Step

### Immediate recommendation

`Inference`

Revise the migration plan and initial service boundary to include the new product-enrichment and qualitative capabilities, not just the original setup -> persona preview path.

### Recommended first backend/API slice now

`Inference`

The first backend extraction should cover:
1. study create/load/update
2. workflow readiness
3. product URL autofill
4. product image analysis and visual context persistence
5. survey parse/normalize/validate
6. persona preview

### Why this changed from the earlier recommendation

`Inference`

On 2026-03-26, a setup + survey + persona-preview slice was enough.

On 2026-03-28, the Product step itself is materially smarter and already tied into downstream prompting. If the new stack skips product enrichment in the first slice, it will ship behind the current Streamlit behavior.

### Practical next artifact to produce before implementation

`Inference`

Create an explicit API contract and persistence model for:
- canonical `Study` state
- product enrichment endpoints
- survey upload
- persona preview
- workflow readiness

That gives the Next.js frontend a clean target while preserving the Python engine where the real product logic lives.
