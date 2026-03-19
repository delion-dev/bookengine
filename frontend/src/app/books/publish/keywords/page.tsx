"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import useSWR from "swr";
import { ChevronRight, Loader2, Sparkles, X, Plus } from "lucide-react";
import { publish } from "@/lib/api";

const MAX_KEYWORDS = 7;

function KeywordTag({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <span className="flex items-center gap-1.5 bg-[rgba(94,106,210,0.15)] border border-[rgba(94,106,210,0.25)] text-[#7C85E0] text-xs font-medium px-2.5 py-1 rounded-full">
      {label}
      <button onClick={onRemove} className="hover:text-white transition-colors">
        <X size={10} />
      </button>
    </span>
  );
}

function KeywordsPage({ book_id }: { book_id: string }) {
  const router = useRouter();
  const { data: kwData, mutate } = useSWR(`keywords-${book_id}`, () => publish.getKeywords(book_id));

  const [keywords, setKeywords] = useState<string[]>([]);
  const [longtail, setLongtail] = useState<string[]>([]);
  const [newKw, setNewKw] = useState("");
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [reasoning, setReasoning] = useState("");
  const [description, setDescription] = useState("");
  const [genSource, setGenSource] = useState("");

  useEffect(() => {
    if (kwData) {
      setKeywords(kwData.keywords ?? []);
      setLongtail(kwData.longtail_keywords ?? []);
      setReasoning(kwData.reasoning ?? "");
      setDescription(kwData.description ?? "");
      setGenSource(kwData.source ?? "");
    }
  }, [kwData]);

  async function handleGenerate() {
    setGenerating(true);
    try {
      const result = await publish.generateKeywords(book_id);
      setKeywords(result.keywords ?? []);
      setLongtail(result.longtail_keywords ?? []);
      setReasoning(result.reasoning ?? "");
      setDescription(result.description ?? "");
      setGenSource(result.source ?? "ai");
      mutate(result, false);
      setSaved(false);
    } finally {
      setGenerating(false);
    }
  }

  function addKeyword() {
    const kw = newKw.trim();
    if (!kw || keywords.includes(kw) || keywords.length >= MAX_KEYWORDS) return;
    setKeywords((prev) => [...prev, kw]);
    setNewKw("");
    setSaved(false);
  }

  async function handleSave(andNext = false) {
    setSaving(true);
    try {
      await publish.saveKeywords(book_id, keywords, longtail);
      setSaved(true);
      if (andNext) setTimeout(() => router.push(`/books/publish/export?book_id=${book_id}`), 600);
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
        <span className="text-[#EDEDEF]">SEO 키워드</span>
      </div>

      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-[#EDEDEF]">SEO 키워드</h1>
          <p className="text-[#8A8F98] text-sm mt-1">Google Books 검색 최적화를 위한 키워드를 관리합니다.</p>
        </div>
        <button
          onClick={handleGenerate}
          disabled={generating}
          className="flex items-center gap-2 bg-[rgba(94,106,210,0.15)] border border-[rgba(94,106,210,0.3)] text-[#7C85E0] px-4 py-2 rounded-xl text-sm font-medium hover:bg-[rgba(94,106,210,0.25)] transition-all disabled:opacity-60"
        >
          {generating ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
          AI 자동 생성
        </button>
      </div>

      {/* Primary keywords */}
      <div className="bg-[rgba(255,255,255,0.04)] border border-[rgba(255,255,255,0.08)] rounded-2xl p-5 space-y-4">
        <div className="flex items-center justify-between">
          <p className="text-[#EDEDEF] font-semibold text-sm">주요 키워드</p>
          <span className={`text-xs font-mono px-2 py-0.5 rounded-full ${
            keywords.length >= MAX_KEYWORDS
              ? "bg-[rgba(239,68,68,0.15)] text-red-400"
              : "bg-[rgba(255,255,255,0.06)] text-[#8A8F98]"
          }`}>
            {keywords.length}/{MAX_KEYWORDS}
          </span>
        </div>

        <div className="flex flex-wrap gap-2 min-h-[40px]">
          {keywords.map((kw) => (
            <KeywordTag
              key={kw}
              label={kw}
              onRemove={() => { setKeywords(keywords.filter((k) => k !== kw)); setSaved(false); }}
            />
          ))}
          {keywords.length === 0 && (
            <p className="text-[#4B5563] text-xs self-center">키워드가 없습니다. AI 생성 또는 직접 입력하세요.</p>
          )}
        </div>

        {keywords.length < MAX_KEYWORDS && (
          <div className="flex gap-2">
            <input
              value={newKw}
              onChange={(e) => setNewKw(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addKeyword()}
              placeholder="키워드 추가 (Enter)"
              className="flex-1 bg-[rgba(255,255,255,0.05)] border border-[rgba(255,255,255,0.08)] rounded-xl px-3 py-2 text-sm text-[#EDEDEF] placeholder-[#4B5563] focus:outline-none focus:border-[#5E6AD2] transition-all"
            />
            <button
              onClick={addKeyword}
              disabled={!newKw.trim()}
              className="flex items-center gap-1 px-3 py-2 rounded-xl bg-[#5E6AD2] text-white text-sm hover:bg-[#7C85E0] disabled:opacity-40 transition-all"
            >
              <Plus size={14} />
            </button>
          </div>
        )}
        <p className="text-[#4B5563] text-xs">Google Play Books 최대 7개 · 한국어/영어 혼용 가능</p>
      </div>

      {/* Long-tail keywords */}
      {longtail.length > 0 && (
        <div className="bg-[rgba(255,255,255,0.03)] border border-[rgba(255,255,255,0.06)] rounded-xl p-4">
          <p className="text-[#8A8F98] font-medium text-xs mb-3">롱테일 키워드 제안 (참고용)</p>
          <div className="flex flex-wrap gap-2">
            {longtail.map((kw) => (
              <span
                key={kw}
                onClick={() => {
                  if (!keywords.includes(kw) && keywords.length < MAX_KEYWORDS) {
                    setKeywords((p) => [...p, kw]);
                    setSaved(false);
                  }
                }}
                className="cursor-pointer bg-[rgba(255,255,255,0.04)] border border-[rgba(255,255,255,0.06)] text-[#8A8F98] hover:text-[#EDEDEF] hover:border-[rgba(94,106,210,0.3)] text-xs px-2.5 py-1 rounded-full transition-all"
              >
                + {kw}
              </span>
            ))}
          </div>
          <p className="text-[#4B5563] text-xs mt-2">클릭하면 주요 키워드에 추가됩니다.</p>
        </div>
      )}

      {/* AI description suggestion */}
      {description && (
        <div className="bg-[rgba(255,255,255,0.03)] border border-[rgba(255,255,255,0.06)] rounded-xl p-4">
          <p className="text-[#8A8F98] font-medium text-xs mb-2">
            AI 생성 도서 설명 제안
            {genSource === "ai" && <span className="ml-1.5 text-[10px] text-[#5E6AD2] bg-[rgba(94,106,210,0.1)] px-1.5 py-0.5 rounded">Gemini</span>}
          </p>
          <p className="text-[#8A8F98] text-xs leading-relaxed">{description}</p>
          <p className="text-[#4B5563] text-xs mt-2">메타데이터 설명으로 복사하려면 메타데이터 페이지에서 직접 입력하세요.</p>
        </div>
      )}

      {/* Reasoning */}
      {reasoning && (
        <p className="text-[#4B5563] text-xs">AI 선택 이유: {reasoning}</p>
      )}

      {/* Actions */}
      <div className="flex items-center justify-between pt-2">
        <Link href={`/books/publish/metadata?book_id=${book_id}`} className="text-sm text-[#8A8F98] hover:text-[#EDEDEF] transition-colors">← 메타데이터</Link>
        <div className="flex gap-3">
          <button
            onClick={() => handleSave(false)}
            disabled={saving}
            className="px-4 py-2 rounded-xl border border-[rgba(255,255,255,0.1)] text-[#EDEDEF] text-sm hover:bg-[rgba(255,255,255,0.05)] transition-all disabled:opacity-50"
          >
            저장
          </button>
          <button
            onClick={() => handleSave(true)}
            disabled={saving || saved}
            className="flex items-center gap-2 bg-[#5E6AD2] text-white px-5 py-2 rounded-xl font-semibold text-sm hover:bg-[#7C85E0] disabled:opacity-60 transition-all"
          >
            {saving && <Loader2 size={14} className="animate-spin" />}
            {saved ? "저장됨 ✓" : "저장하고 다음 →"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Content() {
  const params = useSearchParams();
  const book_id = params.get("book_id") ?? "";
  if (!book_id) return <p className="text-red-500 text-sm">book_id 파라미터가 없습니다.</p>;
  return <KeywordsPage book_id={book_id} />;
}

export default function KeywordsEditorPage() {
  return (
    <Suspense fallback={<p className="text-[#8A8F98] text-sm">로딩 중…</p>}>
      <Content />
    </Suspense>
  );
}
