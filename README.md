# PodLens — Intelligent YouTube Podcast Analyzer for Audience Insights

PodLens turns the comments on a YouTube podcast video into audience
insights. Give it a video URL and it collects the available comments,
cleans them, filters out spam, classifies sentiment, highlights the most
engaged/important comments, and (if an LLM is configured) summarizes
audience reaction and suggests future topics — all shown on a dashboard and
in a full report.

This is a Final Year Project. Two of the ML components — spam detection and
sentiment analysis — are placeholders for models **you train separately**
(a fine-tuned BERT-tiny and a fine-tuned RoBERTa). This application does not
train, fine-tune, or guess at either model; it loads whatever trained
artifacts you place in `model_artifacts/` and reports clearly if they are
missing or incompatible.

## 1. What PodLens does

1. Accepts and validates a YouTube video URL.
2. Collects video metadata and comments via the official YouTube Data API v3.
3. Cleans and deduplicates comments while keeping the original text.
4. Classifies each comment as spam / not spam (your fine-tuned BERT-tiny model).
5. Classifies the sentiment of non-spam comments as positive / negative / neutral (your fine-tuned RoBERTa model).
6. Identifies the most important comments using a transparent, explainable scoring rule (engagement + content length), not another trained model.
7. Generates an audience reaction summary and future topic suggestions with an LLM (OpenAI by default), grounded only in the real comments collected.
8. Displays everything on a dashboard with charts, a filterable comments table, and a full report.
9. Persists videos, comments, per-comment classifications, and analysis results in SQLite.

Nothing outside this list is implemented (no auth, no billing, no publishing, no browser extension, etc.) per the project scope.

## 2. Architecture

```
Frontend (HTML/CSS/vanilla JS + Chart.js)
        │  REST calls only — no direct DB access
        ▼
FastAPI backend (app/api)
        │
        ▼
AnalysisPipeline (app/services/analysis_service.py)
  1. youtube_service      – collect metadata + comments (YouTube Data API v3)
  2. preprocessing_service – clean + dedupe, keep original text
  3. spam_service          – BERT-tiny spam/not-spam (via model_loader)
  4. sentiment_service      – RoBERTa positive/negative/neutral (via model_loader)
  5. importance_service     – rule-based important-comment ranking
  6. audience_insight_service + llm_service – audience summary & topic ideas
        │
        ▼
SQLAlchemy models / repository → SQLite (podlens.db)
        │
        ▼
report_service – builds dashboard + report data from the same stored results
```

Each stage is a separate module so swapping in your trained models later
does not require touching the frontend, database schema, or API layer.

### Folder overview

- `app/main.py` — FastAPI app, startup, central error handling, serves `frontend/`.
- `app/config.py` — environment-based settings (pydantic-settings).
- `app/api/` — request/response schemas (`schemas.py`) and routes (`routes.py`).
- `app/core/` — domain exceptions and logging setup.
- `app/services/` — one module per pipeline stage (see diagram above).
- `app/models/` — SQLAlchemy ORM models, the abstract model interfaces, and the Hugging Face model loader.
- `app/database/` — engine/session setup and the repository (data-access) layer.
- `app/utils/` — pure helper functions (YouTube URL parsing, text cleaning).
- `frontend/` — static HTML/CSS/JS dashboard, served directly by FastAPI.
- `model_artifacts/` — where you place your two trained models (see section 13).
- `tests/` — pytest suite covering URL validation, preprocessing, spam/sentiment services (mocked), the pipeline, the database layer, and the API.

## 3. Prerequisites

- Python 3.11+ (project targets Python 3.1x; anything 3.10+ works with the pinned dependency versions)
- A YouTube Data API v3 key (free, from Google Cloud Console)
- (Optional, for audience insights) An OpenAI API key

## 4. Setup (Windows PowerShell)

```powershell
cd PodLens
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Generic (macOS/Linux):

```bash
cd PodLens
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### Configure environment variables

Edit `.env`:

- `YOUTUBE_API_KEY` — required to collect videos/comments.
- `MAX_COMMENTS_PER_VIDEO` — cap on comments fetched per video (default 200). The app never claims to have collected more than this if more exist — it reports a warning instead.
- `LLM_API_KEY`, `LLM_MODEL` — required for audience summary/topic generation. Leave `LLM_API_KEY` empty to run without this feature; the dashboard will clearly show "insights unavailable".
- `SENTIMENT_MODEL_DIR`, `SPAM_MODEL_DIR` — paths to your trained model folders (defaults point at `model_artifacts/...`).
- `SPAM_LABEL_MAP`, `SENTIMENT_LABEL_MAP` — only needed if your model's `config.json` doesn't already have a clear `id2label` mapping (see section 13).

### Getting a YouTube Data API key

1. Go to the Google Cloud Console → create/select a project.
2. Enable "YouTube Data API v3" under APIs & Services.
3. Create an API key under Credentials.
4. Paste it into `.env` as `YOUTUBE_API_KEY`.

### Getting an OpenAI API key (optional)

1. Create an account at platform.openai.com.
2. Create an API key.
3. Paste it into `.env` as `LLM_API_KEY`. `LLM_MODEL` defaults to `gpt-4o-mini`.

## 5. Running the application

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Then open `http://localhost:8000` in a browser. The database file
(`podlens.db`) is created automatically on first run.

## 6. Running tests

```powershell
.\.venv\Scripts\Activate.ps1
pytest
```

Tests do not download real models or call real external APIs — the spam,
sentiment, and LLM services are exercised through mock/stub implementations
of their interfaces. The YouTube/LLM integration code paths that require
real network credentials are exercised only up to the point where they
correctly report "not configured" (e.g. `test_analyze_without_youtube_key_returns_503`).

## 7. Placing your trained models

### Sentiment RoBERTa → `model_artifacts/sentiment_roberta/`

Place the Hugging Face-format export of your fine-tuned model
(`config.json`, tokenizer files, `model.safetensors` or `pytorch_model.bin`)
directly in this folder. Full details, including the exact label-mapping
requirements, are in `model_artifacts/sentiment_roberta/README.md`.

### Spam BERT-tiny → `model_artifacts/spam_bert_tiny/`

Same idea — place your exported Hugging Face model directory here. Full
details in `model_artifacts/spam_bert_tiny/README.md`.

### Label mappings you must verify

PodLens reads each model's `id2label` from its `config.json` and does not
assume label order. Before relying on real results:

1. Start the app and check the startup/first-analysis logs for a line like
   `Loaded spam_bert_tiny ... with labels {0: 'not_spam', 1: 'spam'}`.
2. If the logged labels look like `LABEL_0`/`LABEL_1` (placeholders) or are
   wrong, set `SPAM_LABEL_MAP` / `SENTIMENT_LABEL_MAP` in `.env` to the
   correct mapping, e.g. `SPAM_LABEL_MAP={"0": "not_spam", "1": "spam"}`.
3. Sentiment labels must resolve to exactly `positive`, `negative`, `neutral`.
   Spam labels must resolve to exactly `spam`, `not_spam`. Anything else
   raises a clear error during analysis rather than being silently
   misinterpreted.

### Verifying a model loaded successfully

Run an analysis (or just watch the startup log). On first use of each
model, you'll see either:

- `Loaded <model_name> from '<path>' on device '<cpu|cuda>' with labels {...}` — success.
- A `ModelNotAvailableError` message stating exactly what's missing (folder
  doesn't exist, missing `config.json`, missing weight file, or unresolved
  label mapping) — surfaced as an analysis warning, not a silent fallback.

## 8. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `503` on `/api/analyze` | `YOUTUBE_API_KEY` missing | Set it in `.env` and restart |
| Analysis status becomes `failed` immediately | Invalid/unsupported URL, video not found, or comments disabled | Check the `error_message` field returned by `/api/analysis/{id}/status` |
| Warning "Spam detection unavailable" / "Sentiment analysis unavailable" | Model artifacts missing/invalid in `model_artifacts/...` | Confirm `config.json` + weight file exist; check logs for the exact `ModelNotAvailableError` text |
| Warning "Audience insights unavailable" | `LLM_API_KEY` not set | Set it in `.env`, or accept that insights are disabled |
| `quotaExceeded` error during collection | YouTube API daily quota used up | Wait for quota reset or use a different API key/project |
| Sentiment/spam labels look swapped | Model's `config.json` id2label is wrong or placeholder | Set `SPAM_LABEL_MAP` / `SENTIMENT_LABEL_MAP` explicitly |

## 9. What still depends on you

- Training/fine-tuning and supplying the RoBERTa sentiment model artifacts.
- Training/fine-tuning and supplying the BERT-tiny spam model artifacts.
- A real `YOUTUBE_API_KEY` for live data collection.
- (Optional) A real `LLM_API_KEY` for audience summaries/topic suggestions.

Everything else — collection, preprocessing, storage, the model-loading
contract, importance ranking, the pipeline, the dashboard, the report, and
the test suite — is implemented and runnable today.
