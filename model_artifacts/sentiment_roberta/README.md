# Sentiment RoBERTa model artifacts

This directory must contain your fine-tuned RoBERTa sentiment classification
model, exported in standard Hugging Face format. Do **not** commit real
model weights to git (see `.gitignore`); this README is the only tracked
file here.

## Required files

Place the output of `model.save_pretrained(...)` and
`tokenizer.save_pretrained(...)` directly in this folder:

- `config.json`
- `tokenizer_config.json`, `vocab.json` / `tokenizer.json`, `merges.txt` (or
  whatever files your tokenizer produces - RoBERTa tokenizers typically need
  `vocab.json` and `merges.txt`, or a single `tokenizer.json` for the fast
  tokenizer)
- one of: `pytorch_model.bin` or `model.safetensors`
- `special_tokens_map.json` (if produced)

Example layout:

```
model_artifacts/sentiment_roberta/
├── config.json
├── merges.txt
├── model.safetensors
├── special_tokens_map.json
├── tokenizer_config.json
└── vocab.json
```

## Label mapping — read this carefully

PodLens does **not** assume label order. It reads `id2label` from
`config.json`. Your fine-tuning code should set this explicitly, e.g.:

```python
model.config.id2label = {0: "negative", 1: "neutral", 2: "positive"}
model.config.label2id = {"negative": 0, "neutral": 1, "positive": 2}
```

If `id2label` is missing or contains placeholder values like `"LABEL_0"`,
`"LABEL_1"`, `"LABEL_2"`, PodLens will log a warning and you must set the
`SENTIMENT_LABEL_MAP` environment variable to the correct mapping, e.g.:

```
SENTIMENT_LABEL_MAP={"0": "negative", "1": "neutral", "2": "positive"}
```

Label values must be exactly one of: `positive`, `negative`, `neutral`
(case-sensitive) for the rest of the application (dashboard, filters,
statistics) to recognize them correctly.

## Verifying it loads

After placing the files, start the app and check the logs for a line like:

```
Loaded sentiment_roberta from './model_artifacts/sentiment_roberta' on device 'cpu' with labels {0: 'negative', 1: 'neutral', 2: 'positive'}
```

If instead you see a `ModelNotAvailableError`, the error message will state
exactly what is missing (directory not found, missing config.json, missing
weight file, or unresolvable label mapping).
