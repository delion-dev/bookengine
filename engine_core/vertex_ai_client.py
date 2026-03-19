"""
vertex_ai_client.py
역할: AIClient 프로토콜을 Vertex REST 기반으로 구현하는 어댑터.

이 구현은 Core Engine의 model_gateway만 호출하며, 직접 REST 세부사항을 노출하지 않는다.
"""

from __future__ import annotations

import json
from typing import Any

from .ai_client import AIClient
from .model_gateway import generate_structured, generate_text, route_provider


def _messages_to_prompt(messages: list[dict]) -> str:
    blocks: list[str] = []
    for item in messages:
        role = item.get("role", "user")
        content = item.get("content", "")
        if isinstance(content, list):
            joined_parts = []
            for part in content:
                if isinstance(part, dict):
                    text = part.get("text")
                    if text:
                        joined_parts.append(text)
                elif isinstance(part, str):
                    joined_parts.append(part)
            content_text = "\n".join(joined_parts).strip()
        else:
            content_text = str(content).strip()
        if not content_text:
            continue
        blocks.append(f"[{role}]\n{content_text}")
    return "\n\n".join(blocks).strip()


class VertexAIClient(AIClient):
    """Vertex REST 기반 AIClient 구현."""

    def generate(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 8192,
        response_json: bool = False,
    ) -> str:
        prompt = _messages_to_prompt(messages)
        generation_config = {"maxOutputTokens": max_tokens}
        if response_json:
            schema = {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                },
                "required": ["content"],
                "additionalProperties": False,
            }
            response = generate_structured(
                route_provider("generate_structured"),
                schema_id="vertex_ai_client.generate@1.0",
                response_schema=schema,
                prompt=prompt,
                system_policy_ref=system,
                context_artifacts=None,
                generation_config=generation_config,
            )
            return json.dumps(response["structured_payload"], ensure_ascii=False)

        response = generate_text(
            route_provider("generate_text"),
            system_policy_ref=system,
            prompt=prompt,
            context_artifacts=None,
            generation_config=generation_config,
        )
        return response["generated_text"]

    def generate_with_thinking(
        self,
        system: str,
        user_content: str,
        thinking_budget: int = 8000,
        max_tokens: int = 16000,
    ) -> str:
        augmented_system = "\n".join(
            [
                system.strip(),
                "",
                "Reason carefully before answering.",
                f"Thinking budget hint: {thinking_budget}.",
                "If the backend does not support explicit thinking controls, emulate the behavior internally and return only the final answer.",
            ]
        ).strip()
        response = generate_text(
            route_provider("generate_text"),
            system_policy_ref=augmented_system,
            prompt=user_content,
            context_artifacts=None,
            generation_config={"maxOutputTokens": max_tokens},
        )
        return response["generated_text"]
