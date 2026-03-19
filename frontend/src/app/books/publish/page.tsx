"use client";

import { Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";
import { BookOpen, FileText, Hash, Download, ChevronRight } from "lucide-react";
import { publish, registry } from "@/lib/api";

const STEPS = [
  {
    id: "style-guide",
    label: "스타일 가이드",
    desc: "Google Books 출판 템플릿 선택",
    icon: BookOpen,
    href: (bid: string) => `/books/publish/style-guide?book_id=${bid}`,
  },
  {
    id: "metadata",
    label: "메타데이터",
    desc: "EPUB ISBN / 출판 정보 입력",
    icon: FileText,
    href: (bid: string) => `/books/publish/metadata?book_id=${bid}`,
  },
  {
    id: "keywords",
    label: "SEO 키워드",
    desc: "AI 자동 생성 + 편집",
    icon: Hash,
    href: (bid: string) => `/books/publish/keywords?book_id=${bid}`,
  },
  {
    id: "export",
    label: "EPUB 생성",
    desc: "최종 EPUB 패키징 및 다운로드",
    icon: Download,
    href: (bid: string) => `/books/publish/export?book_id=${bid}`,
  },
];

function PublishHub({ book_id }: { book_id: string }) {
  const { data: detail } = useSWR(`book-${book_id}`, () => registry.getBook(book_id));
  const { data: exportStatus } = useSWR(`export-status-${book_id}`, () => publish.exportStatus(book_id));

  const bookTitle = detail?.book.display_name ?? book_id;

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <div className="flex items-center gap-3 text-sm">
        <Link href="/" className="text-[#8A8F98] hover:text-[#EDEDEF] transition-colors">대시보드</Link>
        <ChevronRight size={14} className="text-[#4B5563]" />
        <Link href={`/books/detail?book_id=${book_id}`} className="text-[#8A8F98] hover:text-[#EDEDEF] transition-colors">
          {bookTitle}
        </Link>
        <ChevronRight size={14} className="text-[#4B5563]" />
        <span className="text-[#EDEDEF] font-medium">출판</span>
      </div>

      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-[#EDEDEF]">Google Books 출판</h1>
        <p className="text-[#8A8F98] text-sm mt-1">스타일 가이드 적용 → 메타데이터 → SEO 키워드 → EPUB 생성</p>
      </div>

      {/* Export status banner */}
      {exportStatus?.epub_name && (
        <div className="bg-[rgba(34,197,94,0.08)] border border-[rgba(34,197,94,0.2)] rounded-2xl p-4 flex items-center justify-between">
          <div>
            <p className="text-[#22C55E] font-semibold text-sm">EPUB 생성 완료</p>
            <p className="text-[#8A8F98] text-xs mt-0.5">{exportStatus.epub_name} · {exportStatus.file_size_mb}MB · {exportStatus.chapter_count}챕터</p>
          </div>
          <Link
            href={`/books/publish/export?book_id=${book_id}`}
            className="text-xs px-3 py-1.5 rounded-lg bg-[#22C55E] text-black font-semibold hover:bg-[#16a34a] transition-colors"
          >
            다운로드
          </Link>
        </div>
      )}

      {/* Steps grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {STEPS.map((step, idx) => {
          const Icon = step.icon;
          return (
            <Link
              key={step.id}
              href={step.href(book_id)}
              className="group bg-[rgba(255,255,255,0.05)] backdrop-blur-xl border border-[rgba(255,255,255,0.08)] rounded-2xl p-6 flex items-start gap-4 hover:border-[rgba(94,106,210,0.4)] hover:-translate-y-0.5 transition-all duration-200"
            >
              <div className="flex-shrink-0 w-10 h-10 rounded-xl bg-[rgba(94,106,210,0.15)] flex items-center justify-center">
                <Icon size={20} className="text-[#5E6AD2]" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-[#4B5563] text-xs font-mono">Step {idx + 1}</span>
                </div>
                <p className="text-[#EDEDEF] font-semibold text-sm">{step.label}</p>
                <p className="text-[#8A8F98] text-xs mt-0.5">{step.desc}</p>
              </div>
              <ChevronRight size={16} className="text-[#4B5563] group-hover:text-[#5E6AD2] transition-colors mt-1" />
            </Link>
          );
        })}
      </div>

      {/* Google Books info */}
      <div className="bg-[rgba(255,255,255,0.03)] border border-[rgba(255,255,255,0.06)] rounded-2xl p-5">
        <h3 className="text-[#EDEDEF] font-semibold text-sm mb-3">Google Books Partner 안내</h3>
        <ul className="space-y-1.5 text-[#8A8F98] text-xs">
          <li>• <a href="https://play.google.com/books/publish" target="_blank" rel="noopener noreferrer" className="text-[#5E6AD2] underline">Google Play Books Partner Center</a>에서 도서 등록 후 식별자를 받으세요.</li>
          <li>• EPUB 생성 전 ISBN-13 또는 Google Books ID를 메타데이터에 입력하면 자동 삽입됩니다.</li>
          <li>• 커버 이미지 권장 사양: 1600×2560px, JPEG, 300 DPI 이상.</li>
        </ul>
      </div>
    </div>
  );
}

function PublishHubContent() {
  const params = useSearchParams();
  const book_id = params.get("book_id") ?? "";
  if (!book_id) return <p className="text-red-500 text-sm">book_id 파라미터가 없습니다.</p>;
  return <PublishHub book_id={book_id} />;
}

export default function PublishPage() {
  return (
    <Suspense fallback={<p className="text-[#8A8F98] text-sm">로딩 중…</p>}>
      <PublishHubContent />
    </Suspense>
  );
}
