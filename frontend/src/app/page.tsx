"use client";

import Link from "next/link";
import useSWR from "swr";
import { registry, healing } from "@/lib/api";
import { HealthCard } from "@/components/HealthCard";

function BookCard({ bookId, displayName }: { bookId: string; displayName: string }) {
  const { data: health } = useSWR(`health-${bookId}`, () => healing.status(bookId));

  return (
    <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
        <div>
          <h2 className="font-semibold text-lg text-gray-900">{displayName}</h2>
          <p className="text-xs font-mono text-gray-400 mt-0.5">{bookId}</p>
        </div>
        <Link
          href={`/books/detail?book_id=${bookId}`}
          className="text-sm px-4 py-1.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors"
        >
          파이프라인 보기 →
        </Link>
      </div>
      {health && (
        <div className="p-5 grid grid-cols-1 md:grid-cols-2 gap-4">
          <HealthCard status={health} />
          <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
            <h3 className="font-semibold text-gray-800 mb-3">빠른 액션</h3>
            <div className="space-y-2">
              <QuickLink href={`/books/detail?book_id=${bookId}`} label="📊 스테이지 매트릭스" />
              <QuickLink href={`/books/qa?book_id=${bookId}`} label="✅ QA 리포트" />
              <QuickLink href={`/books/work-order?book_id=${bookId}`} label="📋 Work Order" />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function QuickLink({ href, label }: { href: string; label: string }) {
  return (
    <Link href={href} className="flex items-center gap-2 text-sm text-indigo-700 hover:text-indigo-900 hover:underline">
      {label}
    </Link>
  );
}

export default function DashboardPage() {
  const { data: books, error } = useSWR("books-list", () => registry.listBooks());

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-red-700">
        <p className="font-semibold">⚠️ Core Engine API에 연결할 수 없습니다</p>
        <p className="text-sm mt-1">{error?.message ?? "API 연결 실패"}</p>
        <p className="text-sm mt-2 text-red-500">
          FastAPI 서버를 기동하세요:{" "}
          <code className="bg-red-100 px-1 rounded">python tools/core_engine_cli.py run-server</code>
        </p>
      </div>
    );
  }

  if (!books) {
    return <div className="text-gray-400 text-sm">로딩 중…</div>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">대시보드</h1>
        <p className="text-gray-500 text-sm mt-1">
          Core Engine 파이프라인 현황을 확인하고 스테이지를 실행합니다.
        </p>
      </div>

      {books.books.map((book) => (
        <BookCard key={book.book_id} bookId={book.book_id} displayName={book.display_name} />
      ))}

      {books.books.length === 0 && (
        <div className="text-center py-12 text-gray-400">
          등록된 책이 없습니다. bootstrap-book 명령으로 새 책을 생성하세요.
        </div>
      )}
    </div>
  );
}
