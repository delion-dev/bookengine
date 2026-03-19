"use client";

import { Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";
import { registry, stage, healing, type HealingStatus } from "@/lib/api";
import { StageMatrixRunner } from "@/components/StageMatrixRunner";
import { HealthCard } from "@/components/HealthCard";
import { StatusBadge } from "@/components/StatusBadge";

const BOOK_STAGES = ["S-1", "S0", "S1", "S2", "SQA", "S9"];

function ActionLink({ href, label, color }: { href: string; label: string; color: "indigo" | "gray" }) {
  const cls =
    color === "indigo"
      ? "bg-indigo-600 text-white hover:bg-indigo-700"
      : "bg-gray-100 text-gray-700 hover:bg-gray-200";
  return (
    <Link href={href} className={`text-sm px-4 py-1.5 rounded-lg transition-colors ${cls}`}>
      {label}
    </Link>
  );
}

function BookDetail({ book_id }: { book_id: string }) {
  const { data: detail, error: detailErr } = useSWR(`book-${book_id}`, () => registry.getBook(book_id));
  const { data: pipeline, error: pipelineErr } = useSWR(`pipeline-${book_id}`, () => stage.getPipeline(book_id));
  const { data: health } = useSWR<HealingStatus>(`health-${book_id}`, () => healing.status(book_id));

  const error = detailErr || pipelineErr;
  if (error) {
    return (
      <div className="text-red-600 p-4 rounded border border-red-200 bg-red-50">
        {error instanceof Error ? error.message : "데이터 로드 실패"}
      </div>
    );
  }

  if (!detail || !pipeline) {
    return <div className="text-gray-400 text-sm">로딩 중…</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link href="/" className="text-gray-400 hover:text-gray-700 text-sm">← 대시보드</Link>
        <span className="text-gray-300">/</span>
        <h1 className="text-2xl font-bold">{detail.book.display_name}</h1>
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
        <h2 className="font-semibold text-gray-700 mb-3 text-sm">북-레벨 스테이지</h2>
        <div className="flex flex-wrap gap-3">
          {BOOK_STAGES.map((sid) => {
            const st = detail.book_level_stages[sid];
            return (
              <div key={sid} className="flex items-center gap-1.5 text-sm">
                <span className="font-mono text-gray-500">{sid}</span>
                <StatusBadge status={st?.status ?? "not_started"} />
              </div>
            );
          })}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {health && <HealthCard status={health} />}
        <div className="md:col-span-2 rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
          <h2 className="font-semibold text-gray-700 mb-3 text-sm">액션</h2>
          <div className="flex flex-wrap gap-2">
            <ActionLink href={`/books/qa?book_id=${book_id}`} label="QA 리포트" color="indigo" />
            <ActionLink href={`/books/work-order?book_id=${book_id}`} label="Work Order" color="gray" />
          </div>
        </div>
      </div>

      <div>
        <h2 className="font-semibold text-gray-800 mb-3">챕터 × 스테이지 매트릭스</h2>
        <StageMatrixRunner
          bookId={book_id}
          chapterSequence={pipeline.chapter_sequence}
          chapters={pipeline.chapters}
        />
      </div>

      <p className="text-xs text-gray-400">
        ※ 대기(amber) 상태 셀을 클릭하면 해당 스테이지를 실행합니다.
      </p>
    </div>
  );
}

function BookDetailContent() {
  const searchParams = useSearchParams();
  const book_id = searchParams.get("book_id") ?? "";
  if (!book_id) {
    return <div className="text-red-600">book_id 파라미터가 없습니다.</div>;
  }
  return <BookDetail book_id={book_id} />;
}

export default function BookDetailPage() {
  return (
    <Suspense fallback={<div className="text-gray-400 text-sm">로딩 중…</div>}>
      <BookDetailContent />
    </Suspense>
  );
}
