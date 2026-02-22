"""Configuration loading for Homi agent settings."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

DEFAULT_CONFIG_PATH = "homi.config.json"
DEFAULT_PROVIDER = "ollama"
DEFAULT_ENDPOINT = "http://localhost:11434"
DEFAULT_MODEL = "gpt-oss:20b"
DEFAULT_TEMPERATURE = 0.2


@dataclass(frozen=True)
class AgentConfig:
    """Runtime agent configuration values."""

    provider: str
    model_id: str
    endpoint: str | None
    temperature: float | None
    system_prompt: str | None
    model_params: Mapping[str, Any]


def _parse_temperature(raw_value: object, source: str) -> float:
    try:
        return float(raw_value)
    except (TypeError, ValueError) as exc:  # pragma: no cover - simple guard
        raise ValueError(
            f"Invalid temperature value from {source}: {raw_value!r}. Must be numeric."
        ) from exc


def _coalesce(*values: object) -> object | None:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _load_config_file(config_path: Path) -> tuple[dict[str, object], dict[str, object]]:
    if not config_path.exists():
        return {}, {}

    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in config file '{config_path}': {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"Config file '{config_path}' must contain a JSON object.")

    model_section: dict[str, object] = {}
    agent_section: dict[str, object] = {}

    raw_model = payload.get("model")
    if raw_model is not None:
        if not isinstance(raw_model, dict):
            raise ValueError(
                f"Config file '{config_path}' has invalid 'model' section; expected object."
            )
        model_section = dict(raw_model)

    raw_agent = payload.get("agent")
    if raw_agent is not None:
        if not isinstance(raw_agent, dict):
            raise ValueError(
                f"Config file '{config_path}' has invalid 'agent' section; expected object."
            )
        agent_section = dict(raw_agent)

    # Backwards compatibility with earlier flat / agent-scoped config keys.
    legacy_container: dict[str, object] = (
        agent_section if agent_section else dict(payload)
    )
    for key in ("provider", "model_id", "host", "endpoint", "temperature", "params"):
        if key in legacy_container and key not in model_section:
            model_section[key] = legacy_container[key]

    if "system_prompt" in legacy_container and "system_prompt" not in agent_section:
        agent_section["system_prompt"] = legacy_container["system_prompt"]

    return model_section, agent_section


def _parse_model_params(raw_value: object, source: str) -> dict[str, Any]:
    if raw_value is None:
        return {}
    if not isinstance(raw_value, dict):
        raise ValueError(
            f"Invalid model params from {source}: expected JSON object/dict, got {type(raw_value).__name__}."
        )
    return dict(raw_value)


def resolve_agent_config(
    *,
    config_path: str | Path | None = None,
    provider_override: str | None = None,
    host_override: str | None = None,
    model_override: str | None = None,
    temperature_override: float | None = None,
    system_prompt_override: str | None = None,
    env: Mapping[str, str] | None = None,
) -> AgentConfig:
    """Resolve config with precedence: CLI overrides > env vars > config file > defaults."""
    env_data = env if env is not None else os.environ

    path_value = config_path or env_data.get("HOMI_CONFIG", DEFAULT_CONFIG_PATH)
    path = Path(path_value).expanduser()
    model_config, agent_config = _load_config_file(path)

    provider = str(
        _coalesce(
            provider_override,
            env_data.get("HOMI_MODEL_PROVIDER"),
            model_config.get("provider"),
            DEFAULT_PROVIDER,
        )
    )
    model_id = str(
        _coalesce(
            model_override,
            env_data.get("HOMI_MODEL_ID"),
            env_data.get("OLLAMA_MODEL"),  # legacy fallback
            model_config.get("model_id"),
            DEFAULT_MODEL,
        )
    )

    raw_endpoint = _coalesce(
        host_override,
        env_data.get("HOMI_MODEL_ENDPOINT"),
        env_data.get("OLLAMA_HOST"),  # legacy fallback
        model_config.get("endpoint"),
        model_config.get("host"),  # legacy fallback
    )
    endpoint = str(raw_endpoint) if raw_endpoint is not None else None
    if endpoint is None and provider.lower() == "ollama":
        endpoint = DEFAULT_ENDPOINT

    if temperature_override is not None:
        temperature = float(temperature_override)
    elif "HOMI_MODEL_TEMPERATURE" in env_data:
        temperature = _parse_temperature(
            env_data["HOMI_MODEL_TEMPERATURE"], "HOMI_MODEL_TEMPERATURE"
        )
    elif "OLLAMA_TEMPERATURE" in env_data:  # legacy fallback
        temperature = _parse_temperature(
            env_data["OLLAMA_TEMPERATURE"], "OLLAMA_TEMPERATURE"
        )
    elif model_config.get("temperature") is not None:
        temperature = _parse_temperature(
            model_config.get("temperature"), f"config file '{path}'"
        )
    else:
        temperature = DEFAULT_TEMPERATURE if provider.lower() == "ollama" else None

    system_prompt_raw = _coalesce(
        system_prompt_override,
        env_data.get("HOMI_SYSTEM_PROMPT"),
        agent_config.get("system_prompt"),
    )
    system_prompt = str(system_prompt_raw) if system_prompt_raw is not None else None

    mutable_model_params = _parse_model_params(
        model_config.get("params"),
        f"config file '{path}'",
    )
    model_params = MappingProxyType(mutable_model_params)

    return AgentConfig(
        provider=provider,
        model_id=model_id,
        endpoint=endpoint,
        temperature=temperature,
        system_prompt=system_prompt,
        model_params=model_params,
    )
