# Phase 0 Thin Slice Backend Spec

Updated: 2026-03-28  
Workspace root: `SyntheticResponderLab`  
Reference implementation: `NeoSmart-Hackathon-App/`  
Implementation target: future `apps/api/` only  
Out of scope: app/frontend code, background simulation jobs, run execution, analysis pages, interview flows

This document translates the migration docs into Phase 0 implementation artifacts for the first thin slice only.

Thin-slice scope:
- create/load study
- save study mode
- save audience
- save product
- product URL autofill
- product image analysis
- save market
- survey upload/parse/validate
- workflow readiness
- persona preview

Guiding constraints honored:
- Python remains the source of truth for grounding, survey parsing, and persona generation
- `NeoSmart-Hackathon-App/` stays untouched
- adapters wrap existing Python logic instead of rewriting it in JavaScript

---

## A. Canonical Study Domain Model

### A1. Design goals

The canonical `Study` object for Phase 0 must:
- map cleanly to the current legacy schemas
- support save/load across the full thin slice
- preserve derived outputs separately from user-authored inputs
- keep auditability for enrichment and uploads
- be stable enough to back a one-page Next.js workflow

### A2. Supporting enums

#### `StudyMode`

Values:
- `neo_smart`
- `general`

Legacy source:
- `backend/storage.py::VALID_STUDY_MODES`

#### `StudyLifecycleStatus`

Stored values:
- `draft`
- `setup_in_progress`
- `ready_for_persona_preview`
- `persona_previewed`
- `archived`

Rules:
- `draft`: study exists but no meaningful sections saved
- `setup_in_progress`: at least one setup section saved
- `ready_for_persona_preview`: hard thin-slice prerequisites satisfied
- `persona_previewed`: latest persona preview exists
- `archived`: terminal state, not editable

#### `SectionStatus`

Stored values:
- `not_started`
- `saved`
- `invalid`
- `error`

Derived workflow values:
- `blocked`
- `ready`
- `complete`
- `warning`

Use:
- `SectionStatus` is stored on saved user/system components
- workflow stages derive `blocked/ready/complete/warning` from saved components

#### `AssetType`

Values:
- `survey_upload`
- `product_image`
- `scraped_page_text`

#### `AssetStatus`

Values:
- `uploaded`
- `available`
- `deleted`
- `failed`

#### `EnrichmentType`

Values:
- `product_url_autofill`
- `product_image_analysis`

#### `EnrichmentStatus`

Values:
- `pending`
- `completed`
- `failed`

#### `PersonaPreviewStatus`

Values:
- `completed`
- `failed`

#### `WorkflowStageKey`

Phase 0 values:
- `study_mode`
- `audience`
- `product`
- `market`
- `survey`
- `personas`

### A3. Canonical `Study` object

The canonical `Study` returned by `GET /api/v1/studies/{study_id}` should be:

```json
{
  "study_id": "std_01HV...",
  "lifecycle_status": "setup_in_progress",
  "owner": {
    "owner_user_id": null,
    "owner_org_id": null
  },
  "study_mode": {
    "status": "saved",
    "value": "neo_smart",
    "saved_at": "2026-03-28T18:42:11Z",
    "updated_at": "2026-03-28T18:42:11Z"
  },
  "audience": {
    "status": "saved",
    "value": {},
    "saved_at": "2026-03-28T18:43:08Z",
    "updated_at": "2026-03-28T18:43:08Z"
  },
  "product": {
    "status": "saved",
    "value": {},
    "saved_at": "2026-03-28T18:45:02Z",
    "updated_at": "2026-03-28T18:45:02Z"
  },
  "market": {
    "status": "saved",
    "value": {},
    "saved_at": "2026-03-28T18:46:18Z",
    "updated_at": "2026-03-28T18:46:18Z"
  },
  "survey": {
    "status": "saved",
    "source_asset_id": "ast_01HV...",
    "source_filename": "survey.md",
    "source_format": "md",
    "schema": {},
    "question_count": 12,
    "parse_warnings": [],
    "saved_at": "2026-03-28T18:47:10Z",
    "updated_at": "2026-03-28T18:47:10Z"
  },
  "product_enrichments": {
    "latest_url_autofill": {},
    "latest_image_analysis": {}
  },
  "derived": {
    "geography_context": {},
    "workflow": {},
    "latest_persona_preview": {}
  },
  "created_at": "2026-03-28T18:41:20Z",
  "updated_at": "2026-03-28T18:47:10Z",
  "archived_at": null
}
```

### A4. Field-by-field model

#### Root fields

| Field | Type | Required | Owned by | Notes |
|---|---|---|---|---|
| `study_id` | string | required | system | Public API id, stable |
| `lifecycle_status` | enum | required | system-derived | Based on saved sections and persona preview presence |
| `owner.owner_user_id` | string nullable | optional | system/auth | Null until auth exists |
| `owner.owner_org_id` | string nullable | optional | system/auth | Null until org ownership exists |
| `study_mode` | `StudyModeState` | required | user + system metadata | Always present as envelope, value may be null before save |
| `audience` | `AudienceState` | required | user + system metadata | Always present as envelope |
| `product` | `ProductState` | required | user + system metadata | Always present as envelope |
| `market` | `MarketState` | required | user + system metadata | Always present as envelope |
| `survey` | `SurveyState` | required | user + system metadata | Always present as envelope |
| `product_enrichments` | object | required | system | Latest enrichment history refs/results |
| `derived.geography_context` | `GeographyContext` nullable | derived | system | Built from audience ZIP during persona preview or explicit resolve |
| `derived.workflow` | `WorkflowReadiness` | derived | system | Returned in study payload for convenience |
| `derived.latest_persona_preview` | `PersonaPreviewResult` nullable | derived | system | Null until preview runs |
| `created_at` | timestamp | required | system | Creation time |
| `updated_at` | timestamp | required | system | Last mutation to any persisted child |
| `archived_at` | timestamp nullable | optional | system | Set only on archive |

#### `StudyModeState`

| Field | Type | Required | Owned by | Notes |
|---|---|---|---|---|
| `status` | enum `not_started/saved/invalid/error` | required | system | `saved` only when valid mode persisted |
| `value` | `StudyMode` nullable | optional | user | `neo_smart` or `general` |
| `saved_at` | timestamp nullable | optional | system | First successful save |
| `updated_at` | timestamp nullable | optional | system | Most recent change |

#### `AudienceState`

`value` maps directly to `backend.schemas.AudienceFilter`.

| Field | Type | Required | Owned by | Notes |
|---|---|---|---|---|
| `status` | enum | required | system | |
| `value.state` | string nullable | optional | user | Legacy `AudienceFilter.state` |
| `value.metro` | string nullable | optional | user | |
| `value.zip_code` | string nullable | optional | user | 5-digit ZIP validation from legacy schema |
| `value.age_min` | int nullable | optional | user | 0-120 |
| `value.age_max` | int nullable | optional | user | 0-120 |
| `value.income_min` | int nullable | optional | user | `>=0` |
| `value.income_max` | int nullable | optional | user | `>=0` |
| `value.homeowner_only` | bool | required | user | default `false` |
| `value.renter_only` | bool | required | user | default `false` |
| `value.household_size_min` | int nullable | optional | user | `>=1` |
| `value.household_size_max` | int nullable | optional | user | `>=1` |
| `value.work_from_home` | bool nullable | optional | user | |
| `value.lifestyle_tags` | string[] | required | user | default `[]` |
| `value.home_type` | string nullable | optional | user | |
| `value.notes` | string nullable | optional | user | |
| `saved_at` | timestamp nullable | optional | system | |
| `updated_at` | timestamp nullable | optional | system | |

#### `ProductState`

`value` maps directly to `backend.schemas.BusinessProductContext`.

| Field | Type | Required | Owned by | Notes |
|---|---|---|---|---|
| `status` | enum | required | system | |
| `value.business_name` | string nullable | optional | user | |
| `value.industry` | string nullable | optional | user | |
| `value.product_name` | string nullable | optional | user | Legacy validator requires `product_name` or `product_description` |
| `value.product_type` | string nullable | optional | user | |
| `value.product_description` | string nullable | optional | user | |
| `value.target_customer` | string nullable | optional | user | |
| `value.price_range` | string nullable | optional | user | |
| `value.primary_goal` | string nullable | optional | user | |
| `value.key_features` | string[] | required | user | default `[]` |
| `value.main_use_cases` | string[] | required | user | default `[]` |
| `value.main_pain_points_solved` | string[] | required | user | default `[]` |
| `value.main_barriers_or_concerns` | string[] | required | user | default `[]` |
| `value.product_image_labels` | string[] | required | user/system | Populated manually or from image analysis |
| `value.product_image_objects` | string[] | required | user/system | Populated manually or from image analysis |
| `value.product_image_colors` | string[] | required | user/system | Stored as formatted strings like `#AABBCC (42.1%)` |
| `value.notes` | string nullable | optional | user | |
| `saved_at` | timestamp nullable | optional | system | |
| `updated_at` | timestamp nullable | optional | system | |

#### `MarketState`

`value` maps directly to `backend.schemas.MarketContext` plus `CompetitorEntry`.

| Field | Type | Required | Owned by | Notes |
|---|---|---|---|---|
| `status` | enum | required | system | |
| `value.category` | string nullable | optional | user | |
| `value.direct_competitors` | `CompetitorEntry[]` | required | user | default `[]` |
| `value.substitutes` | string[] | required | user | default `[]` |
| `value.typical_price_band` | string nullable | optional | user | |
| `value.common_expected_features` | string[] | required | user | default `[]` |
| `value.common_objections` | string[] | required | user | default `[]` |
| `value.notes` | string nullable | optional | user | |
| `saved_at` | timestamp nullable | optional | system | |
| `updated_at` | timestamp nullable | optional | system | |

`CompetitorEntry` fields:
- `name`
- `product_type`
- `price_range`
- `key_features[]`
- `strengths[]`
- `weaknesses[]`

#### `SurveyState`

`schema` maps directly to `backend.schemas.SurveySchema`.

| Field | Type | Required | Owned by | Notes |
|---|---|---|---|---|
| `status` | enum | required | system | |
| `source_asset_id` | string nullable | optional | system | FK to uploaded survey asset |
| `source_filename` | string nullable | optional | system | Original uploaded filename |
| `source_format` | string nullable | optional | system | Legacy parser returns `md/docx/pdf` |
| `schema.survey_title` | string nullable | optional | derived | From parser/normalizer |
| `schema.description` | string nullable | optional | derived | |
| `schema.source_format` | string nullable | optional | derived | |
| `schema.parse_warnings` | string[] | required | derived | |
| `schema.questions` | `SurveyQuestion[]` | required when saved | derived | Must contain at least 1 question |
| `question_count` | int | required when saved | derived | Convenience field |
| `saved_at` | timestamp nullable | optional | system | |
| `updated_at` | timestamp nullable | optional | system | |

`SurveyQuestion` fields:
- `id`
- `text`
- `question_type`
- `options[]`
- `required`
- `min_value`
- `max_value`
- `help_text`

#### `ProductEnrichments`

These are system-owned records representing the latest enrichment attempt/results. They should not replace the canonical saved `product.value`; they are inputs that may or may not be applied.

`latest_url_autofill`:
- `enrichment_id`
- `status`
- `input_url`
- `scraped_text_asset_id` nullable
- `proposed_product_patch` object matching `BusinessProductContext`
- `warnings[]`
- `error` nullable
- `applied_to_product` bool
- `created_at`
- `completed_at`

`latest_image_analysis`:
- `enrichment_id`
- `status`
- `source_asset_id`
- `analysis.labels[]`
- `analysis.objects[]`
- `analysis.logos[]`
- `analysis.text`
- `analysis.colors[]`
- `analysis.web_entities[]`
- `proposed_product_patch`
  - `product_image_labels[]`
  - `product_image_objects[]`
  - `product_image_colors[]`
- `error` nullable
- `applied_to_product` bool
- `created_at`
- `completed_at`

#### `Derived.geography_context`

Maps to `backend.schemas.GeographyContext`.

Fields:
- `zip_code`
- `county_fips`
- `county_name`
- `cbsa_code`
- `cbsa_name`
- `puma`
- `tract_code`
- `source`

Ownership:
- system-derived only

#### `Derived.latest_persona_preview`

| Field | Type | Required | Owned by | Notes |
|---|---|---|---|---|
| `preview_id` | string | required when present | system | Stable id for latest preview |
| `status` | `completed/failed` | required when present | system | |
| `request.sample_size` | int | required | user request | Not persisted on root inputs |
| `request.use_grounded_priors` | bool | required | user request | defaults `true` |
| `request.use_geography_filtered_priors` | bool | required | user request | defaults `true` |
| `request.use_cex_affordability_priors` | bool | required | user request | defaults `true` |
| `request.seed` | int nullable | optional | user request | optional deterministic seed |
| `generation_mode` | string | required when completed | system-derived | Legacy values: `grounded_priors`, `heuristic_fallback`, `heuristic_only` |
| `grounded_priors_available` | bool | required when completed | derived | from legacy persona generator |
| `cex_affordability_available` | bool | required when completed | derived | from `prior_sampler` |
| `geography_context` | `GeographyContext` nullable | optional | derived | derived from audience ZIP if present |
| `prior_notes[]` | object[] | required when completed | derived | from `get_last_persona_prior_notes()` |
| `personas[]` | `PersonaProfile[]` | required when completed | derived | from legacy persona generator |
| `warning_messages[]` | string[] | required | system-derived | quality/degraded-mode warnings |
| `created_at` | timestamp | required when present | system | |
| `completed_at` | timestamp nullable | optional | system | |

### A5. Hard-required vs optional vs derived summary

#### Required root fields on every `Study`

- `study_id`
- `lifecycle_status`
- `owner`
- `study_mode` envelope
- `audience` envelope
- `product` envelope
- `market` envelope
- `survey` envelope
- `product_enrichments`
- `derived`
- `created_at`
- `updated_at`

#### Optional user-authored values

- `study_mode.value`
- all `audience.value.*`
- all `product.value.*` except product save requires at least `product_name` or `product_description`
- all `market.value.*`
- all survey fields before upload

#### Derived/system-only fields

- `lifecycle_status`
- all `saved_at/updated_at/created_at/completed_at`
- `source_asset_id`
- `question_count`
- `product_enrichments.*`
- `derived.geography_context`
- `derived.workflow`
- `derived.latest_persona_preview`

### A6. Workflow readiness rules for Phase 0

This spec intentionally does not reuse the legacy `backend/workflow.py` rules 1:1, because the old workflow assumes `experiment` exists and this slice does not.

Phase 0 workflow rules:

| Stage | Complete when | Blocking rules |
|---|---|---|
| `study_mode` | valid mode saved | none |
| `audience` | valid `AudienceFilter` saved | none |
| `product` | valid `BusinessProductContext` saved | requires `product_name` or `product_description` |
| `market` | valid `MarketContext` saved and not empty | API layer should reject fully empty saves |
| `survey` | validated `SurveySchema` saved | requires at least 1 normalized question |
| `personas` | latest successful persona preview exists | preview request requires saved audience; missing product/market/survey should be warnings, not hard blockers |

Hard prerequisite for `POST /personas/preview`:
- saved audience

Soft readiness warnings for `POST /personas/preview`:
- no saved study mode
- no saved product
- no saved market
- no saved survey
- ZIP present but geography lookup degraded
- grounding priors missing, falling back to heuristic mode

---

## B. API Contract

### B1. Common conventions

#### Base path

- `/api/v1`

#### Content types

- JSON for all non-upload endpoints
- `multipart/form-data` for survey upload and product image upload

#### Success response wrapper

Use a consistent top-level shape:

```json
{
  "data": {},
  "meta": {
    "request_id": "req_01HV...",
    "generated_at": "2026-03-28T19:10:00Z"
  }
}
```

#### Error response wrapper

```json
{
  "error": {
    "code": "validation_error",
    "message": "Human-readable summary",
    "details": {},
    "request_id": "req_01HV..."
  }
}
```

#### Standard error codes

- `validation_error` -> `400`
- `not_found` -> `404`
- `conflict` -> `409`
- `unsupported_media_type` -> `415`
- `provider_unavailable` -> `503`
- `dependency_missing` -> `503`
- `legacy_module_error` -> `500`

### B2. Endpoint contract table

---

### 1. `POST /api/v1/studies`

Purpose:
- create a new empty canonical study

Sync vs async:
- sync

Legacy modules called:
- none directly

Request schema:

```json
{
  "study_mode": "neo_smart",
  "owner_user_id": null,
  "owner_org_id": null
}
```

Request rules:
- body may be empty
- if `study_mode` provided, it must be `neo_smart` or `general`

Response schema:

```json
{
  "data": {
    "study": "<Canonical Study object>"
  }
}
```

Validation:
- validate `study_mode` using the same allowed values as legacy `backend/storage.py`

Error responses:
- `400 validation_error` for invalid `study_mode`

Implementation notes:
- initialize all section envelopes with `status = not_started`
- initialize `lifecycle_status = draft`

---

### 2. `GET /api/v1/studies/{study_id}`

Purpose:
- load the full canonical study snapshot

Sync vs async:
- sync

Legacy modules called:
- none directly

Request schema:
- path param `study_id`

Response schema:

```json
{
  "data": {
    "study": "<Canonical Study object>"
  }
}
```

Validation:
- `study_id` must resolve to a persisted study

Error responses:
- `404 not_found`

---

### 3. `PATCH /api/v1/studies/{study_id}/study-mode`

Purpose:
- save or update the selected study mode

Sync vs async:
- sync

Legacy modules called:
- conceptually mirrors `backend.storage.save_study_mode`

Request schema:

```json
{
  "study_mode": "neo_smart"
}
```

Response schema:

```json
{
  "data": {
    "study_mode": {
      "status": "saved",
      "value": "neo_smart",
      "saved_at": "2026-03-28T19:12:00Z",
      "updated_at": "2026-03-28T19:12:00Z"
    },
    "study_lifecycle_status": "setup_in_progress"
  }
}
```

Validation rules:
- `study_mode` required
- must be one of `neo_smart`, `general`

Error responses:
- `400 validation_error`
- `404 not_found`
- `409 conflict` if study archived

---

### 4. `PATCH /api/v1/studies/{study_id}/audience`

Purpose:
- validate and save `AudienceFilter`

Sync vs async:
- sync

Legacy modules called:
- `backend.schemas.AudienceFilter`

Request schema:
- exact `AudienceFilter` payload

```json
{
  "state": "California",
  "metro": "Los Angeles",
  "zip_code": "90049",
  "age_min": 25,
  "age_max": 64,
  "income_min": 50000,
  "income_max": 200000,
  "homeowner_only": true,
  "renter_only": false,
  "household_size_min": 1,
  "household_size_max": 4,
  "work_from_home": null,
  "lifestyle_tags": ["remote work", "wellness"],
  "home_type": "Single-family",
  "notes": "Primary launch audience."
}
```

Response schema:

```json
{
  "data": {
    "audience": {
      "status": "saved",
      "value": {},
      "saved_at": "2026-03-28T19:13:00Z",
      "updated_at": "2026-03-28T19:13:00Z"
    },
    "workflow": "<WorkflowReadiness>"
  }
}
```

Validation rules:
- use legacy `AudienceFilter` validation exactly:
  - ZIP must be 5 digits if provided
  - min/max ranges must be ordered
  - `homeowner_only` and `renter_only` cannot both be `true`

Error responses:
- `400 validation_error`
- `404 not_found`
- `409 conflict`

---

### 5. `PATCH /api/v1/studies/{study_id}/product`

Purpose:
- validate and save `BusinessProductContext`

Sync vs async:
- sync

Legacy modules called:
- `backend.schemas.BusinessProductContext`

Request schema:
- exact `BusinessProductContext` payload

```json
{
  "business_name": "Neo Smart Living",
  "industry": "Factory-built modular backyard structures",
  "product_name": "Tahoe Mini",
  "product_type": "Permit-light modular backyard studio",
  "product_description": "Compact backyard studio.",
  "target_customer": "Homeowners with backyard space",
  "price_range": "$23,000 delivered and installed",
  "primary_goal": "Validate demand",
  "key_features": ["Fast install", "Compact footprint"],
  "main_use_cases": ["Home office"],
  "main_pain_points_solved": ["Need extra space"],
  "main_barriers_or_concerns": ["Upfront cost"],
  "product_image_labels": ["Modular structure"],
  "product_image_objects": ["Glass door"],
  "product_image_colors": ["#AABBCC (31.2%)"],
  "notes": "Imported from visual analysis."
}
```

Response schema:

```json
{
  "data": {
    "product": {
      "status": "saved",
      "value": {},
      "saved_at": "2026-03-28T19:14:00Z",
      "updated_at": "2026-03-28T19:14:00Z"
    },
    "workflow": "<WorkflowReadiness>"
  }
}
```

Validation rules:
- legacy validator must pass
- specifically, `product_name` or `product_description` must be provided

Error responses:
- `400 validation_error`
- `404 not_found`
- `409 conflict`

---

### 6. `POST /api/v1/studies/{study_id}/product/url-autofill`

Purpose:
- scrape product page text and generate a proposed `BusinessProductContext`

Sync vs async:
- sync in Phase 0

Legacy modules called:
- `backend.scraper.scrape_product_page`
- `backend.vision.generate_full_context_from_url`
- `backend.schemas.BusinessProductContext`

Request schema:

```json
{
  "url": "https://example.com/product",
  "apply_to_product": false
}
```

Response schema:

```json
{
  "data": {
    "enrichment": {
      "enrichment_id": "pen_01HV...",
      "status": "completed",
      "input_url": "https://example.com/product",
      "proposed_product_patch": {},
      "warnings": [],
      "applied_to_product": false,
      "created_at": "2026-03-28T19:15:00Z",
      "completed_at": "2026-03-28T19:15:08Z"
    },
    "product": "<Current ProductState>"
  }
}
```

Validation rules:
- `url` required
- must be `http://` or `https://`
- hard timeout recommended: 20 seconds total

Behavior rules:
- scrape URL text first
- send scraped text through `generate_full_context_from_url`
- validate returned JSON by constructing `BusinessProductContext`
- if `apply_to_product = true`, overwrite the current saved product state with the validated result
- if `apply_to_product = false`, return only the proposed patch/enrichment result

Error responses:
- `400 validation_error` for bad URL
- `404 not_found`
- `503 provider_unavailable` when `OPENROUTER_API_KEY` missing
- `503 dependency_missing` when scraper/provider credentials missing
- `500 legacy_module_error` when scraped text cannot be converted into valid product context JSON

Important implementation note:
- store the enrichment result even when `apply_to_product = false`
- do not silently mutate the canonical product object unless explicitly requested

---

### 7. `POST /api/v1/studies/{study_id}/product/image-analysis`

Purpose:
- upload a product image, run Vision analysis, and optionally apply the visual fields to the saved product

Sync vs async:
- sync in Phase 0

Legacy modules called:
- `backend.vision.extract_full_analysis`
- `backend.schemas.BusinessProductContext` only when applying to product

Request schema:
- `multipart/form-data`

Fields:
- `file`: required image file (`jpg`, `jpeg`, `png`)
- `apply_to_product`: optional bool, default `false`

Response schema:

```json
{
  "data": {
    "asset": {
      "asset_id": "ast_01HV...",
      "asset_type": "product_image",
      "original_filename": "photo.jpg",
      "mime_type": "image/jpeg",
      "byte_size": 248233
    },
    "enrichment": {
      "enrichment_id": "pen_01HV...",
      "status": "completed",
      "analysis": {
        "labels": ["Prefabricated building"],
        "objects": ["Door"],
        "logos": [],
        "text": "",
        "colors": [{"hex": "#D9D9D2", "percentage": 24.1}],
        "web_entities": ["Backyard office"]
      },
      "proposed_product_patch": {
        "product_image_labels": ["Prefabricated building"],
        "product_image_objects": ["Door"],
        "product_image_colors": ["#D9D9D2 (24.1%)"]
      },
      "applied_to_product": false
    },
    "product": "<Current ProductState>"
  }
}
```

Validation rules:
- file required
- MIME/type extension must be one of `jpg/jpeg/png`
- size limit recommended: 10 MB

Behavior rules:
- persist uploaded image as `study_asset`
- call `extract_full_analysis(file_bytes)`
- convert color dicts to stored strings matching current app behavior:
  - `#HEX (percentage%)`
- if `apply_to_product = true`:
  - merge `product_image_labels`, `product_image_objects`, `product_image_colors` into the saved product
  - if no saved product exists yet, return `409 conflict` rather than creating a partial product silently

Error responses:
- `400 validation_error`
- `404 not_found`
- `409 conflict` when applying to product but no product exists yet
- `415 unsupported_media_type`
- `503 provider_unavailable` when Google Vision credentials are missing
- `500 legacy_module_error`

Important implementation note:
- this endpoint is intentionally narrower than `generate_full_context_from_image`
- Phase 0 scope is image analysis, not full LLM-generated product-context-from-image

---

### 8. `PATCH /api/v1/studies/{study_id}/market`

Purpose:
- validate and save `MarketContext`

Sync vs async:
- sync

Legacy modules called:
- `backend.schemas.CompetitorEntry`
- `backend.schemas.MarketContext`

Request schema:
- exact `MarketContext` payload

```json
{
  "category": "Backyard prefab studio",
  "direct_competitors": [
    {
      "name": "Competitor A",
      "product_type": "Prefab studio",
      "price_range": "$20k-$30k",
      "key_features": ["Fast install"],
      "strengths": ["Affordable"],
      "weaknesses": ["Low customization"]
    }
  ],
  "substitutes": ["Garage conversion"],
  "typical_price_band": "$20k-$35k",
  "common_expected_features": ["Natural light"],
  "common_objections": ["Permitting"],
  "notes": "Primary comparison set."
}
```

Response schema:

```json
{
  "data": {
    "market": {
      "status": "saved",
      "value": {},
      "saved_at": "2026-03-28T19:17:00Z",
      "updated_at": "2026-03-28T19:17:00Z"
    },
    "workflow": "<WorkflowReadiness>"
  }
}
```

Validation rules:
- validate competitors with legacy `CompetitorEntry`
- validate root object with legacy `MarketContext`
- additional API-layer rule recommended:
  - reject fully empty `MarketContext` payloads with no meaningful fields populated

Why this extra API rule is recommended:
- legacy `MarketContext` accepts a fully empty object
- saving an empty market payload would mark the section complete without adding value

Error responses:
- `400 validation_error`
- `404 not_found`
- `409 conflict`

---

### 9. `POST /api/v1/studies/{study_id}/survey/upload`

Purpose:
- upload a survey file, parse it, normalize it, validate it, and persist the canonical `SurveySchema`

Sync vs async:
- sync

Legacy modules called:
- `backend.survey.parser.parse_uploaded_survey`
- `backend.survey.schema_normalizer.normalize_survey_payload`
- `backend.survey.validator.validate_survey_schema`

Request schema:
- `multipart/form-data`

Fields:
- `file`: required file

Supported types:
- `.md`
- `.docx`
- `.pdf`

Response schema:

```json
{
  "data": {
    "asset": {
      "asset_id": "ast_01HV...",
      "asset_type": "survey_upload",
      "original_filename": "survey.md",
      "mime_type": "text/markdown",
      "byte_size": 9321
    },
    "survey": {
      "status": "saved",
      "source_asset_id": "ast_01HV...",
      "source_filename": "survey.md",
      "source_format": "md",
      "schema": {},
      "question_count": 12,
      "parse_warnings": [],
      "saved_at": "2026-03-28T19:18:00Z",
      "updated_at": "2026-03-28T19:18:00Z"
    },
    "workflow": "<WorkflowReadiness>"
  }
}
```

Validation rules:
- file required
- extension must be one of supported types
- parser output must contain at least one valid normalized question
- duplicate question ids are rejected by legacy `validate_survey_schema`

Error responses:
- `400 validation_error`
- `404 not_found`
- `415 unsupported_media_type`
- `500 legacy_module_error`

Implementation notes:
- store original binary upload as an asset
- store canonical normalized schema in persisted study state
- return parse warnings directly to client

---

### 10. `GET /api/v1/studies/{study_id}/workflow`

Purpose:
- compute and return thin-slice workflow readiness

Sync vs async:
- sync

Legacy modules called:
- no direct call to `backend/workflow.py`
- use legacy logic only as a conceptual reference

Response schema:

```json
{
  "data": {
    "workflow": {
      "stages": [
        {
          "stage_key": "study_mode",
          "status": "complete",
          "hard_blockers": [],
          "warnings": [],
          "completed_at": "2026-03-28T19:12:00Z"
        },
        {
          "stage_key": "personas",
          "status": "ready",
          "hard_blockers": [],
          "warnings": ["survey not yet uploaded"],
          "completed_at": null
        }
      ],
      "ready_for_persona_preview": true,
      "next_recommended_stage": "survey"
    }
  }
}
```

Derived rules:
- `ready_for_persona_preview = true` only when audience is saved
- missing product/market/survey should appear as warnings, not hard blockers
- if latest persona preview exists, `personas.status = complete`

Error responses:
- `404 not_found`

---

### 11. `POST /api/v1/studies/{study_id}/personas/preview`

Purpose:
- generate a deterministic persona preview from saved audience state using the legacy grounding pipeline

Sync vs async:
- sync

Legacy modules called:
- `backend.grounding.geography_context.build_geography_context_from_zip`
- `backend.simulation.persona_generator.generate_persona_profiles_with_mode`
- `backend.simulation.persona_generator.get_last_persona_prior_notes`
- `backend.simulation.persona_generator.grounded_priors_available`
- `backend.grounding.prior_sampler.cex_affordability_priors_available`

Request schema:

```json
{
  "sample_size": 12,
  "use_grounded_priors": true,
  "use_geography_filtered_priors": true,
  "use_cex_affordability_priors": true,
  "seed": 42
}
```

Request defaults:
- `sample_size = 12`
- `use_grounded_priors = true`
- `use_geography_filtered_priors = true`
- `use_cex_affordability_priors = true`
- `seed = null`

Response schema:

```json
{
  "data": {
    "persona_preview": {
      "preview_id": "ppr_01HV...",
      "status": "completed",
      "request": {
        "sample_size": 12,
        "use_grounded_priors": true,
        "use_geography_filtered_priors": true,
        "use_cex_affordability_priors": true,
        "seed": 42
      },
      "generation_mode": "grounded_priors",
      "grounded_priors_available": true,
      "cex_affordability_available": true,
      "geography_context": {},
      "prior_notes": [],
      "warning_messages": [],
      "personas": [],
      "created_at": "2026-03-28T19:20:00Z",
      "completed_at": "2026-03-28T19:20:01Z"
    },
    "workflow": "<WorkflowReadiness>"
  }
}
```

Validation rules:
- audience must already be saved
- `sample_size` must be `>= 1`
- recommended API cap: `sample_size <= 50` for preview responsiveness

Behavior rules:
- if audience has `zip_code`, build `GeographyContext` first
- call legacy persona generator with requested flags
- store:
  - preview request params
  - generated personas
  - generation mode
  - geography context
  - prior notes
- if grounded priors fail to load and legacy generator falls back heuristically:
  - do not fail request
  - return `generation_mode = heuristic_fallback`
  - include warning message

Error responses:
- `400 validation_error`
- `404 not_found`
- `409 conflict` when no audience is saved
- `500 legacy_module_error` only for unrecoverable failures not handled by legacy fallback logic

---

## C. Persistence Schema

### C1. Persistence design principles

For Phase 0, use a normalized shell with JSONB payloads for legacy-compatible objects.

Why:
- the legacy inputs already exist as stable Pydantic objects
- JSONB reduces impedance mismatch while the API boundary is being established
- audit/history still matters for uploads, enrichments, and persona previews

### C2. Tables

#### 1. `studies`

Purpose:
- root identity, ownership, and lifecycle status

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid pk` | internal PK |
| `public_id` | `text unique not null` | API-facing id, e.g. `std_...` |
| `owner_user_id` | `text null` | nullable until auth exists |
| `owner_org_id` | `text null` | nullable until orgs exist |
| `study_mode` | `text null` | `neo_smart` or `general` |
| `lifecycle_status` | `text not null` | enum from `StudyLifecycleStatus` |
| `latest_persona_preview_run_id` | `uuid null` | FK to `persona_preview_runs.id` |
| `created_at` | `timestamptz not null` | |
| `updated_at` | `timestamptz not null` | |
| `archived_at` | `timestamptz null` | |

Indexes:
- unique index on `public_id`
- index on `owner_user_id`
- index on `lifecycle_status`

#### 2. `study_section_states`

Purpose:
- persist the current canonical payload for each saved study section

Section keys for Phase 0:
- `study_mode`
- `audience`
- `product`
- `market`
- `survey`

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid pk` | |
| `study_id` | `uuid not null fk studies(id)` | |
| `section_key` | `text not null` | enum-like string |
| `status` | `text not null` | `not_started/saved/invalid/error` |
| `value_json` | `jsonb null` | canonical payload for the section |
| `validation_errors_json` | `jsonb null` | optional structured errors |
| `source_asset_id` | `uuid null fk study_assets(id)` | mainly for `survey` |
| `saved_at` | `timestamptz null` | first successful save |
| `updated_at` | `timestamptz not null` | last mutation |

Constraints:
- unique `(study_id, section_key)`

Notes:
- `survey.value_json` stores the full canonical `SurveySchema`
- `study_mode.value_json` may store `{"study_mode": "neo_smart"}`

#### 3. `study_assets`

Purpose:
- track uploaded survey files and uploaded product images

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid pk` | |
| `public_id` | `text unique not null` | API-facing id `ast_...` |
| `study_id` | `uuid not null fk studies(id)` | |
| `asset_type` | `text not null` | `survey_upload` or `product_image` |
| `status` | `text not null` | `uploaded/available/deleted/failed` |
| `original_filename` | `text not null` | |
| `mime_type` | `text not null` | |
| `byte_size` | `bigint not null` | |
| `sha256` | `text not null` | dedupe/debug |
| `storage_provider` | `text not null` | `local_fs` in Phase 0 |
| `storage_key` | `text not null` | relative key under artifacts root |
| `metadata_json` | `jsonb not null default '{}'` | parser hints, image dimensions, etc. |
| `created_at` | `timestamptz not null` | |
| `deleted_at` | `timestamptz null` | |

Indexes:
- index on `study_id`
- index on `(study_id, asset_type, created_at desc)`

#### 4. `study_product_enrichments`

Purpose:
- audit URL autofill and image analysis attempts/results

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid pk` | |
| `public_id` | `text unique not null` | API-facing id `pen_...` |
| `study_id` | `uuid not null fk studies(id)` | |
| `enrichment_type` | `text not null` | `product_url_autofill` or `product_image_analysis` |
| `status` | `text not null` | `pending/completed/failed` |
| `input_url` | `text null` | only for URL autofill |
| `source_asset_id` | `uuid null fk study_assets(id)` | only for image analysis |
| `request_json` | `jsonb not null default '{}'` | flags such as `apply_to_product` |
| `result_json` | `jsonb null` | proposed product patch, analysis data |
| `error_json` | `jsonb null` | provider/network/validation errors |
| `applied_to_product` | `boolean not null default false` | whether canonical product was mutated |
| `created_at` | `timestamptz not null` | |
| `completed_at` | `timestamptz null` | |

Indexes:
- index on `(study_id, enrichment_type, created_at desc)`

#### 5. `persona_preview_runs`

Purpose:
- persist the latest preview request and its derived metadata

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid pk` | |
| `public_id` | `text unique not null` | API-facing id `ppr_...` |
| `study_id` | `uuid not null fk studies(id)` | |
| `status` | `text not null` | `completed/failed` |
| `sample_size` | `integer not null` | |
| `use_grounded_priors` | `boolean not null` | |
| `use_geography_filtered_priors` | `boolean not null` | |
| `use_cex_affordability_priors` | `boolean not null` | |
| `seed` | `integer null` | |
| `generation_mode` | `text null` | `grounded_priors/heuristic_fallback/heuristic_only` |
| `grounded_priors_available` | `boolean null` | |
| `cex_affordability_available` | `boolean null` | |
| `geography_context_json` | `jsonb null` | `GeographyContext` snapshot |
| `prior_notes_json` | `jsonb not null default '[]'` | |
| `warning_messages_json` | `jsonb not null default '[]'` | |
| `created_at` | `timestamptz not null` | |
| `completed_at` | `timestamptz null` | |
| `error_json` | `jsonb null` | |

Indexes:
- index on `(study_id, created_at desc)`

#### 6. `persona_preview_personas`

Purpose:
- store the actual preview personas separately from run metadata

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid pk` | |
| `preview_run_id` | `uuid not null fk persona_preview_runs(id)` | |
| `study_id` | `uuid not null fk studies(id)` | denormalized for easier querying |
| `row_index` | `integer not null` | stable ordering |
| `persona_id` | `text not null` | legacy persona id |
| `fit_tier` | `text null` | denormalized from payload |
| `segment_label` | `text null` | denormalized from payload |
| `persona_json` | `jsonb not null` | full `PersonaProfile` snapshot |
| `created_at` | `timestamptz not null` | |

Constraints:
- unique `(preview_run_id, row_index)`

#### 7. `jobs`

Purpose:
- reserve a stable table for later async work

Phase 0 usage:
- create the table now
- none of the in-scope endpoints are required to enqueue jobs yet

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid pk` | |
| `public_id` | `text unique not null` | API-facing id `job_...` |
| `study_id` | `uuid null fk studies(id)` | nullable for global jobs |
| `job_type` | `text not null` | future values like `simulation_run`, `interview_generation` |
| `status` | `text not null` | `queued/running/completed/failed/cancelled` |
| `payload_json` | `jsonb not null default '{}'` | |
| `result_json` | `jsonb null` | |
| `error_json` | `jsonb null` | |
| `queued_at` | `timestamptz not null` | |
| `started_at` | `timestamptz null` | |
| `completed_at` | `timestamptz null` | |
| `heartbeat_at` | `timestamptz null` | |

### C3. Artifact storage design

#### Local filesystem storage in Phase 0

Store uploaded files under a backend-owned artifacts root.

Recommended path pattern:

```text
{ARTIFACTS_ROOT}/
  studies/
    {study_public_id}/
      survey/
        {asset_public_id}/
          original/{sanitized_filename}
      product-images/
        {asset_public_id}/
          original/{sanitized_filename}
      scraped-page-text/
        {asset_public_id}/
          original/page.txt
```

Recommended storage rules:
- `storage_provider = local_fs`
- `storage_key` stores the path relative to `ARTIFACTS_ROOT`
- always compute and store `sha256`
- never rely on original filename for lookup

#### Survey upload storage

Store:
- raw uploaded file in `study_assets`
- canonical normalized schema in `study_section_states(section_key='survey').value_json`

Do not store:
- parser intermediate payload as a separate first-class table unless debugging requires it later

#### Product image storage

Store:
- raw uploaded image in `study_assets`
- analysis result in `study_product_enrichments.result_json`
- applied visual fields in `study_section_states(section_key='product').value_json` only if explicitly applied

#### Product URL scrape storage

Recommended:
- store the full scraped text as an optional `study_asset` with `asset_type = scraped_page_text`
- keep the parsed/proposed product patch in `study_product_enrichments.result_json`

Why:
- it preserves auditability without forcing the canonical `Study` object to carry large page text blobs

### C4. Why JSONB is the right Phase 0 choice

- it preserves legacy payload shapes
- it minimizes refactor work while scaffolding the backend
- it keeps the API contract stable even if the legacy schemas evolve slightly
- it still allows targeted denormalization where queryability matters, such as preview personas and assets

---

## D. Environment and Asset Contract

### D1. Required env vars for `apps/api`

These should be treated as required for the API process to boot correctly in Phase 0.

| Env var | Required | Purpose |
|---|---|---|
| `APP_ENV` | yes | `development`, `staging`, `production` |
| `APP_DEBUG` | yes | debug mode flag |
| `DATABASE_URL` | yes | Postgres connection string |
| `ARTIFACTS_ROOT` | yes | writable directory for uploaded assets |
| `LEGACY_APP_ROOT` | yes | absolute path to `NeoSmart-Hackathon-App` for adapter imports/health checks |

Recommended defaults in local dev:
- `APP_ENV=development`
- `APP_DEBUG=true`
- `LEGACY_APP_ROOT=/Users/mnd/Desktop/AI Hackathon/SyntheticResponderLab/NeoSmart-Hackathon-App`

### D2. Capability-required provider env vars

These are not hard boot requirements, but the corresponding endpoint must report `503` when the capability is unavailable.

| Env var | Endpoint/capability | Required when |
|---|---|---|
| `OPENROUTER_API_KEY` | product URL autofill | using `POST /product/url-autofill` |
| `OPENROUTER_BASE_URL` | product URL autofill | optional override, default to legacy value |
| `GOOGLE_CLOUD_API_KEY` | product image analysis | using API-key auth for Vision |
| `GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON` | product image analysis | optional alternative to API key |
| `GOOGLE_CLOUD_SERVICE_ACCOUNT_PATH` | product image analysis | optional alternative to inline JSON |
| `HUD_API_TOKEN` | geography lookup fallback | only when local HUD lookup files are missing and ZIP enrichment should hit HUD API |

Notes:
- `backend/vision.py` currently reads `GOOGLE_CLOUD_API_KEY` directly and accepts service-account info as a function argument, not from env. The adapter layer should bridge `GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON/PATH` into that function call.
- `HUD_API_TOKEN` is used in code today but missing from the legacy `.env.example`.

### D3. Optional provider env vars for later phases

Not needed for the thin slice, but should be standardized now because the repo already references them.

| Env var | Current repo relevance |
|---|---|
| `ANTHROPIC_API_KEY` | used by interview insights provider routing |
| `RUNS_DIR` | legacy runtime override, not enough by itself for the new API |
| `DATA_ROOT` | present in `.env.example`, but legacy modules still resolve many paths relative to their own files |

### D4. Required local data assets for thin-slice quality

#### Required for grounded persona preview quality

Expected under:
- `NeoSmart-Hackathon-App/data/processed/priors/`

Required files:
- `age_income_priors.parquet`
- `ownership_home_type_priors.parquet`
- `household_size_priors.parquet`
- `work_mode_hints.parquet`

Optional but strongly preferred:
- `age_income_priors_geo.parquet`
- `ownership_home_type_priors_geo.parquet`
- `household_size_priors_geo.parquet`
- `work_mode_hints_geo.parquet`

Optional CEX add-ons:
- `cex_affordability_priors.parquet`
- `cex_spending_priors.parquet`

Behavior when missing:
- if required grounding priors are missing, persona preview should still work through the legacy heuristic fallback path
- API should expose this as a degraded-quality warning, not a silent success

#### Required for local geography enrichment quality

Expected under:
- `NeoSmart-Hackathon-App/data/processed/lookups/`

Preferred files:
- `hud_zip_cbsa_lookup.parquet`
- `hud_zip_county_lookup.parquet`

Optional:
- `hud_zip_puma_lookup.parquet`

Behavior when missing:
- `build_geography_context_from_zip()` will fall back to HUD API if `HUD_API_TOKEN` exists
- otherwise it returns ZIP-only fallback context

#### Not required for this slice

These are present in the repo or referenced by the wider app, but not required for Phase 0:
- `data/processed/benchmarks/realism_targets_neo_smart_template.json`
- interview transcript fixture CSV expected by `backend/fixtures.py`
- research-brief preset assets

### D5. Startup health checks

Implement `/api/v1/health` with structured checks.

#### Hard-fail startup checks

The API should refuse startup if any of these fail:
- `DATABASE_URL` missing or DB unreachable
- `ARTIFACTS_ROOT` missing or not writable
- `LEGACY_APP_ROOT` missing or not readable
- required Python packages for thin-slice imports are missing:
  - `pydantic`
  - `requests`
  - `python-docx`
  - `pypdf`
  - `pandas`

#### Boot-with-warning checks

The API may start in degraded mode if these fail:
- `OPENROUTER_API_KEY` missing
  - disable product URL autofill
- Vision credentials missing
  - disable product image analysis
- grounding prior parquet files missing
  - persona preview falls back heuristically
- local HUD lookup parquet files missing
  - geography lookup falls back to HUD API or ZIP-only
- `HUD_API_TOKEN` missing
  - no remote HUD fallback if local lookups absent
- `cryptography` missing while service-account auth is configured
  - Vision service-account path unavailable

#### Suggested health payload

```json
{
  "data": {
    "status": "degraded",
    "checks": {
      "database": {"status": "ok"},
      "artifacts_root": {"status": "ok"},
      "legacy_app_root": {"status": "ok"},
      "openrouter": {"status": "warn", "message": "OPENROUTER_API_KEY missing"},
      "google_vision": {"status": "ok"},
      "grounding_priors": {"status": "warn", "message": "Required parquet files missing"},
      "hud_lookups": {"status": "warn", "message": "Local lookup files missing"},
      "python_dependencies": {"status": "ok"}
    }
  }
}
```

### D6. Missing dependency fixes based on current repo findings

These are concrete fixes the new `apps/api` environment must include.

#### Must add for legacy parity

| Package | Why |
|---|---|
| `pandas` | directly imported by grounding and analysis modules; missing from legacy `requirements.txt` |
| `cryptography` | required by `backend/vision.py` for Google service-account auth |

#### Strongly recommended inferred additions

These are inferred from the observed code paths.

| Package | Why |
|---|---|
| `pyarrow` | `pandas.read_parquet()` is used heavily for priors/lookups; a parquet engine is needed |
| `python-multipart` | required for FastAPI multipart uploads |

#### New `apps/api` scaffold dependencies

These are not repo-finding fixes, but they are needed to scaffold the new backend cleanly.

| Package | Why |
|---|---|
| `fastapi` | API framework |
| `uvicorn` | ASGI server |
| `sqlalchemy` | ORM / SQL mapping |
| `alembic` | migrations |
| `psycopg[binary]` or equivalent | Postgres driver |
| `pydantic-settings` | environment loading |

### D7. Important contract notes from the legacy codebase

1. `DATA_ROOT` is present in the legacy `.env.example`, but many legacy modules still compute paths from `__file__` instead of actually honoring `DATA_ROOT`.

2. The current checked-out repo does not contain the full grounding asset set under `data/processed/priors` and `data/processed/lookups`. The API must therefore treat grounded persona preview as a capability that may be degraded, not guaranteed.

3. `HUD_API_TOKEN` and `ANTHROPIC_API_KEY` are used by code but not consistently documented in the legacy env files.

4. The prototype transcript CSV expected by `backend/fixtures.py` is not present in this workspace, but it is not needed for the thin slice.

---

## Recommended next move after this spec

Use this document to scaffold `apps/api` in this order:

1. create DB migrations for:
   - `studies`
   - `study_section_states`
   - `study_assets`
   - `study_product_enrichments`
   - `persona_preview_runs`
   - `persona_preview_personas`
   - `jobs`
2. implement the canonical `Study` response serializer
3. wire legacy adapters for:
   - `AudienceFilter`
   - `BusinessProductContext`
   - `MarketContext`
   - survey parser/normalizer/validator
   - geography context
   - persona preview
   - URL autofill
   - image analysis
4. implement `/health`
5. implement the thin-slice endpoints in the same order as the one-page UX
