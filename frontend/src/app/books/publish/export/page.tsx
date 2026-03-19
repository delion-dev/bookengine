"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";
import { ChevronRight, Download, Loader2, CheckCircle2, AlertCircle, Package } from "lucide-react";
import { publish, registry } from "@/lib/api";

function ComplianceBadge({ ok, label }: { ok: boolean | undefined; label: string }) {
  return (
    <div className={`flex items-center gap-2 text-xs px-3 py-2 rounded-lg ${
      ok ? "bg-[rgba(34,197,94,0.08)] text-[#22C55E]" : "bg-[rgba(239,68,68,0.08)] text-red-400"
    }`}>
      {ok ? <CheckCircle2 size={12} /> : <AlertCircle size={12} />}
      {label}
    </div>
  );
}

function ExportPage({ book_id }: { book_id: string }) {
  const { data: detail } = useSWR(`book-${book_id}`, () => registry.getBook(book_id));
  const { data: status, mutate } = useSWR(`export-status-${book_id}`, () => publish.exportStatus(book_id), {
    refreshInterval: 0,
  });

  const [building, setBuilding] = useState(false);
  const [buildError, setBuildError] = useState<string | null>(null);

  const bookTitle = detail?.book.display_name ?? book_id;
  const hasEpub = !!status?.epub_name;
  const compliance = status?.compliance as Record<string, unknown> | undefined;

  async function handleBuild() {
    setBuilding(true);
    setBuildError(null);
    try {
      const result = await publish.exportEpub(book_id);
      mutate(result, false);
    } catch (e) {
      setBuildError(e instanceof Error ? e.message : "EPUB 생성 실패");
    } finally {
      setBuilding(false);
    }
  }

  function handleDownload() {
    const url = `http://localhost:8000/engine/publish/export/${book_id}/download`;
    const a = document.createElement("a");
    a.href = url;
    a.download = status?.epub_name ?? "book.epub";
    a.click();
  }

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-xs text-[#8A8F98]">
        <Link href={`/books/publish?book_id=${book_id}`} className="hover:text-[#EDEDEF] transition-colors">출판 허브</Link>
        <ChevronRight size={12} />
        <span className="text-[#EDEDEF]">EPUB 생성</span>
      </div>

      <div>
        <h1 className="text-xl font-bold text-[#EDEDEF]">EPUB 패키징 및 다운로드</h1>
        <p className="text-[#8A8F98] text-sm mt-1">{bookTitle}의 최종 EPUB 3.x 파일을 생성합니다.</p>
      </div>

      {/* Build card */}
      <div className="bg-[rgba(255,255,255,0.04)] border border-[rgba(255,255,255,0.08)] rounded-2xl p-6">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-2xl bg-[rgba(94,106,210,0.15)] flex items-center justify-center flex-shrink-0">
            <Package size={24} className="text-[#5E6AD2]" />
          </div>
          <div className="flex-1">
            <h2 className="text-[#EDEDEF] font-semibold mb-1">EPUB 3.x 생성</h2>
            <ul className="text-[#8A8F98] text-xs space-y-1 mb-4">
              <li>• 챕터 마크다운 → XHTML 변환</li>
              <li>• 스타일 가이드 CSS 적용</li>
              <li>• OPF Package Document + NCX + Navigation Document 생성</li>
              <li>• EPUB 메타데이터 (ISBN/Google ID) 삽입</li>
              <li>• ZIP 패키징 (mimetype 첫 항목 · 비압축)</li>
            </ul>

            {buildError && (
              <div className="bg-[rgba(239,68,68,0.08)] border border-[rgba(239,68,68,0.2)] rounded-xl p-3 text-red-400 text-sm mb-4">
                <AlertCircle size={14} className="inline mr-1" />{buildError}
              </div>
            )}

            <button
              onClick={handleBuild}
              disabled={building}
              className="flex items-center gap-2 bg-[#5E6AD2] text-white px-5 py-2.5 rounded-xl font-semibold text-sm hover:bg-[#7C85E0] disabled:opacity-60 transition-all"
            >
              {building ? <Loader2 size={14} className="animate-spin" /> : <Package size={14} />}
              {building ? "생성 중…" : hasEpub ? "재생성" : "EPUB 생성 시작"}
            </button>
          </div>
        </div>
      </div>

      {/* Result */}
      {hasEpub && (
        <>
          {/* File info */}
          <div className="bg-[rgba(34,197,94,0.06)] border border-[rgba(34,197,94,0.2)] rounded-2xl p-5">
            <div className="flex items-center gap-3 mb-4">
              <CheckCircle2 size={18} className="text-[#22C55E]" />
              <p className="text-[#22C55E] font-semibold">EPUB 생성 완료</p>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
              {[
                { label: "파일명", value: status?.epub_name ?? "-" },
                { label: "파일 크기", value: `${status?.file_size_mb ?? 0} MB` },
                { label: "챕터 수", value: `${status?.chapter_count ?? 0}개` },
                { label: "목차 항목", value: `${status?.toc_entries ?? 0}개` },
              ].map(({ label, value }) => (
                <div key={label} className="bg-[rgba(255,255,255,0.04)] rounded-xl p-3">
                  <p className="text-[#4B5563] text-xs">{label}</p>
                  <p className="text-[#EDEDEF] font-mono text-sm mt-0.5">{value}</p>
                </div>
              ))}
            </div>
            <button
              onClick={handleDownload}
              className="flex items-center gap-2 bg-[#22C55E] text-black px-5 py-2.5 rounded-xl font-bold text-sm hover:bg-[#16a34a] transition-all"
            >
              <Download size={14} /> EPUB 다운로드
            </button>
          </div>

          {/* Compliance */}
          {compliance && (
            <div className="bg-[rgba(255,255,255,0.03)] border border-[rgba(255,255,255,0.06)] rounded-xl p-4">
              <p className="text-[#EDEDEF] font-semibold text-sm mb-3">Google Books 규격 준수 체크</p>
              <div className="flex flex-wrap gap-2">
                <ComplianceBadge ok={compliance.epub_version === "3.x"} label="EPUB 3.x" />
                <ComplianceBadge ok={!!compliance.has_nav_document} label="Navigation Document" />
                <ComplianceBadge ok={!!compliance.has_ncx} label="NCX (EPUB 2 호환)" />
                <ComplianceBadge ok={!!compliance.has_cover} label="커버 이미지" />
                <ComplianceBadge ok={!!compliance.size_ok} label={`파일 크기 (<50MB)`} />
              </div>
            </div>
          )}

          {/* Google Books upload guide */}
          <div className="bg-[rgba(255,255,255,0.03)] border border-[rgba(255,255,255,0.06)] rounded-xl p-4 text-xs text-[#8A8F98] space-y-1.5">
            <p className="text-[#EDEDEF] font-medium mb-2">Google Play Books 업로드 방법</p>
            <p>1. <a href="https://play.google.com/books/publish" target="_blank" rel="noopener noreferrer" className="text-[#5E6AD2] underline">Google Play Books Partner Center</a>에 로그인합니다.</p>
            <p>2. "책 추가" → "파일 업로드"에서 다운로드한 EPUB 파일을 선택합니다.</p>
            <p>3. 메타데이터 (ISBN, 설명, 분류)를 Partner Center에서 확인 후 제출합니다.</p>
            <p>4. 구글 심사 완료 후 Google Play Books에서 도서가 게시됩니다.</p>
          </div>
        </>
      )}

      {/* Back nav */}
      <div className="pt-2">
        <Link href={`/books/publish/keywords?book_id=${book_id}`} className="text-sm text-[#8A8F98] hover:text-[#EDEDEF] transition-colors">← SEO 키워드</Link>
      </div>
    </div>
  );
}

function Content() {
  const params = useSearchParams();
  const book_id = params.get("book_id") ?? "";
  if (!book_id) return <p className="text-red-500 text-sm">book_id 파라미터가 없습니다.</p>;
  return <ExportPage book_id={book_id} />;
}

export default function EpubExportPage() {
  return (
    <Suspense fallback={<p className="text-[#8A8F98] text-sm">로딩 중…</p>}>
      <Content />
    </Suspense>
  );
}
