"use client";

import { Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";
import { registry, workOrder } from "@/lib/api";

const AGENT_COLORS: Record<string, string> = {
  "AG-WR": "bg-indigo-100 text-indigo-800",
  "AG-ST": "bg-violet-100 text-violet-800",
  "AG-VIS": "bg-sky-100 text-sky-800",
  "AG-IM": "bg-cyan-100 text-cyan-800",
  "AG-QA": "bg-amber-100 text-amber-800",
  "AG-PUB": "bg-emerald-100 text-emerald-800",
  "AG-REF": "bg-pink-100 text-pink-800",
  "AG-DCP": "bg-orange-100 text-orange-800",
  "AG-UKM": "bg-teal-100 text-teal-800",
  "AG-SYS": "bg-red-100 text-red-800",
};

function Breadcrumb({ book_id }: { book_id: string }) {
  return (
    <div className="flex items-center gap-3 text-sm">
      <Link href="/" className="text-gray-400 hover:text-gray-700">← 대시보드</Link>
      <span className="text-gray-300">/</span>
      <Link href={`/books/detail?book_id=${book_id}`} className="text-gray-400 hover:text-gray-700">
        {book_id}
      </Link>
      <span className="text-gray-300">/</span>
      <span className="text-gray-700 font-medium">Work Order</span>
    </div>
  );
}

function WorkOrderContent({ book_id }: { book_id: string }) {
  const { data: detail } = useSWR(`book-${book_id}`, () => registry.getBook(book_id));
  const { data: order, error } = useSWR(`work-order-${book_id}`, () => workOrder.issue(book_id));

  if (error) {
    return (
      <div className="space-y-4">
        <Breadcrumb book_id={book_id} />
        <div className="text-red-600 p-4 rounded border border-red-200 bg-red-50">
          {error instanceof Error ? error.message : "데이터 로드 실패"}
        </div>
      </div>
    );
  }

  if (!order) {
    return <div className="text-gray-400 text-sm">로딩 중…</div>;
  }

  return (
    <div className="space-y-6">
      <Breadcrumb book_id={book_id} />

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Work Order</h1>
          <p className="text-xs font-mono text-gray-400 mt-0.5">
            {detail?.book.display_name ?? book_id} — {order.order_id}
          </p>
        </div>
        <span className="text-xs bg-gray-100 text-gray-500 px-3 py-1 rounded-full">
          {order.priority_queue.length}개 작업
        </span>
      </div>

      <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-100">
          <h2 className="font-semibold text-gray-700 text-sm">우선순위 대기열</h2>
        </div>
        {order.priority_queue.length === 0 ? (
          <div className="p-8 text-center text-gray-400 text-sm">
            대기 중인 작업이 없습니다. 모든 스테이지가 완료되었습니다.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs text-gray-500 uppercase">
              <tr>
                <th className="text-center px-4 py-2 w-12">순위</th>
                <th className="text-left px-4 py-2">챕터</th>
                <th className="text-left px-4 py-2">스테이지</th>
                <th className="text-left px-4 py-2">에이전트</th>
                <th className="text-left px-4 py-2">액션</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {order.priority_queue.map((item) => {
                const agentColor = AGENT_COLORS[item.agent_id] ?? "bg-gray-100 text-gray-700";
                return (
                  <tr key={`${item.chapter_id}-${item.stage_id}`} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-center font-bold text-gray-400">#{item.rank}</td>
                    <td className="px-4 py-3 font-mono text-xs text-gray-700">{item.chapter_id}</td>
                    <td className="px-4 py-3 font-mono text-xs font-semibold text-gray-800">{item.stage_id}</td>
                    <td className="px-4 py-3">
                      <span className={`text-xs px-2 py-0.5 rounded-full font-mono font-medium ${agentColor}`}>
                        {item.agent_id}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-500">{item.action}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {order.gate_failures.length > 0 && (
        <div className="rounded-xl border border-red-200 bg-white shadow-sm overflow-hidden">
          <div className="px-4 py-3 border-b border-red-100 bg-red-50">
            <h2 className="font-semibold text-red-700 text-sm">Gate 실패 ({order.gate_failures.length}건)</h2>
          </div>
          <table className="w-full text-sm">
            <thead className="bg-red-50 text-xs text-red-500 uppercase">
              <tr>
                <th className="text-left px-4 py-2">챕터</th>
                <th className="text-left px-4 py-2">스테이지</th>
                <th className="text-left px-4 py-2">사유</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-red-100">
              {order.gate_failures.map((gf, i) => (
                <tr key={i} className="bg-red-50/50">
                  <td className="px-4 py-3 font-mono text-xs text-red-700">{gf.chapter_id}</td>
                  <td className="px-4 py-3 font-mono text-xs font-semibold text-red-800">{gf.stage_id}</td>
                  <td className="px-4 py-3 text-xs text-red-600">{gf.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function WorkOrderPageContent() {
  const searchParams = useSearchParams();
  const book_id = searchParams.get("book_id") ?? "";
  if (!book_id) {
    return <div className="text-red-600">book_id 파라미터가 없습니다.</div>;
  }
  return <WorkOrderContent book_id={book_id} />;
}

export default function WorkOrderPage() {
  return (
    <Suspense fallback={<div className="text-gray-400 text-sm">로딩 중…</div>}>
      <WorkOrderPageContent />
    </Suspense>
  );
}
