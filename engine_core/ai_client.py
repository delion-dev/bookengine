"""
AIClient 프로토콜 - AI API 호출 추상 인터페이스.

SOLID 원칙:
  - DIP(Dependency Inversion): 상위 레이어는 이 인터페이스에만 의존한다.
  - ISP(Interface Segregation): 실제로 사용하는 두 메서드만 정의한다.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class AIClient(Protocol):
    """AI 텍스트 생성 클라이언트 인터페이스."""

    def generate(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 8192,
        response_json: bool = False,
    ) -> str:
        """표준 텍스트 생성. response_json=True 시 JSON 출력 강제."""
        ...

    def generate_with_thinking(
        self,
        system: str,
        user_content: str,
        thinking_budget: int = 8000,
        max_tokens: int = 16000,
    ) -> str:
        """Deep Thinking 모드 텍스트 생성. 미지원 시 일반 생성으로 폴백."""
        ...
