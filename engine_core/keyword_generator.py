from __future__ import annotations

"""SEO Keyword Generator — AI-Powered Keyword Extraction

Uses the configured Gemini/OpenAI model to analyze the book's:
  - Title + subtitle
  - Chapter titles (from TOC)
  - Book description / proposal

Outputs:
  - 7 primary Google Books keywords (Google Play Books limit)
  - BISAC code recommendation
  - THEMA code recommendation
  - Search-optimized description (≤ 2000 chars)
  - Long-tail keyword suggestions
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .common import ensure_dir, now_iso, read_json, read_text, write_json
from .metadata_engine import (
    BISAC_CATEGORIES,
    BISAC_CODES,
    THEMA_CATEGORIES,
    THEMA_CODES,
    load_book_metadata,
    save_book_metadata,
)

# ---------------------------------------------------------------------------
# Prompt Templates
# ---------------------------------------------------------------------------

KEYWORD_SYSTEM_PROMPT = """당신은 구글 북스(Google Play Books) SEO 전문가입니다.
주어진 도서 정보를 분석하여 검색 최적화 키워드와 메타데이터를 생성합니다.
반드시 유효한 JSON만 반환하세요. 마크다운 코드 블록 없이 순수 JSON만 출력합니다."""

KEYWORD_USER_PROMPT = """다음 도서 정보를 분석하여 SEO 메타데이터를 생성하세요.

## 도서 정보
제목: {title}
부제: {subtitle}
저자: {author}
챕터 목록:
{chapter_list}

## 요청 사항
1. Google Play Books 키워드 (정확히 7개, 한국어 또는 영어 혼용 가능)
2. 추천 BISAC 코드 (아래 목록 중 1개 선택)
3. 추천 THEMA 코드 (아래 목록 중 1개 선택)
4. SEO 최적화 도서 설명 (2000자 이내, 자연스러운 한국어, 핵심 키워드 포함)
5. 롱테일 키워드 추가 5개

## BISAC 코드 목록
{bisac_list}

## THEMA 코드 목록
{thema_list}

## 출력 형식 (순수 JSON)
{{
  "keywords": ["키워드1", "키워드2", "키워드3", "키워드4", "키워드5", "키워드6", "키워드7"],
  "bisac_code": "COM004000",
  "thema_code": "UYQ",
  "description": "SEO 최적화된 도서 설명 (2000자 이내)",
  "longtail_keywords": ["롱테일1", "롱테일2", "롱테일3", "롱테일4", "롱테일5"],
  "reasoning": "선택 이유 간단 설명"
}}"""

# ---------------------------------------------------------------------------
# Chapter List Extractor
# ---------------------------------------------------------------------------

def _extract_chapter_list(book_root: Path) -> str:
    """Extract chapter titles from book structure."""
    chapters_dir = book_root / "chapters"
    if not chapters_dir.exists():
        return "챕터 정보 없음"

    titles: list[str] = []
    for ch_dir in sorted(chapters_dir.iterdir()):
        if not ch_dir.is_dir():
            continue
        # Try to read chapter title from draft or plan files
        for fname in ("draft5.md", "draft4.md", "draft3.md", "chapter_plan.md"):
            fpath = ch_dir / fname
            if fpath.exists():
                text = read_text(fpath)
                match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
                if match:
                    titles.append(f"- {ch_dir.name}: {match.group(1).strip()}")
                    break
        else:
            titles.append(f"- {ch_dir.name}")

    return "\n".join(titles) if titles else "챕터 정보 없음"


def _extract_proposal_summary(book_root: Path, max_chars: int = 500) -> str:
    """Extract summary from book proposal/blueprint."""
    for fname in ("book_blueprint.json", "proposal.md", "book_proposal.md"):
        path = book_root / fname
        if not path.exists():
            path = book_root / "publication" / fname
        if path.exists():
            if fname.endswith(".json"):
                try:
                    data = read_json(path)
                    return str(data.get("summary", data.get("description", "")))[:max_chars]
                except Exception:
                    pass
            else:
                text = read_text(path)
                return text[:max_chars]
    return ""


# ---------------------------------------------------------------------------
# AI Keyword Generation
# ---------------------------------------------------------------------------

async def generate_keywords_async(book_id: str, book_root: Path) -> dict[str, Any]:
    """Call AI model to generate SEO keywords. Returns keyword data."""
    try:
        from .model_gateway import call_model_async
    except ImportError:
        return _generate_keywords_fallback(book_id, book_root)

    metadata = load_book_metadata(book_id)
    chapter_list = _extract_chapter_list(book_root)

    bisac_list = "\n".join(f"  {code}: {label}" for code, label in list(BISAC_CODES.items())[:10])
    thema_list = "\n".join(f"  {code}: {label}" for code, label in list(THEMA_CODES.items())[:8])

    user_prompt = KEYWORD_USER_PROMPT.format(
        title=metadata.get("title", book_id),
        subtitle=metadata.get("subtitle", ""),
        author=metadata.get("author", ""),
        chapter_list=chapter_list,
        bisac_list=bisac_list,
        thema_list=thema_list,
    )

    try:
        raw = await call_model_async(
            system=KEYWORD_SYSTEM_PROMPT,
            user=user_prompt,
            model_role="structured",
            max_tokens=1500,
        )
        result = _parse_keyword_response(raw)
    except Exception as e:
        result = _generate_keywords_fallback(book_id, book_root)
        result["error"] = str(e)

    result["generated_at"] = now_iso()
    result["book_id"] = book_id
    _save_keywords(book_id, result)
    return result


def generate_keywords_sync(book_id: str, book_root: Path) -> dict[str, Any]:
    """Synchronous wrapper — uses fallback heuristic if AI unavailable."""
    try:
        import asyncio
        loop = asyncio.new_event_loop()
        return loop.run_until_complete(generate_keywords_async(book_id, book_root))
    except Exception:
        return _generate_keywords_fallback(book_id, book_root)


def _parse_keyword_response(raw: str) -> dict[str, Any]:
    """Parse JSON from AI response, with fallback."""
    # Strip markdown code fences if present
    clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
    try:
        data = json.loads(clean)
        return {
            "keywords": data.get("keywords", [])[:7],
            "bisac_code": data.get("bisac_code", "COM004000"),
            "thema_code": data.get("thema_code", "UYQ"),
            "description": data.get("description", ""),
            "longtail_keywords": data.get("longtail_keywords", []),
            "reasoning": data.get("reasoning", ""),
            "source": "ai",
        }
    except json.JSONDecodeError:
        return {"keywords": [], "source": "parse_error", "raw": raw[:500]}


def _generate_keywords_fallback(book_id: str, book_root: Path) -> dict[str, Any]:
    """Heuristic fallback when AI is not available."""
    metadata = load_book_metadata(book_id)
    title = metadata.get("title", book_id)

    # Extract words from title as base keywords
    words = [w for w in re.split(r"[\s\-·/]+", title) if len(w) >= 2][:4]

    default_keywords = [
        *words,
        "AI 도서",
        "자동 집필",
        "파이프라인",
    ][:7]

    return {
        "keywords": default_keywords,
        "bisac_code": "COM004000",
        "thema_code": "UYQ",
        "description": f"{title}. {metadata.get('description', '')}",
        "longtail_keywords": [],
        "reasoning": "휴리스틱 기반 자동 생성 (AI 미사용)",
        "source": "fallback",
        "generated_at": now_iso(),
        "book_id": book_id,
    }


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

APPDATA_ROOT = Path.home() / "AppData" / "Roaming" / "BookEngine"


def _keywords_path(book_id: str) -> Path:
    return APPDATA_ROOT / "books" / book_id / "keywords.json"


def _save_keywords(book_id: str, data: dict[str, Any]) -> None:
    path = _keywords_path(book_id)
    ensure_dir(path.parent)
    write_json(path, data)


def load_keywords(book_id: str) -> dict[str, Any] | None:
    path = _keywords_path(book_id)
    if path.exists():
        return read_json(path)
    return None


def save_keywords_manual(book_id: str, keywords: list[str], longtail: list[str] | None = None) -> dict[str, Any]:
    """Save manually edited keywords."""
    existing = load_keywords(book_id) or {}
    data = {
        **existing,
        "keywords": keywords[:7],
        "longtail_keywords": longtail or existing.get("longtail_keywords", []),
        "book_id": book_id,
        "updated_at": now_iso(),
        "source": "manual",
    }
    _save_keywords(book_id, data)

    # Also update metadata
    meta = load_book_metadata(book_id)
    meta["keywords"] = keywords[:7]
    save_book_metadata(book_id, meta)

    return data


def merge_keywords_to_metadata(book_id: str) -> dict[str, Any]:
    """Merge generated keywords into book metadata and return updated metadata."""
    kw_data = load_keywords(book_id)
    if not kw_data:
        return load_book_metadata(book_id)

    meta = load_book_metadata(book_id)
    meta["keywords"] = kw_data.get("keywords", [])

    if kw_data.get("bisac_code"):
        meta["bisac_code"] = kw_data["bisac_code"]
    if kw_data.get("thema_code"):
        meta["thema_code"] = kw_data["thema_code"]
    if kw_data.get("description") and not meta.get("description"):
        meta["description"] = kw_data["description"]

    result = save_book_metadata(book_id, meta)
    return result["metadata"]
