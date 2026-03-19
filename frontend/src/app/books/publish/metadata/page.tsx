"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import useSWR from "swr";
import { ChevronRight, ExternalLink, Loader2, AlertCircle } from "lucide-react";
import { publish } from "@/lib/api";
import type { EpubMetadata } from "@/lib/api";

function Field({
  label, value, onChange, required, placeholder, hint, type = "text",
}: {
  label: string; value: string; onChange: (v: string) => void;
  required?: boolean; placeholder?: string; hint?: string; type?: string;
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-[#8A8F98] mb-1.5">
        {label}{required && <span className="text-red-400 ml-0.5">*</span>}
      </label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full bg-[rgba(255,255,255,0.05)] border border-[rgba(255,255,255,0.08)] rounded-xl px-3.5 py-2.5 text-sm text-[#EDEDEF] placeholder-[#4B5563] focus:outline-none focus:border-[#5E6AD2] focus:ring-1 focus:ring-[rgba(94,106,210,0.3)] transition-all"
      />
      {hint && <p className="text-[#4B5563] text-xs mt-1">{hint}</p>}
    </div>
  );
}

function Select({
  label, value, onChange, options,
}: {
  label: string; value: string; onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-[#8A8F98] mb-1.5">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full bg-[rgba(255,255,255,0.05)] border border-[rgba(255,255,255,0.08)] rounded-xl px-3.5 py-2.5 text-sm text-[#EDEDEF] focus:outline-none focus:border-[#5E6AD2] transition-all"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value} className="bg-[#0E1223]">{o.label}</option>
        ))}
      </select>
    </div>
  );
}

const EMPTY_META: EpubMetadata = {
  title: "", subtitle: "", author: "", publisher: "Self-Published",
  publication_date: "", language: "ko", isbn13: "", google_books_id: "",
  description: "", keywords: [], bisac_code: "COM004000",
  thema_code: "UYQ", age_rating: "전체", adult_content: false,
};

function MetadataPage({ book_id }: { book_id: string }) {
  const router = useRouter();
  const { data: preview, mutate } = useSWR(`metadata-${book_id}`, () => publish.getMetadata(book_id));

  const [form, setForm] = useState<EpubMetadata>(EMPTY_META);
  const [showOPF, setShowOPF] = useState(false);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (preview?.metadata) setForm(preview.metadata);
  }, [preview]);

  function set(key: keyof EpubMetadata, value: string | boolean) {
    setForm((prev) => ({ ...prev, [key]: value }));
    setSaved(false);
  }

  async function handleSave(andNext = false) {
    setSaving(true);
    setErrors([]);
    try {
      const result = await publish.saveMetadata(book_id, form);
      if (!result.ok) {
        setErrors(result.errors);
      } else {
        setSaved(true);
        mutate();
        if (andNext) {
          setTimeout(() => router.push(`/books/publish/keywords?book_id=${book_id}`), 600);
        }
      }
    } catch (e) {
      setErrors([e instanceof Error ? e.message : "저장 실패"]);
    } finally {
      setSaving(false);
    }
  }

  const bisacOptions = preview?.bisac_categories.map((c) => ({ value: c.code, label: c.label })) ?? [];
  const themaOptions = preview?.thema_categories.map((c) => ({ value: c.code, label: c.label })) ?? [];
  const langOptions = preview?.languages.map((l) => ({ value: l.code, label: l.label })) ?? [];
  const ageOptions = (preview?.age_ratings ?? ["전체"]).map((r) => ({ value: r, label: r }));

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-xs text-[#8A8F98]">
        <Link href={`/books/publish?book_id=${book_id}`} className="hover:text-[#EDEDEF] transition-colors">출판 허브</Link>
        <ChevronRight size={12} />
        <span className="text-[#EDEDEF]">메타데이터</span>
      </div>

      <div>
        <h1 className="text-xl font-bold text-[#EDEDEF]">EPUB 메타데이터</h1>
        <p className="text-[#8A8F98] text-sm mt-1">Google Books 등록을 위한 도서 정보를 입력합니다.</p>
      </div>

      {/* Errors */}
      {errors.length > 0 && (
        <div className="bg-[rgba(239,68,68,0.08)] border border-[rgba(239,68,68,0.2)] rounded-xl p-4 space-y-1">
          {errors.map((e, i) => (
            <div key={i} className="flex items-center gap-2 text-red-400 text-sm">
              <AlertCircle size={14} /> {e}
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Field label="제목" value={form.title} onChange={(v) => set("title", v)} required placeholder="BookEngine — AI 도서 자동 집필 파이프라인" />
        <Field label="부제" value={form.subtitle} onChange={(v) => set("subtitle", v)} placeholder="Multi-Agent Orchestration 실전 가이드" />
        <Field label="저자" value={form.author} onChange={(v) => set("author", v)} required placeholder="홍길동" />
        <Field label="출판사" value={form.publisher} onChange={(v) => set("publisher", v)} placeholder="Self-Published" />
        <Field label="출판일" value={form.publication_date} onChange={(v) => set("publication_date", v)} type="date" placeholder="2026-06-01" />
        <Select label="언어" value={form.language} onChange={(v) => set("language", v)} options={langOptions.length ? langOptions : [{ value: "ko", label: "한국어" }]} />
      </div>

      {/* Identifiers */}
      <div className="bg-[rgba(255,255,255,0.03)] border border-[rgba(255,255,255,0.06)] rounded-xl p-4 space-y-4">
        <p className="text-[#EDEDEF] font-semibold text-sm">도서 식별자</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Field
            label="ISBN-13"
            value={form.isbn13}
            onChange={(v) => set("isbn13", v)}
            placeholder="978-XXXXXXXXXX"
            hint="하이픈 포함 또는 미포함 모두 가능"
          />
          <div>
            <label className="block text-xs font-medium text-[#8A8F98] mb-1.5">
              Google Books Partner ID
              <a href="https://play.google.com/books/publish" target="_blank" rel="noopener noreferrer"
                className="inline-flex items-center gap-0.5 text-[#5E6AD2] ml-1.5 text-xs">
                Partners 페이지 <ExternalLink size={10} />
              </a>
            </label>
            <input
              type="text"
              value={form.google_books_id}
              onChange={(e) => set("google_books_id", e.target.value)}
              placeholder="partner-XXXXXXXX"
              className="w-full bg-[rgba(255,255,255,0.05)] border border-[rgba(255,255,255,0.08)] rounded-xl px-3.5 py-2.5 text-sm text-[#EDEDEF] placeholder-[#4B5563] focus:outline-none focus:border-[#5E6AD2] focus:ring-1 focus:ring-[rgba(94,106,210,0.3)] transition-all"
            />
          </div>
        </div>
      </div>

      {/* Description */}
      <div>
        <label className="block text-xs font-medium text-[#8A8F98] mb-1.5">
          도서 설명 <span className="text-[#4B5563]">(Google Books 검색 노출용 · 2000자 이내)</span>
        </label>
        <textarea
          value={form.description}
          onChange={(e) => set("description", e.target.value)}
          rows={5}
          maxLength={2000}
          placeholder="도서의 핵심 내용과 독자 대상을 설명하세요. SEO 키워드 자동 삽입 가능합니다."
          className="w-full bg-[rgba(255,255,255,0.05)] border border-[rgba(255,255,255,0.08)] rounded-xl px-3.5 py-2.5 text-sm text-[#EDEDEF] placeholder-[#4B5563] focus:outline-none focus:border-[#5E6AD2] resize-none transition-all"
        />
        <p className="text-[#4B5563] text-xs mt-1 text-right">{form.description.length}/2000</p>
      </div>

      {/* Categories */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Select label="BISAC 분류" value={form.bisac_code} onChange={(v) => set("bisac_code", v)} options={bisacOptions} />
        <Select label="THEMA 분류" value={form.thema_code} onChange={(v) => set("thema_code", v)} options={themaOptions} />
        <Select label="연령 등급" value={form.age_rating} onChange={(v) => set("age_rating", v)} options={ageOptions} />
      </div>

      {/* OPF preview toggle */}
      <div>
        <button
          onClick={() => setShowOPF(!showOPF)}
          className="text-xs text-[#5E6AD2] hover:text-[#7C85E0] transition-colors"
        >
          {showOPF ? "▼ OPF XML 숨기기" : "▶ OPF XML 미리보기"}
        </button>
        {showOPF && preview?.opf_xml && (
          <pre className="mt-2 bg-[#0E1223] border border-[rgba(255,255,255,0.06)] rounded-xl p-4 text-xs text-[#8A8F98] overflow-x-auto font-mono leading-relaxed">
            {preview.opf_xml}
          </pre>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center justify-between pt-2">
        <Link href={`/books/publish/style-guide?book_id=${book_id}`} className="text-sm text-[#8A8F98] hover:text-[#EDEDEF] transition-colors">← 스타일 가이드</Link>
        <div className="flex gap-3">
          <button
            onClick={() => handleSave(false)}
            disabled={saving}
            className="px-4 py-2 rounded-xl border border-[rgba(255,255,255,0.1)] text-[#EDEDEF] text-sm hover:bg-[rgba(255,255,255,0.05)] transition-all disabled:opacity-50"
          >
            {saving ? <Loader2 size={14} className="animate-spin inline mr-1" /> : null}
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
  return <MetadataPage book_id={book_id} />;
}

export default function MetadataEditorPage() {
  return (
    <Suspense fallback={<p className="text-[#8A8F98] text-sm">로딩 중…</p>}>
      <Content />
    </Suspense>
  );
}
