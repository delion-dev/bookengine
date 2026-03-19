"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import useSWR from "swr";
import { Check, ChevronRight, Loader2 } from "lucide-react";
import { publish } from "@/lib/api";
import type { StyleGuide } from "@/lib/api";

function StyleGuideCard({
  guide,
  selected,
  onSelect,
}: {
  guide: StyleGuide;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      onClick={onSelect}
      className={`w-full text-left rounded-2xl border p-5 transition-all duration-200 ${
        selected
          ? "border-[#5E6AD2] bg-[rgba(94,106,210,0.1)] shadow-[0_0_0_1px_rgba(94,106,210,0.3)]"
          : "border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.04)] hover:border-[rgba(94,106,210,0.3)] hover:bg-[rgba(255,255,255,0.07)]"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1.5">
            <span className="text-[#EDEDEF] font-semibold text-sm">{guide.name}</span>
            {selected && (
              <span className="flex items-center gap-1 text-[10px] font-semibold text-[#5E6AD2] bg-[rgba(94,106,210,0.15)] px-2 py-0.5 rounded-full">
                <Check size={10} /> 선택됨
              </span>
            )}
          </div>
          <p className="text-[#8A8F98] text-xs leading-relaxed">{guide.description}</p>
          <p className="text-[#4B5563] text-xs mt-2">대상: {guide.target}</p>
        </div>
        <span className="flex-shrink-0 font-mono text-[10px] text-[#4B5563] bg-[rgba(255,255,255,0.04)] px-2 py-1 rounded-lg border border-[rgba(255,255,255,0.06)]">
          {guide.id}
        </span>
      </div>
    </button>
  );
}

function StyleGuidePage({ book_id }: { book_id: string }) {
  const router = useRouter();
  const { data: catalog } = useSWR("style-guides", () => publish.listStyleGuides());
  const { data: current } = useSWR(`style-guide-${book_id}`, () => publish.getStyleGuide(book_id));

  const [selectedId, setSelectedId] = useState<string>("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const resolvedId = selectedId || current?.id || "GBOOK-TECH";

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      await publish.saveStyleGuide(book_id, resolvedId);
      setSaved(true);
      setTimeout(() => router.push(`/books/publish/metadata?book_id=${book_id}`), 800);
    } catch (e) {
      setError(e instanceof Error ? e.message : "저장 실패");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-xs text-[#8A8F98]">
        <Link href={`/books/publish?book_id=${book_id}`} className="hover:text-[#EDEDEF] transition-colors">출판 허브</Link>
        <ChevronRight size={12} />
        <span className="text-[#EDEDEF]">스타일 가이드</span>
      </div>

      <div>
        <h1 className="text-xl font-bold text-[#EDEDEF]">스타일 가이드 선택</h1>
        <p className="text-[#8A8F98] text-sm mt-1">Google Books 기술 규격에 맞는 EPUB 레이아웃 템플릿을 선택합니다.</p>
      </div>

      {error && (
        <div className="bg-[rgba(239,68,68,0.1)] border border-[rgba(239,68,68,0.2)] rounded-xl p-3 text-red-400 text-sm">{error}</div>
      )}

      {/* Guide cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {catalog?.style_guides.map((g) => (
          <StyleGuideCard
            key={g.id}
            guide={g}
            selected={resolvedId === g.id}
            onSelect={() => { setSelectedId(g.id); setSaved(false); }}
          />
        ))}
      </div>

      {/* Google Books compliance note */}
      <div className="bg-[rgba(255,255,255,0.03)] border border-[rgba(255,255,255,0.06)] rounded-xl p-4 text-xs text-[#8A8F98] space-y-1">
        <p className="text-[#EDEDEF] font-medium mb-1.5">Google Books 기술 규격</p>
        <p>• EPUB 3.x 포맷 · NCX + Navigation Document 모두 포함</p>
        <p>• 커버 이미지 최소 1600×2560px · JPEG/PNG · 300 DPI</p>
        <p>• 챕터당 파일 크기 50MB 이하 · 폰트 임베딩 필수</p>
      </div>

      {/* Action */}
      <div className="flex items-center justify-between pt-2">
        <Link
          href={`/books/publish?book_id=${book_id}`}
          className="text-sm text-[#8A8F98] hover:text-[#EDEDEF] transition-colors"
        >
          ← 출판 허브
        </Link>
        <button
          onClick={handleSave}
          disabled={saving || saved}
          className="flex items-center gap-2 bg-[#5E6AD2] text-white px-5 py-2.5 rounded-xl font-semibold text-sm hover:bg-[#7C85E0] disabled:opacity-60 transition-all"
        >
          {saving && <Loader2 size={14} className="animate-spin" />}
          {saved ? "저장됨 ✓" : "저장하고 다음 →"}
        </button>
      </div>
    </div>
  );
}

function Content() {
  const params = useSearchParams();
  const book_id = params.get("book_id") ?? "";
  if (!book_id) return <p className="text-red-500 text-sm">book_id 파라미터가 없습니다.</p>;
  return <StyleGuidePage book_id={book_id} />;
}

export default function StyleGuideSelectorPage() {
  return (
    <Suspense fallback={<p className="text-[#8A8F98] text-sm">로딩 중…</p>}>
      <Content />
    </Suspense>
  );
}
