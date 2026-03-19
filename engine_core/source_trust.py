from __future__ import annotations

import re
from urllib import parse


LOW_TRUST_HOST_PATTERNS = (
    "namu.wiki",
    "bunjang.co.kr",
    "brunch.co.kr",
    "instagram.com",
    "tiktok.com",
    "youtube.com",
    "youtu.be",
    "x.com",
    "twitter.com",
    "blog.naver.com",
    "cafe.naver.com",
    "dcinside.com",
    "reddit.com",
)

SOCIAL_OR_UGC_HOST_PATTERNS = (
    "brunch.co.kr",
    "instagram.com",
    "tiktok.com",
    "youtube.com",
    "youtu.be",
    "x.com",
    "twitter.com",
    "blog.naver.com",
    "cafe.naver.com",
    "reddit.com",
)

PROXY_HOST_PATTERNS = (
    "vertexaisearch.cloud.google.com",
)

SOURCE_ALIAS_HOSTS = {
    "브런치": "brunch.co.kr",
    "브런치 리뷰": "brunch.co.kr",
    "나무위키": "namu.wiki",
    "인스타그램": "instagram.com",
    "유튜브": "youtube.com",
    "트위터": "x.com",
    "엑스": "x.com",
    "뉴스1": "news1.kr",
    "미디어펜": "mediapen.com",
    "문화일보": "munhwa.com",
}

HOST_TOKEN_PATTERN = re.compile(r"(?<!@)\b(?:https?://)?(?:www\.)?([a-z0-9.-]+\.[a-z]{2,})(?:/|\b)")

OFFICIAL_SOURCE_TYPES = {
    "official_source",
    "official_film_info",
    "official_tourism",
    "official_local_info",
    "primary_history_source",
    "scholarly_reference",
}

NEWSLIKE_SOURCE_TYPES = {
    "news",
    "recent_news",
    "critic_review",
    "news_explainer",
}

SUPPLEMENTAL_ONLY_SOURCE_TYPES = {
    "social_trend",
    "recent_review",
    "recent_ugc",
}

STRICT_REFERENCE_TYPES = {
    "official_source",
    "official_film_info",
    "official_tourism",
    "official_local_info",
    "primary_history_source",
    "scholarly_reference",
}


def _normalized_host(url_or_identifier: str | None) -> str:
    if not url_or_identifier:
        return ""
    parsed = parse.urlparse(url_or_identifier)
    host = (parsed.netloc or "").lower().strip()
    if not host and (url_or_identifier.startswith("http://") or url_or_identifier.startswith("https://")):
        host = (parsed.path or "").lower().strip()
    if host.startswith("www."):
        host = host[4:]
    return host


def _matches_host_pattern(host: str, patterns: tuple[str, ...]) -> bool:
    return any(host == pattern or host.endswith(f".{pattern}") for pattern in patterns)


def _extract_host_token(text: str | None) -> str:
    if not text:
        return ""
    match = HOST_TOKEN_PATTERN.search(text.lower())
    if not match:
        return ""
    host = match.group(1).strip(".")
    if host.startswith("www."):
        host = host[4:]
    return host


def _alias_host(text: str | None) -> str:
    if not text:
        return ""
    normalized = text.strip().lower()
    for alias, host in SOURCE_ALIAS_HOSTS.items():
        if alias.lower() in normalized:
            return host
    return ""


def _resolve_reference_host(source: dict) -> str:
    candidates: list[str] = []
    direct_host = _normalized_host(source.get("url_or_identifier"))
    if direct_host:
        candidates.append(direct_host)

    for field in ("source_name", "title", "url_or_identifier"):
        value = source.get(field)
        alias_host = _alias_host(value)
        if alias_host:
            candidates.append(alias_host)
        token_host = _extract_host_token(value)
        if token_host:
            candidates.append(token_host)

    seen: set[str] = set()
    deduped = []
    for host in candidates:
        if not host or host in seen:
            continue
        seen.add(host)
        deduped.append(host)

    for host in deduped:
        if not _matches_host_pattern(host, PROXY_HOST_PATTERNS):
            return host
    return deduped[0] if deduped else ""


def assess_source_trust(source: dict) -> dict:
    source_copy = dict(source)
    host = _resolve_reference_host(source)
    source_type = source.get("source_type_hint") or source.get("source_type") or ""

    trust_level = "medium"
    trust_reason = "general_web_source"
    primary_eligible = True

    if not host:
        trust_level = "low"
        trust_reason = "missing_host_or_url"
        primary_eligible = False
    elif _matches_host_pattern(host, LOW_TRUST_HOST_PATTERNS):
        trust_level = "low"
        trust_reason = "ugc_marketplace_or_wiki"
        primary_eligible = False
    elif host.endswith(".go.kr") or host.endswith(".gov") or host.endswith(".ac.kr") or host.endswith(".edu"):
        trust_level = "high"
        trust_reason = "official_or_institutional_domain"
        primary_eligible = True
    elif source_type in OFFICIAL_SOURCE_TYPES:
        trust_level = "high"
        trust_reason = "official_or_primary_source_type"
        primary_eligible = True
    elif source_type == "map_service":
        trust_level = "medium"
        trust_reason = "map_service_practical_reference"
        primary_eligible = True
    elif source_type in NEWSLIKE_SOURCE_TYPES:
        trust_level = "medium"
        trust_reason = "news_or_editorial_source"
        primary_eligible = True
    elif source_type in SUPPLEMENTAL_ONLY_SOURCE_TYPES:
        trust_level = "medium"
        trust_reason = "social_or_recent_signal"
        primary_eligible = not _matches_host_pattern(host, SOCIAL_OR_UGC_HOST_PATTERNS)
    elif _matches_host_pattern(host, SOCIAL_OR_UGC_HOST_PATTERNS):
        trust_level = "low"
        trust_reason = "social_or_ugc_domain"
        primary_eligible = False

    source_copy["reference_host"] = host
    source_copy["trust_level"] = trust_level
    source_copy["trust_reason"] = trust_reason
    source_copy["primary_eligible"] = primary_eligible
    return source_copy


def partition_sources_for_citation(sources: list[dict]) -> dict:
    annotated = [assess_source_trust(source) for source in sources]
    primary_sources = [source for source in annotated if source["primary_eligible"]]
    supplemental_sources = [source for source in annotated if not source["primary_eligible"]]
    trust_summary = {
        "high": sum(1 for source in annotated if source["trust_level"] == "high"),
        "medium": sum(1 for source in annotated if source["trust_level"] == "medium"),
        "low": sum(1 for source in annotated if source["trust_level"] == "low"),
        "primary_eligible": len(primary_sources),
        "supplemental_only": len(supplemental_sources),
    }
    return {
        "annotated": annotated,
        "primary_sources": primary_sources,
        "supplemental_sources": supplemental_sources,
        "trust_summary": trust_summary,
    }


def assess_reference_slot_fit(reference_entry: dict) -> dict:
    reference_type = reference_entry.get("source_type", "")
    trust_level = reference_entry.get("trust_level") or ""
    host = reference_entry.get("reference_host") or _resolve_reference_host(reference_entry)
    source_name = (reference_entry.get("source_name") or "").lower()

    if not reference_entry.get("title") or not reference_entry.get("url_or_identifier"):
        return {"slot_fit_status": "unfilled", "slot_fit_reason": "missing_reference_fields"}

    if reference_type in STRICT_REFERENCE_TYPES:
        if trust_level == "high":
            return {"slot_fit_status": "strong_fit", "slot_fit_reason": "strict_reference_backed_by_high_trust_source"}
        return {"slot_fit_status": "weak_fit", "slot_fit_reason": "strict_reference_backed_by_non_high_trust_source"}

    if reference_type == "map_service":
        if "map" in host or "map" in source_name:
            return {"slot_fit_status": "strong_fit", "slot_fit_reason": "map_service_reference_detected"}
        return {"slot_fit_status": "weak_fit", "slot_fit_reason": "map_service_slot_without_map_provider"}

    if reference_type in NEWSLIKE_SOURCE_TYPES:
        if trust_level in {"medium", "high"}:
            return {"slot_fit_status": "strong_fit", "slot_fit_reason": "newslike_slot_backed_by_editorial_source"}
        return {"slot_fit_status": "weak_fit", "slot_fit_reason": "newslike_slot_without_editorial_confidence"}

    if reference_type in SUPPLEMENTAL_ONLY_SOURCE_TYPES:
        if trust_level == "low":
            return {"slot_fit_status": "weak_fit", "slot_fit_reason": "signal_slot_backed_by_low_trust_source"}
        return {"slot_fit_status": "strong_fit", "slot_fit_reason": "signal_slot_backed_by_usable_signal_source"}

    return {"slot_fit_status": "strong_fit", "slot_fit_reason": "general_reference_slot"}
