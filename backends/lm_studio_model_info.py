"""Read loaded-model configuration from LM Studio's native model-list API."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class ParallelLimitDetection:
    parallel: int | None
    model_key: str | None
    instance_id: str | None
    error: str | None = None


def native_models_url(base_url: str) -> str:
    value = base_url.strip()
    if not value:
        raise ValueError("LM Studio base URL must not be empty")
    parts = urlsplit(value)
    path = parts.path.rstrip("/")
    for suffix in (
        "/api/v1/chat",
        "/api/v1/models",
        "/api/v1",
        "/v1/chat/completions",
        "/v1/models",
        "/v1",
    ):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break
    root = urlunsplit((parts.scheme, parts.netloc, path, "", "")).rstrip("/")
    return f"{root}/api/v1/models"


def detect_parallel_limit(
    *,
    model: str,
    base_url: str = "http://localhost:1234/v1",
    timeout_seconds: float = 10.0,
) -> ParallelLimitDetection:
    """Return the loaded instance's configured parallel prediction limit.

    LM Studio exposes this as ``loaded_instances[].config.parallel``. Exact loaded
    instance ID matches are preferred, then exact model-key matches. Detection is
    advisory and returns an error string rather than blocking inference.
    """
    request = Request(native_models_url(base_url), method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return ParallelLimitDetection(
            parallel=None,
            model_key=None,
            instance_id=None,
            error=f"HTTP {exc.code}: {detail}",
        )
    except URLError as exc:
        return ParallelLimitDetection(
            parallel=None,
            model_key=None,
            instance_id=None,
            error=str(exc.reason),
        )
    except (TimeoutError, json.JSONDecodeError) as exc:
        return ParallelLimitDetection(
            parallel=None,
            model_key=None,
            instance_id=None,
            error=f"{type(exc).__name__}: {exc}",
        )

    models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        return ParallelLimitDetection(
            parallel=None,
            model_key=None,
            instance_id=None,
            error="Unexpected /api/v1/models response shape",
        )

    exact_instance: tuple[str | None, dict[str, Any]] | None = None
    exact_key: tuple[str | None, dict[str, Any]] | None = None
    for model_entry in models:
        if not isinstance(model_entry, dict):
            continue
        key = model_entry.get("key")
        key_value = key if isinstance(key, str) else None
        instances = model_entry.get("loaded_instances")
        if not isinstance(instances, list):
            continue
        for instance in instances:
            if not isinstance(instance, dict):
                continue
            instance_id = instance.get("id")
            if instance_id == model:
                exact_instance = (key_value, instance)
                break
            if key_value == model and exact_key is None:
                exact_key = (key_value, instance)
        if exact_instance is not None:
            break

    selected = exact_instance or exact_key
    if selected is None:
        return ParallelLimitDetection(
            parallel=None,
            model_key=None,
            instance_id=None,
            error=f"No loaded instance matched model {model!r}",
        )

    model_key, instance = selected
    instance_id = instance.get("id")
    config = instance.get("config")
    parallel = config.get("parallel") if isinstance(config, dict) else None
    if not isinstance(parallel, int) or isinstance(parallel, bool) or parallel < 1:
        return ParallelLimitDetection(
            parallel=None,
            model_key=model_key,
            instance_id=instance_id if isinstance(instance_id, str) else None,
            error="Loaded instance does not expose a positive config.parallel value",
        )

    return ParallelLimitDetection(
        parallel=parallel,
        model_key=model_key,
        instance_id=instance_id if isinstance(instance_id, str) else None,
        error=None,
    )
