# Spam BERT-tiny model artifacts

This directory must contain your fine-tuned BERT-tiny spam/not-spam
classification model, exported in standard Hugging Face format. Do **not**
commit real model weights to git (see `.gitignore`); this README is the
only tracked file here.

## Required files

Place the output of `model.save_pretrained(...)` and
`tokenizer.save_pretrained(...)` directly in this folder:

- `config.json`
- `tokenizer_config.json`, `vocab.txt` (WordPiece tokenizer typical for
  BERT-family models)
- one of: `pytorch_model.bin` or `model.safetensors`
- `special_tokens_map.json` (if produced)

Example layout:

```
model_artifacts/spam_bert_tiny/
├── config.json
├── model.safetensors
├── special_tokens_map.json
├── tokenizer_config.json
└── vocab.txt
```

## Label mapping — read this carefully

PodLens does **not** assume which label id means "spam" vs "not spam". It
reads `id2label` from `config.json`. Your fine-tuning code should set this
explicitly, e.g.:

```python
model.config.id2label = {0: "not_spam", 1: "spam"}
model.config.label2id = {"not_spam": 0, "spam": 1}
```

If `id2label` is missing or contains placeholder values like `"LABEL_0"`,
`"LABEL_1"`, PodLens will log a warning and you must set the
`SPAM_LABEL_MAP` environment variable to the correct mapping, e.g.:

```
SPAM_LABEL_MAP={"0": "not_spam", "1": "spam"}
```

Label values must be exactly one of: `spam`, `not_spam` (case-sensitive)
for the rest of the application to recognize them correctly.

## Confidence threshold

`SPAM_CONFIDENCE_THRESHOLD` (default `0.5`) is used only for secondary
display/flagging purposes. The primary spam/not-spam decision always comes
from the model's own argmax prediction, not from this threshold.

## Verifying it loads

After placing the files, start the app and check the logs for a line like:

```
Loaded spam_bert_tiny from './model_artifacts/spam_bert_tiny' on device 'cpu' with labels {0: 'not_spam', 1: 'spam'}
```

If instead you see a `ModelNotAvailableError`, the error message will state
exactly what is missing (directory not found, missing config.json, missing
weight file, or unresolvable label mapping).
