"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { Sidebar } from "./Sidebar";
import { useAppStore } from "@/lib/store";
import { license } from "@/lib/api";

interface AppShellProps {
  children: React.ReactNode;
}

const PUBLIC_PATHS = ["/onboarding"];
const MAX_RETRIES = 8;       // 최대 8회 재시도
const RETRY_INTERVAL = 1500; // 1.5초 간격 → 최대 12초 대기

export function AppShell({ children }: AppShellProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { licenseStatus, setLicenseStatus } = useAppStore();
  const [checked, setChecked] = useState(false);
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) {
      setChecked(true);
      return;
    }

    // 스토어에 유효한 라이선스 캐시가 있으면 바로 통과
    if (licenseStatus?.valid) {
      setChecked(true);
      return;
    }

    let cancelled = false;

    const tryCheck = (attempt: number) => {
      license
        .status()
        .then((status) => {
          if (cancelled) return;
          if (status.valid) {
            setLicenseStatus(status);
            setChecked(true);
          } else {
            router.replace("/onboarding");
          }
        })
        .catch(() => {
          if (cancelled) return;
          if (attempt < MAX_RETRIES) {
            // 서버 아직 기동 중 — 재시도
            setRetryCount(attempt + 1);
            setTimeout(() => tryCheck(attempt + 1), RETRY_INTERVAL);
          } else {
            // 최대 재시도 초과 → 온보딩으로
            router.replace("/onboarding");
          }
        });
    };

    tryCheck(0);

    return () => {
      cancelled = true;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  if (!checked && !PUBLIC_PATHS.some((p) => pathname.startsWith(p))) {
    return (
      <div className="flex h-screen bg-[#020203] items-center justify-center flex-col gap-3">
        <div className="w-6 h-6 rounded-full border-2 border-[#5E6AD2] border-t-transparent animate-spin" />
        {retryCount > 0 && (
          <p className="text-[#4B5563] text-xs">
            서버 연결 중… ({retryCount}/{MAX_RETRIES})
          </p>
        )}
      </div>
    );
  }

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
