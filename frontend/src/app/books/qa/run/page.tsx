"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

function RunQAContent() {
  const searchParams = useSearchParams();
  const book_id = searchParams.get("book_id") ?? "";
  const router = useRouter();
  const [status, setStatus] = useState<"running" | "done" | "error">("running");
  const [message, setMessage] = useState("QA 스테이지 실행 중…");

  useEffect(() => {
    if (!book_id) {
      setStatus("error");
      setMessage("book_id 파라미터가 없습니다.");
      return;
    }
    fetch(`${API_BASE}/engine/qa/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ book_id }),
    })
      .then(async (res) => {
        if (!res.ok) {
          const text = await res.text();
          throw new Error(`API ${res.status}: ${text}`);
        }
        return res.json();
      })
      .then(() => {
        setStatus("done");
        setMessage("QA 완료. 결과 페이지로 이동합니다…");
        setTimeout(() => router.push(`/books/qa?book_id=${book_id}`), 1200);
      })
      .catch((e: Error) => {
        setStatus("error");
        setMessage(e.message);
      });
  }, [book_id, router]);

  return (
    <div className="flex flex-col items-center justify-center min-h-[40vh] gap-4">
      {status === "running" && (
        <div className="h-8 w-8 rounded-full border-4 border-indigo-600 border-t-transparent animate-spin" />
      )}
      {status === "done" && <div className="text-emerald-600 text-4xl">✅</div>}
      {status === "error" && <div className="text-red-600 text-4xl">❌</div>}
      <p
        className={`text-sm font-medium ${
          status === "error" ? "text-red-700" : status === "done" ? "text-emerald-700" : "text-gray-600"
        }`}
      >
        {message}
      </p>
      {status === "error" && (
        <button
          onClick={() => router.back()}
          className="text-xs px-3 py-1.5 rounded bg-gray-100 text-gray-700 hover:bg-gray-200"
        >
          돌아가기
        </button>
      )}
    </div>
  );
}

export default function RunQAPage() {
  return (
    <Suspense fallback={<div className="text-gray-400 text-sm">로딩 중…</div>}>
      <RunQAContent />
    </Suspense>
  );
}
