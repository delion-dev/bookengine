"""
llm_client.py
역할: .env 파일의 설정을 읽어 Google Gemini / Vertex AI 환경을 정규화하는 중앙 클라이언트.
Agent: AG-OM
Date: 2026-03-14
"""

from __future__ import annotations

from typing import Any

from .ai_client import AIClient
from .model_gateway import (
    describe_model_gateway,
    generate_structured,
    load_model_gateway_config,
    load_repo_env,
    route_provider,
)
from .vertex_ai_client import VertexAIClient


class LLMConfig:
    def __init__(self) -> None:
        self.env_vars = load_repo_env()
        self._gateway_config = load_model_gateway_config()
        self.api_key = self.env_vars.get("VERTEX_API_KEY") or self.env_vars.get("GEMINI_API_KEY", "")
        self.model_name = (
            self.env_vars.get("VERTEX_MODEL_TEXT")
            or self.env_vars.get("GEMINI_CONTENT_MODEL")
            or self._gateway_config.text_model
        )
        self.project_id = self.env_vars.get("VERTEX_PROJECT_ID") or self.env_vars.get("GOOGLE_CLOUD_PROJECT", "")
        self.region = (
            self.env_vars.get("VERTEX_REGION")
            or self.env_vars.get("GOOGLE_CLOUD_LOCATION")
            or self.env_vars.get("GOOGLE_CLOUD_REGION", self._gateway_config.location)
        )
        self.provider = self._gateway_config.provider
        self.auth_mode = self._gateway_config.auth_mode
        self.endpoint_mode = self._gateway_config.endpoint_mode
        self.enable_live_calls = self._gateway_config.enable_live_calls

    def describe(self) -> dict[str, Any]:
        payload = describe_model_gateway()
        payload["config"]["model_name"] = self.model_name
        return payload


class GeminiClient:
    """
    Core Engine 표준 Gemini / Vertex AI 중앙 클라이언트.

    주의:
    - 외부 호출은 항상 Model Gateway를 통해 수행한다.
    - provider 설정에 따라 Vertex REST 또는 Gemini API direct로 라우팅된다.
    """

    def __init__(self) -> None:
        self.config = LLMConfig()
        self.base_url = (
            "https://generativelanguage.googleapis.com"
            if self.config.provider == "gemini_api"
            else "https://aiplatform.googleapis.com"
        )
        self._client: AIClient = VertexAIClient()

    def generate_content(self, prompt: str, system_instruction: str | None = None) -> str:
        return self._client.generate(
            system=system_instruction or "",
            messages=[{"role": "user", "content": prompt}],
        )

    def generate_structured_content(
        self,
        *,
        prompt: str,
        response_schema: dict[str, Any],
        system_instruction: str | None = None,
        schema_id: str = "structured_payload@1.0",
    ) -> dict[str, Any]:
        response = generate_structured(
            route_provider("generate_structured"),
            schema_id=schema_id,
            response_schema=response_schema,
            prompt=prompt,
            system_policy_ref=system_instruction,
            context_artifacts=None,
        )
        return response["structured_payload"]


if __name__ == "__main__":
    client = GeminiClient()
    print("Gemini / Vertex client ready.")
    print(f" - Model: {client.config.model_name}")
    print(f" - Provider: {client.config.provider}")
    print(f" - Project: {client.config.project_id}")
    print(f" - Region: {client.config.region}")
    print(f" - Auth mode: {client.config.auth_mode}")
    print(f" - Live calls enabled: {client.config.enable_live_calls}")
