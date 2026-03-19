"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import useSWR from "swr";
import {
  BookOpen,
  LayoutDashboard,
  Zap,
  CheckSquare,
  ClipboardList,
  Upload,
  Settings,
  Plus,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { registry } from "@/lib/api";
import { AdSenseSlot } from "@/components/ads/AdSenseSlot";
import { useState } from "react";

interface NavItemProps {
  href: string;
  icon: React.ReactNode;
  label: string;
  indent?: boolean;
}

function NavItem({ href, icon, label, indent = false }: NavItemProps) {
  const pathname = usePathname();
  const isActive =
    pathname === href || (href !== "/" && pathname.startsWith(href));

  return (
    <Link
      href={href}
      className={`flex items-center gap-3 px-3 py-2 rounded-xl text-sm transition-all duration-150 group
        ${indent ? "ml-3" : ""}
        ${
          isActive
            ? "bg-[#5E6AD2]/20 text-[#7C85E0] border border-[#5E6AD2]/30"
            : "text-[#8A8F98] hover:text-[#EDEDEF] hover:bg-white/[0.05]"
        }`}
    >
      <span className={`flex-shrink-0 ${isActive ? "text-[#5E6AD2]" : "text-[#4B5563] group-hover:text-[#8A8F98]"}`}>
        {icon}
      </span>
      <span className="truncate">{label}</span>
    </Link>
  );
}

export function Sidebar() {
  const { data: books } = useSWR("books-list", () => registry.listBooks(), {
    refreshInterval: 10000,
  });
  const [expandedBook, setExpandedBook] = useState<string | null>(
    books?.books?.[0]?.book_id ?? null
  );

  const bookList = books?.books ?? [];

  return (
    <aside className="w-60 flex-shrink-0 h-screen sticky top-0 flex flex-col border-r border-white/[0.06] bg-[#050506]">
      {/* Logo */}
      <div className="px-5 py-5 border-b border-white/[0.06]">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-[#5E6AD2] flex items-center justify-center flex-shrink-0">
            <BookOpen size={16} className="text-white" />
          </div>
          <div>
            <p className="text-[#EDEDEF] font-semibold text-sm leading-tight">BookEngine</p>
            <p className="text-[#4B5563] text-[10px]">AI 도서 집필 플랫폼</p>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
        {/* 책 목록 */}
        <div className="mb-2">
          <p className="text-[#4B5563] text-[10px] font-semibold uppercase tracking-wider px-3 mb-2">
            내 책
          </p>

          {bookList.length === 0 && (
            <p className="text-[#4B5563] text-xs px-3 py-1">등록된 책 없음</p>
          )}

          {bookList.map((book) => (
            <div key={book.book_id}>
              <button
                onClick={() =>
                  setExpandedBook(
                    expandedBook === book.book_id ? null : book.book_id
                  )
                }
                className="w-full flex items-center gap-2 px-3 py-2 rounded-xl text-sm text-[#8A8F98] hover:text-[#EDEDEF] hover:bg-white/[0.05] transition-all"
              >
                <BookOpen size={15} className="flex-shrink-0 text-[#5E6AD2]" />
                <span className="truncate flex-1 text-left">{book.display_name}</span>
                {expandedBook === book.book_id ? (
                  <ChevronDown size={13} />
                ) : (
                  <ChevronRight size={13} />
                )}
              </button>

              {expandedBook === book.book_id && (
                <div className="mt-1 space-y-0.5">
                  <NavItem
                    href={`/?book_id=${book.book_id}`}
                    icon={<LayoutDashboard size={14} />}
                    label="대시보드"
                    indent
                  />
                  <NavItem
                    href={`/books/detail?book_id=${book.book_id}`}
                    icon={<Zap size={14} />}
                    label="파이프라인"
                    indent
                  />
                  <NavItem
                    href={`/books/qa?book_id=${book.book_id}`}
                    icon={<CheckSquare size={14} />}
                    label="QA 리포트"
                    indent
                  />
                  <NavItem
                    href={`/books/work-order?book_id=${book.book_id}`}
                    icon={<ClipboardList size={14} />}
                    label="Work Order"
                    indent
                  />
                  <NavItem
                    href={`/books/publish?book_id=${book.book_id}`}
                    icon={<Upload size={14} />}
                    label="Google Books 출판"
                    indent
                  />
                </div>
              )}
            </div>
          ))}
        </div>

        {/* 새 책 등록 */}
        <Link
          href="/books/new"
          className="flex items-center gap-2 px-3 py-2 rounded-xl text-sm text-[#5E6AD2] hover:bg-[#5E6AD2]/10 border border-dashed border-[#5E6AD2]/30 hover:border-[#5E6AD2]/50 transition-all"
        >
          <Plus size={15} />
          <span>새 책 등록</span>
        </Link>
      </nav>

      {/* 하단 — AdSense 예약 영역 + 설정 */}
      <div className="border-t border-white/[0.06]">
        {/* AdSense 슬롯 */}
        <div id="sidebar-ad-slot" className="px-3 py-2 flex items-center justify-center">
          <AdSenseSlot type="sidebar" />
        </div>

        <div className="px-3 pb-4">
          <NavItem
            href="/settings"
            icon={<Settings size={15} />}
            label="설정"
          />
        </div>
      </div>
    </aside>
  );
}
