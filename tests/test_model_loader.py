import json

import pytest

from app.core.exceptions import ModelNotAvailableError
from app.models.model_loader import resolve_label_map, validate_model_directory


def test_validate_model_directory_missing_dir(tmp_path):
    missing_dir = tmp_path / "does_not_exist"
    with pytest.raises(ModelNotAvailableError, match="does not exist"):
        validate_model_directory(str(missing_dir))


def test_validate_model_directory_missing_config(tmp_path):
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "pytorch_model.bin").write_bytes(b"fake")

    with pytest.raises(ModelNotAvailableError, match="config.json"):
        validate_model_directory(str(model_dir))


def test_validate_model_directory_missing_weights(tmp_path):
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "config.json").write_text(json.dumps({"id2label": {"0": "spam"}}))

    with pytest.raises(ModelNotAvailableError, match="weight file"):
        validate_model_directory(str(model_dir))


def test_validate_model_directory_valid(tmp_path):
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "config.json").write_text(json.dumps({"id2label": {"0": "spam"}}))
    (model_dir / "model.safetensors").write_bytes(b"fake")

    validate_model_directory(str(model_dir))  # should not raise


def test_resolve_label_map_prefers_explicit_map():
    config_map = {"0": "LABEL_0", "1": "LABEL_1"}
    explicit = {"0": "not_spam", "1": "spam"}

    result = resolve_label_map(config_map, explicit)

    assert result == {0: "not_spam", 1: "spam"}


def test_resolve_label_map_uses_config_when_not_placeholder():
    config_map = {"0": "not_spam", "1": "spam"}

    result = resolve_label_map(config_map, None)

    assert result == {0: "not_spam", 1: "spam"}


def test_resolve_label_map_raises_when_unresolvable():
    with pytest.raises(ModelNotAvailableError):
        resolve_label_map(None, None)
