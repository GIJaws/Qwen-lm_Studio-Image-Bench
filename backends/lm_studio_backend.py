"""LM Studio OpenAI-compatible inference backend for Qwen-Image-Bench.

The upstream harness treats each image/dimension pair as an independent
single-turn request. This backend preserves that contract and sends each task to
LM Studio's stateless /v1/chat/completions endpoint.
"""

from __future__ import annotations

import base64
import io
import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from PIL import Image


class LMStudioBackendError(RuntimeError):
    """Raised when LM Studio rejects a request or returns an invalid response."""


@dataclass(frozen=True)
class LMStudioJudgeConfig:
    """Configuration for LM Studio's OpenAI-compatible chat-completions API."""

    base_url: str = "http://localhost:1234/v1"
    model: str = "qwen-image-bench"
    max_new_tokens: int = 4096
    temperature: float = 0.0
    top_k: int = 1
    top_p: float = 1.0
    repeat_penalty: float = 1.05
    seed: int | None = 42
    timeout_seconds: float = 300.0
    image_format: str = "PNG"
    extra_body: dict[str, Any] | None = None

    @property
    def chat_completions_url(self) -> str:
        base = self.base_url.rstrip("/") + "/"
        return urljoin(base, "chat/completions")


class LMStudioJudge:
    """Drop-in judge backend matching MsSwiftJudge.generate_batch().

    Each input item must contain:
      - system_prompt: str
      - user_text: str
      - image: PIL.Image.Image

    The return value is a list of generated text strings in the same order as
    the input items, matching the interface expected by judge.py.
    """

    IMAGE_MARKER = "<image>"

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:1234/v1",
        max_new_tokens: int = 4096,
        temperature: float = 0.0,
        top_k: int = 1,
        top_p: float = 1.0,
        repeat_penalty: float = 1.05,
        seed: int | None = 42,
        timeout_seconds: float = 300.0,
        image_format: str = "PNG",
        extra_body: dict[str, Any] | None = None,
    ) -> None:
        self.config = LMStudioJudgeConfig(
            base_url=base_url,
            model=model,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_k=top_k,
            top_p=top_p,
            repeat_penalty=repeat_penalty,
            seed=seed,
            timeout_seconds=timeout_seconds,
            image_format=image_format,
            extra_body=extra_body,
        )

    def generate_batch(self, items: list[dict[str, Any]]) -> list[str]:
        """Generate one independent LM Studio response per item.

        The upstream ms-swift backend accepts a batch of independent InferRequest
        objects. LM Studio's REST API does not expose the same in-process batch
        primitive, so this method submits bounded-size harness batches as serial
        HTTP requests while preserving output ordering.
        """
        return [self._generate_one(item, index) for index, item in enumerate(items)]

    def _generate_one(self, item: dict[str, Any], index: int) -> str:
        payload = self._build_payload(item)
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            self.config.chat_completions_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise LMStudioBackendError(
                f"LM Studio request {index} failed with HTTP {exc.code}: {detail}"
            ) from exc
        except URLError as exc:
            raise LMStudioBackendError(
                f"LM Studio request {index} failed: {exc.reason}"
            ) from exc
        except TimeoutError as exc:
            raise LMStudioBackendError(
                f"LM Studio request {index} timed out after "
                f"{self.config.timeout_seconds:g}s"
            ) from exc

        return self._extract_message_content(response_body, index)

    def _build_payload(self, item: dict[str, Any]) -> dict[str, Any]:
        system_prompt = str(item["system_prompt"])
        user_text = str(item["user_text"])
        image = item["image"]
        if not isinstance(image, Image.Image):
            raise TypeError("LMStudioJudge item['image'] must be a PIL.Image.Image")

        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": self._build_user_content(user_text, image),
                },
            ],
            "temperature": self.config.temperature,
            "top_k": self.config.top_k,
            "top_p": self.config.top_p,
            "repeat_penalty": self.config.repeat_penalty,
            "max_tokens": self.config.max_new_tokens,
            "stream": False,
        }

        if self.config.seed is not None:
            payload["seed"] = self.config.seed
        if self.config.extra_body:
            payload.update(self.config.extra_body)

        return payload

    def _build_user_content(
        self,
        user_text: str,
        image: Image.Image,
    ) -> list[dict[str, Any]]:
        """Place the image where Qwen's prompt template emits ``<image>``.

        Qwen's upstream prompt puts the image before the evaluation dimension and
        checklist. Preserving that order keeps the LM Studio request faithful to
        the original harness and allows repeated passes for one image to share the
        longest possible prompt prefix. If a custom prompt omits the marker, the
        image is appended after the text as a compatibility fallback.
        """
        image_part: dict[str, Any] = {
            "type": "image_url",
            "image_url": {
                "url": self._encode_image_url(image),
            },
        }

        if self.IMAGE_MARKER not in user_text:
            return [
                {"type": "text", "text": user_text},
                image_part,
            ]

        before_image, after_image = user_text.split(self.IMAGE_MARKER, 1)
        content: list[dict[str, Any]] = []
        if before_image:
            content.append({"type": "text", "text": before_image})
        content.append(image_part)
        if after_image:
            content.append({"type": "text", "text": after_image})
        return content

    def _encode_image_url(self, image: Image.Image) -> str:
        buf = io.BytesIO()
        image.save(buf, format=self.config.image_format)
        encoded = base64.b64encode(buf.getvalue()).decode("ascii")
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

    @staticmethod
    def _extract_message_content(response_body: str, index: int) -> str:
        try:
            data = json.loads(response_body)
            choices = data["choices"]
            message = choices[0]["message"]
            content = message["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise LMStudioBackendError(
                f"LM Studio request {index} returned an unexpected response shape: "
                f"{response_body[:500]}"
            ) from exc

        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    parts.append(part["text"])
            if parts:
                return "".join(parts)

        raise LMStudioBackendError(
            f"LM Studio request {index} returned non-text message content: {content!r}"
        )
