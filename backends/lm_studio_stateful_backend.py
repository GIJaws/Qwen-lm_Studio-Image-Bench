"""LM Studio native stateful chat backend with streaming and branch support."""

from __future__ import annotations

import base64
import io
import json
from dataclasses import dataclass
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from PIL import Image


ProgressCallback = Callable[[str, str, dict[str, Any]], None]


class StatefulLMStudioBackendError(RuntimeError):
    """Raised when LM Studio rejects a stateful request or returns invalid data."""


@dataclass(frozen=True)
class StatefulChatResult:
    """Normalized result from LM Studio's native chat endpoint."""

    message: str
    reasoning: str
    response_id: str | None
    model_instance_id: str | None
    stats: dict[str, Any]
    raw_result: dict[str, Any]


@dataclass(frozen=True)
class StatefulLMStudioJudgeConfig:
    model: str
    base_url: str = "http://localhost:1234/v1"
    max_output_tokens: int = 4096
    temperature: float = 0.0
    top_k: int = 1
    top_p: float = 1.0
    repeat_penalty: float = 1.05
    timeout_seconds: float = 300.0
    image_format: str = "PNG"
    reasoning: str | None = "on"
    base_reasoning: str | None = "off"
    base_max_output_tokens: int = 8
    context_length: int | None = None
    stream: bool = True
    extra_body: dict[str, Any] | None = None

    @property
    def chat_url(self) -> str:
        return native_chat_url(self.base_url)


def native_chat_url(base_url: str) -> str:
    """Normalize a server root, ``/v1``, or ``/api/v1`` URL to native chat."""
    value = base_url.strip()
    if not value:
        raise ValueError("LM Studio base URL must not be empty")
    parts = urlsplit(value)
    path = parts.path.rstrip("/")
    for suffix in ("/api/v1/chat", "/api/v1", "/v1/chat/completions", "/v1"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break
    normalized = urlunsplit((parts.scheme, parts.netloc, path, "", "")).rstrip("/")
    return f"{normalized}/api/v1/chat"


class StatefulLMStudioJudge:
    """Create one stored image context, then branch independent evaluations."""

    IMAGE_MARKER = "<image>"

    def __init__(
        self,
        *,
        model: str,
        base_url: str = "http://localhost:1234/v1",
        max_output_tokens: int = 4096,
        temperature: float = 0.0,
        top_k: int = 1,
        top_p: float = 1.0,
        repeat_penalty: float = 1.05,
        timeout_seconds: float = 300.0,
        image_format: str = "PNG",
        reasoning: str | None = "on",
        base_reasoning: str | None = "off",
        base_max_output_tokens: int = 8,
        context_length: int | None = None,
        stream: bool = True,
        extra_body: dict[str, Any] | None = None,
    ) -> None:
        self.config = StatefulLMStudioJudgeConfig(
            model=model,
            base_url=base_url,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            top_k=top_k,
            top_p=top_p,
            repeat_penalty=repeat_penalty,
            timeout_seconds=timeout_seconds,
            image_format=image_format,
            reasoning=reasoning,
            base_reasoning=base_reasoning,
            base_max_output_tokens=base_max_output_tokens,
            context_length=context_length,
            stream=stream,
            extra_body=extra_body,
        )

    def create_shared_context(
        self,
        *,
        system_prompt: str | None,
        user_text: str,
        image: Image.Image,
        label: str = "Shared context",
        progress: ProgressCallback | None = None,
    ) -> StatefulChatResult:
        """Store the image and common prefix, returning a branchable response ID."""
        if not isinstance(image, Image.Image):
            raise TypeError("image must be a PIL.Image.Image")
        payload = self._base_payload(
            input_items=self._build_input_with_image(user_text, image),
            system_prompt=system_prompt,
            store=True,
            max_output_tokens=self.config.base_max_output_tokens,
            reasoning=self.config.base_reasoning,
        )
        result = self._request(payload, label=label, progress=progress)
        if not result.response_id:
            raise StatefulLMStudioBackendError(
                "LM Studio did not return response_id for stored shared context"
            )
        return result

    def evaluate_branch(
        self,
        *,
        previous_response_id: str,
        user_text: str,
        label: str,
        progress: ProgressCallback | None = None,
    ) -> StatefulChatResult:
        """Evaluate one dimension as an independent branch from shared context."""
        payload = self._base_payload(
            input_items=user_text,
            system_prompt=None,
            store=False,
            max_output_tokens=self.config.max_output_tokens,
            reasoning=self.config.reasoning,
        )
        payload["previous_response_id"] = previous_response_id
        return self._request(payload, label=label, progress=progress)

    def _base_payload(
        self,
        *,
        input_items: str | list[dict[str, Any]],
        system_prompt: str | None,
        store: bool,
        max_output_tokens: int,
        reasoning: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "input": input_items,
            "store": store,
            "stream": self.config.stream,
            "temperature": self.config.temperature,
            "top_k": self.config.top_k,
            "top_p": self.config.top_p,
            "repeat_penalty": self.config.repeat_penalty,
            "max_output_tokens": max_output_tokens,
        }
        if system_prompt is not None and system_prompt.strip():
            payload["system_prompt"] = system_prompt
        if reasoning is not None:
            payload["reasoning"] = reasoning
        if self.config.context_length is not None:
            payload["context_length"] = self.config.context_length
        if self.config.extra_body:
            payload.update(self.config.extra_body)
        return payload

    def _build_input_with_image(
        self,
        user_text: str,
        image: Image.Image,
    ) -> list[dict[str, Any]]:
        image_item = {
            "type": "image",
            "data_url": self._encode_image_data_url(image),
        }
        if self.IMAGE_MARKER not in user_text:
            return [
                {"type": "message", "content": user_text},
                image_item,
            ]

        before, after = user_text.split(self.IMAGE_MARKER, 1)
        items: list[dict[str, Any]] = []
        if before:
            items.append({"type": "message", "content": before})
        items.append(image_item)
        if after:
            items.append({"type": "message", "content": after})
        return items

    def _encode_image_data_url(self, image: Image.Image) -> str:
        buffer = io.BytesIO()
        image.save(buffer, format=self.config.image_format)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        media_type = self._image_media_type(self.config.image_format)
        return f"data:{media_type};base64,{encoded}"

    @staticmethod
    def _image_media_type(image_format: str) -> str:
        normalized = image_format.strip().upper()
        if normalized in {"JPEG", "JPG"}:
            return "image/jpeg"
        if normalized == "WEBP":
            return "image/webp"
        return "image/png"

    def _request(
        self,
        payload: dict[str, Any],
        *,
        label: str,
        progress: ProgressCallback | None,
    ) -> StatefulChatResult:
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if payload.get("stream"):
            headers["Accept"] = "text/event-stream"
        request = Request(
            self.config.chat_url,
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                if payload.get("stream"):
                    result = self._read_stream(response, label=label, progress=progress)
                else:
                    result = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise StatefulLMStudioBackendError(
                f"{label} failed with HTTP {exc.code}: {detail}"
            ) from exc
        except URLError as exc:
            raise StatefulLMStudioBackendError(
                f"{label} failed: {exc.reason}"
            ) from exc
        except TimeoutError as exc:
            raise StatefulLMStudioBackendError(
                f"{label} timed out after {self.config.timeout_seconds:g}s"
            ) from exc
        except json.JSONDecodeError as exc:
            raise StatefulLMStudioBackendError(
                f"{label} returned invalid JSON: {exc}"
            ) from exc

        return self._normalize_result(result, label=label)

    def _read_stream(
        self,
        response: Iterable[bytes],
        *,
        label: str,
        progress: ProgressCallback | None,
    ) -> dict[str, Any]:
        event_name: str | None = None
        data_lines: list[str] = []
        final_result: dict[str, Any] | None = None
        streamed_error: dict[str, Any] | None = None

        def dispatch() -> None:
            nonlocal event_name, data_lines, final_result, streamed_error
            if not data_lines:
                event_name = None
                return
            raw_data = "\n".join(data_lines)
            try:
                data = json.loads(raw_data)
            except json.JSONDecodeError as exc:
                raise StatefulLMStudioBackendError(
                    f"{label} returned invalid SSE JSON for {event_name}: "
                    f"{raw_data[:500]}"
                ) from exc
            event_type = event_name or str(data.get("type", "message"))
            if progress is not None:
                progress(label, event_type, data)
            if event_type == "chat.end":
                candidate = data.get("result")
                if isinstance(candidate, dict):
                    final_result = candidate
            elif event_type == "error":
                error_value = data.get("error")
                streamed_error = (
                    error_value
                    if isinstance(error_value, dict)
                    else {"message": str(error_value)}
                )
            event_name = None
            data_lines = []

        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
            if not line:
                dispatch()
                continue
            if line.startswith(":"):
                continue
            if line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        dispatch()

        if final_result is None:
            if streamed_error is not None:
                raise StatefulLMStudioBackendError(
                    f"{label} stream failed: "
                    f"{streamed_error.get('message', streamed_error)}"
                )
            raise StatefulLMStudioBackendError(
                f"{label} stream ended without chat.end result"
            )
        return final_result

    @staticmethod
    def _normalize_result(
        result: dict[str, Any],
        *,
        label: str,
    ) -> StatefulChatResult:
        output = result.get("output")
        if not isinstance(output, list):
            raise StatefulLMStudioBackendError(
                f"{label} returned unexpected output shape: {result!r}"
            )
        messages: list[str] = []
        reasoning: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, str):
                continue
            if item.get("type") == "message":
                messages.append(content)
            elif item.get("type") == "reasoning":
                reasoning.append(content)
        if not messages:
            raise StatefulLMStudioBackendError(
                f"{label} returned no message content: {result!r}"
            )
        stats = result.get("stats")
        return StatefulChatResult(
            message="".join(messages),
            reasoning="".join(reasoning),
            response_id=(
                result.get("response_id")
                if isinstance(result.get("response_id"), str)
                else None
            ),
            model_instance_id=(
                result.get("model_instance_id")
                if isinstance(result.get("model_instance_id"), str)
                else None
            ),
            stats=stats if isinstance(stats, dict) else {},
            raw_result=result,
        )
