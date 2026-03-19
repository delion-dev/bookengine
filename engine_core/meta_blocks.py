from __future__ import annotations

import re
from dataclasses import dataclass


META_BLOCK_PATTERN = re.compile(
    r'<!-- META_START\b(?P<attrs>[^>]*)id="(?P<meta_id>[^"]+)"[^>]*-->.*?<!-- META_END\b[^>]*id="(?P=meta_id)"[^>]*-->',
    re.DOTALL,
)

META_START_PATTERN = re.compile(r"<!-- META_START\b")
META_END_PATTERN = re.compile(r"<!-- META_END\b")


@dataclass(frozen=True)
class MetaBlock:
    meta_id: str
    raw: str


def render_meta_block(
    *,
    meta_id: str,
    kind: str,
    stage_id: str,
    owner: str,
    action: str,
    body: str,
) -> str:
    normalized_body = body.strip()
    return "\n".join(
        [
            f'<!-- META_START id="{meta_id}" kind="{kind}" stage="{stage_id}" owner="{owner}" action="{action}" -->',
            normalized_body,
            f'<!-- META_END id="{meta_id}" -->',
        ]
    )


def extract_meta_blocks(text: str) -> list[MetaBlock]:
    return [
        MetaBlock(meta_id=match.group("meta_id"), raw=match.group(0))
        for match in META_BLOCK_PATTERN.finditer(text)
    ]


def strip_meta_blocks(text: str) -> tuple[str, list[str]]:
    removed_ids = [block.meta_id for block in extract_meta_blocks(text)]
    cleaned = META_BLOCK_PATTERN.sub("", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip() + "\n"
    return cleaned, removed_ids


def meta_block_summary(text: str) -> dict[str, object]:
    blocks = extract_meta_blocks(text)
    return {
        "meta_block_count": len(blocks),
        "meta_block_ids": [block.meta_id for block in blocks],
        "meta_start_count": len(META_START_PATTERN.findall(text)),
        "meta_end_count": len(META_END_PATTERN.findall(text)),
    }
