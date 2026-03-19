"use client";

import { Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";
import { registry, qa } from "@/lib/api";

function Breadcrumb({ book_id, label }: { book_id: string; label: string }) {
  return (
    <div className="flex items-center gap-3 text-sm">
      <Link href="/" className="text-gray-400 hover:text-gray-700">← 대시보드</Link>
      <span className="text-gray-300">/</span>
      <Link href={`/books/detail?book_id=${book_id}`} className="text-gray-400 hover:text-gray-700">
        {book_id}
      </Link>
      <span className="text-gray-300">/</span>
      <span className="text-gray-700 font-medium">{label}</span>
    </div>
  );
}

function QAContent({ book_id }: { book_id: string }) {
  const { data: detail } = useSWR(`book-${book_id}`, () => registry.getBook(book_id));
  const { data: report, error } = useSWR(`qa-report-${book_id}`, () => qa.getReport(book_id));

  const isNotFound = error?.message?.includes("404");

  if (error && isNotFound) {
    return (
      <div className="space-y-4">
        <Breadcrumb book_id={book_id} label="QA 리포트" />
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-6">
          <p className="font-semibold text-amber-800">QA 리포트 없음</p>
          <p className="text-sm text-amber-700 mt-1">SQA 스테이지를 실행하면 리포트가 생성됩니다.</p>
          <Link
            href={`/books/qa/run?book_id=${book_id}`}
            className="inline-block mt-3 text-xs px-3 py-1.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors"
          >
            QA 재실행
          </Link>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-4">
        <Breadcrumb book_id={book_id} label="QA 리포트" />
        <div className="text-red-600 p-4 rounded border border-red-200 bg-red-50">
          {error.message}
        </div>
      </div>
    );
  }

  if (!report) {
    return <div className="text-gray-400 text-sm">로딩 중…</div>;
  }

  const pct = Math.round((report.checks_passed / report.checks_total) * 100);

  return (
    <div className="space-y-6">
      <Breadcrumb book_id={book_id} label="QA 리포트" />

      <div
        className={`rounded-xl p-5 border ${
          report.overall_pass ? "bg-emerald-50 border-emerald-200" : "bg-red-50 border-red-200"
        }`}
      >
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold">
              {detail?.book.display_name ?? book_id} — QA 리포트
            </h1>
            <p className="text-sm mt-1 text-gray-600">
              게시 판정:{" "}
              <span className={`font-bold ${report.overall_pass ? "text-emerald-700" : "text-red-700"}`}>
                {report.overall_pass ? "PASS ✅" : "FAIL ❌"}
              </span>
            </p>
          </div>
          <div className="text-right">
            <div className={`text-3xl font-bold ${report.overall_pass ? "text-emerald-700" : "text-red-700"}`}>
              {pct}%
            </div>
            <div className="text-xs text-gray-500">{report.checks_passed}/{report.checks_total} 통과</div>
          </div>
        </div>
        <div className="w-full bg-white/60 rounded-full h-2 mt-3">
          <div
            className={`h-2 rounded-full ${report.overall_pass ? "bg-emerald-500" : "bg-red-500"}`}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
          <h2 className="font-semibold text-gray-700 text-sm">체크 결과</h2>
          <Link
            href={`/books/qa/run?book_id=${book_id}`}
            className="text-xs px-3 py-1.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors"
          >
            QA 재실행
          </Link>
        </div>
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-xs text-gray-500 uppercase">
            <tr>
              <th className="text-left px-4 py-2">체크 항목</th>
              <th className="text-center px-4 py-2 w-20">결과</th>
              <th className="text-left px-4 py-2">상세</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {report.checks.map((c) => (
              <tr key={c.check} className={c.passed ? "" : "bg-red-50"}>
                <td className="px-4 py-3 font-mono text-xs text-gray-700">{c.check}</td>
                <td className="px-4 py-3 text-center">
                  {c.passed ? (
                    <span className="text-emerald-600 font-bold">PASS</span>
                  ) : (
                    <span className="text-red-600 font-bold">FAIL</span>
                  )}
                </td>
                <td className="px-4 py-3 text-xs text-gray-500">{c.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {report.failed_checks.length > 0 && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4">
          <p className="text-sm font-semibold text-red-700 mb-2">실패 항목 요약</p>
          <ul className="space-y-1">
            {report.failed_checks.map((fc) => (
              <li key={fc} className="text-xs text-red-600 font-mono">• {fc}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function QAPageContent() {
  const searchParams = useSearchParams();
  const book_id = searchParams.get("book_id") ?? "";
  if (!book_id) {
    return <div className="text-red-600">book_id 파라미터가 없습니다.</div>;
  }
  return <QAContent book_id={book_id} />;
}

export default function QAPage() {
  return (
    <Suspense fallback={<div className="text-gray-400 text-sm">로딩 중…</div>}>
      <QAPageContent />
    </Suspense>
  );
}
