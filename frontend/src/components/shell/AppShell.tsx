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
const MAX_SERVER_RETRIES = 10;   // 서버 기동 대기 최대 횟수
const RETRY_INTERVAL = 1500;     // 1.5초 간격 → 최대 15초 대기

// 서버 연결 실패 vs 라이선스 없음을 구분하는 상태
type CheckState =
  | "idle"
  | "connecting"    // 서버 연결 시도 중
  | "no_license"    // 서버 응답 OK, 라이선스 없음
  | "server_down"   // 서버 응답 없음 (최대 재시도 초과)
  | "ok";           // 서버 OK + 라이선스 유효

export function AppShell({ children }: AppShellProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { licenseStatus, setLicenseStatus } = useAppStore();
  const [checkState, setCheckState] = useState<CheckState>("idle");
  const [retryCount, setRetryCount] = useState(0);

  const isPublic = PUBLIC_PATHS.some((p) => pathname.startsWith(p));

  useEffect(() => {
    if (isPublic) {
      setCheckState("ok");
      return;
    }

    // 스토어에 유효한 라이선스 캐시가 있으면 바로 통과
    if (licenseStatus?.valid) {
      setCheckState("ok");
      return;
    }

    let cancelled = false;
    setCheckState("connecting");

    const tryCheck = (attempt: number) => {
      license
        .status()
        .then((status) => {
          if (cancelled) return;
          if (status.valid) {
            // ✅ 서버 OK + 라이선스 유효
            setLicenseStatus(status);
            setCheckState("ok");
          } else {
            // ✅ 서버 OK, 라이선스 없음 → 온보딩
            setCheckState("no_license");
            router.replace("/onboarding");
          }
        })
        .catch(() => {
          if (cancelled) return;
          if (attempt < MAX_SERVER_RETRIES) {
            // ⏳ 서버 아직 기동 중 — 재시도
            setRetryCount(attempt + 1);
            setTimeout(() => tryCheck(attempt + 1), RETRY_INTERVAL);
          } else {
            // ❌ 서버 다운 — 별도 안내 (온보딩 대신 server_down 화면)
            setCheckState("server_down");
          }
        });
    };

    tryCheck(0);

    return () => {
      cancelled = true;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  // 공개 페이지 (온보딩)
  if (isPublic) {
    return <>{children}</>;
  }

  // 서버 연결 중
  if (checkState === "idle" || checkState === "connecting") {
    return (
      <div className="flex h-screen bg-[#020203] items-center justify-center flex-col gap-3">
        <div className="w-6 h-6 rounded-full border-2 border-[#5E6AD2] border-t-transparent animate-spin" />
        <p className="text-[#4B5563] text-xs">
          {retryCount > 0
            ? `서버 연결 중… (${retryCount}/${MAX_SERVER_RETRIES})`
            : "BookEngine 초기화 중…"}
        </p>
      </div>
    );
  }

  // 서버 다운 (Python 서버 미기동)
  if (checkState === "server_down") {
    return (
      <div className="flex h-screen bg-[#020203] items-center justify-center flex-col gap-4 px-6">
        <div className="backdrop-blur-md bg-white/5 border border-white/[0.08] rounded-2xl p-8 max-w-sm w-full text-center">
          <p className="text-[#EF4444] font-semibold mb-2">서버에 연결할 수 없습니다</p>
          <p className="text-[#4B5563] text-sm mb-6">
            FastAPI 서버가 실행 중인지 확인해주세요.
          </p>
          <code className="block bg-black/30 text-[#8A8F98] text-xs rounded-lg px-4 py-3 mb-6 text-left">
            python tools/core_engine_cli.py run-server
          </code>
          <button
            onClick={() => {
              setRetryCount(0);
              setCheckState("connecting");
              // 재시도 트리거 — pathname 변경 없이 수동 재시도
              license.status().then((s) => {
                if (s.valid) { setLicenseStatus(s); setCheckState("ok"); }
                else { setCheckState("no_license"); router.replace("/onboarding"); }
              }).catch(() => setCheckState("server_down"));
            }}
            className="w-full bg-[#5E6AD2] hover:bg-[#7C85E0] text-white rounded-xl px-5 py-2.5 text-sm transition-all"
          >
            다시 연결
          </button>
        </div>
      </div>
    );
  }

  // 정상 렌더링
  return (
    <div className="flex h-screen bg-[#020203] overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-6xl mx-auto px-6 py-6">{children}</div>
      </main>
    </div>
  );
}
