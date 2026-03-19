"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { Sidebar } from "./Sidebar";
import { useAppStore } from "@/lib/store";
import { license } from "@/lib/api";

interface AppShellProps {
  children: React.ReactNode;
}

// 라이선스 인증 없이 접근 가능한 경로
const PUBLIC_PATHS = ["/onboarding"];

export function AppShell({ children }: AppShellProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { licenseStatus, setLicenseStatus } = useAppStore();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    // 공개 경로는 가드 건너뜀
    if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) {
      setChecked(true);
      return;
    }

    // 스토어에 유효한 라이선스가 있으면 바로 통과
    if (licenseStatus?.valid) {
      setChecked(true);
      return;
    }

    // 없으면 API로 재확인 (앱 재기동 시 서버 측 상태 동기화)
    license
      .status()
      .then((status) => {
        if (status.valid) {
          setLicenseStatus(status);
          setChecked(true);
        } else {
          router.replace("/onboarding");
        }
      })
      .catch(() => {
        // 서버 미기동 상태 — 온보딩으로 이동
        router.replace("/onboarding");
      });
  }, [pathname, licenseStatus, router, setLicenseStatus]);

  // 라이선스 확인 전 빈 화면 (플래시 방지)
  if (!checked && !PUBLIC_PATHS.some((p) => pathname.startsWith(p))) {
    return (
      <div className="flex h-screen bg-[#020203] items-center justify-center">
        <div className="w-6 h-6 rounded-full border-2 border-[#5E6AD2] border-t-transparent animate-spin" />
      </div>
    );
  }

  // 온보딩 페이지는 AppShell 레이아웃 없이 full-screen
  if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) {
    return <>{children}</>;
  }

  return (
    <div className="flex h-screen bg-[#020203] overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-6xl mx-auto px-6 py-6">{children}</div>
      </main>
    </div>
  );
}
