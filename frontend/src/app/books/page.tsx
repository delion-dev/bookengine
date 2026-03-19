"use client";

import Link from "next/link";
import useSWR from "swr";
import { registry } from "@/lib/api";
import { PlusCircle } from "lucide-react";

export default function BooksPage() {
  const { data: books, error } = useSWR("books-list", () => registry.listBooks());

  if (error) {
    return (
      <div className="text-red-600 p-4 rounded border border-red-200 bg-red-50">
        API 연결 실패. FastAPI 서버가 실행 중인지 확인하세요.
      </div>
    );
  }

  if (!books) {
    return <div className="text-gray-400 text-sm">로딩 중…</div>;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">등록된 책</h1>
        <Link
          href="/books/new"
          className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium px-4 py-2 rounded-lg"
        >
          <PlusCircle size={16} /> 새 책 등록
        </Link>
      </div>
      {books.books.map((book) => (
        <Link
          key={book.book_id}
          href={`/books/detail?book_id=${book.book_id}`}
          className="block rounded-xl border border-gray-200 bg-white p-5 shadow-sm hover:border-indigo-300 hover:shadow-md transition-all"
        >
          <div className="font-semibold text-lg text-gray-900">{book.display_name}</div>
          <div className="font-mono text-xs text-gray-400 mt-1">{book.book_id}</div>
          <div className="text-xs text-gray-400 mt-1 truncate">{book.book_root}</div>
        </Link>
      ))}
    </div>
  );
}
