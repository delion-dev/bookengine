"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { KeyRound, ArrowRight, Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import { license } from "@/lib/api";
import { useAppStore } from "@/lib/store";

const TRIAL_KEY = "BKENG-TRIAL-00000-00000-00000";

function formatKey(raw: string): string {
  const clean = raw.replace(/[^A-Za-z0-9]/g, "").toUpperCase();
  const parts = [];
  for (let i = 0; i < clean.length && parts.join("").replace(/-/g, "").length < 29; i += 5) {
    parts.push(clean.slice(i, i + 5));
  }
  return parts.join("-").slice(0, 34);
}

export function LicenseKeyForm() {
  const router = useRouter();
  const setLicenseStatus = useAppStore((s) => s.setLicenseStatus);
  const [key, setKey] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setKey(formatKey(e.target.value));
    setError("");
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!key.trim()) {
      setError("라이선스 키를 입력해 주세요.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const result = await license.validate(key.trim());
      if (result.valid) {
        setLicenseStatus(result);
        setSuccess(true);
        setTimeout(() => router.push("/"), 800);
      } else {
        setError("유효하지 않은 라이선스 키입니다. 키를 확인해 주세요.");
      }
    } catch {
      setError("서버 연결에 실패했습니다. 앱을 다시 시작해 주세요.");
    } finally {
      setLoading(false);
    }
  };

  const handleTrial = async () => {
    setKey(TRIAL_KEY);
    setLoading(true);
    setError("");
    try {
      const result = await license.validate(TRIAL_KEY);
      if (result.valid) {
        setLicenseStatus(result);
        setSuccess(true);
        setTimeout(() => router.push("/"), 800);
      }
    } catch {
      setError("서버 연결에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="w-full max-w-md mx-auto">
      {/* 로고 */}
      <div className="text-center mb-8">
        <div className="w-16 h-16 rounded-2xl bg-[#5E6AD2] flex items-center justify-center mx-auto mb-4 shadow-[0_0_40px_rgba(94,106,210,0.3)]">
          <KeyRound size={28} className="text-white" />
        </div>
        <h1 className="text-2xl font-bold text-[#EDEDEF]">BookEngine</h1>
        <p className="text-[#8A8F98] text-sm mt-1">AI 기반 도서 자동 집필 플랫폼</p>
      </div>

      {/* 카드 */}
      <div className="backdrop-blur-md bg-white/5 border border-white/[0.08] rounded-2xl p-8">
        <h2 className="text-[#EDEDEF] font-semibold text-lg mb-1">라이선스 키 인증</h2>
        <p className="text-[#8A8F98] text-sm mb-6">구매한 라이선스 키를 입력하거나 무료 체험을 시작하세요.</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm text-[#8A8F98] mb-1.5" htmlFor="license-key">
              라이선스 키
            </label>
            <input
              id="license-key"
              type="text"
              value={key}
              onChange={handleChange}
              placeholder="BKENG-XXXXX-XXXXX-XXXXX-XXXXX"
              maxLength={34}
              className="w-full bg-white/[0.05] border border-white/[0.08] focus:border-[#5E6AD2] focus:ring-2 focus:ring-[#5E6AD2]/25 rounded-xl px-4 py-3 text-[#EDEDEF] font-mono text-sm outline-none transition-all placeholder:text-[#4B5563]"
              autoFocus
              spellCheck={false}
            />
            {error && (
              <p className="flex items-center gap-1.5 text-[#EF4444] text-xs mt-2">
                <AlertCircle size={13} /> {error}
              </p>
            )}
            {success && (
              <p className="flex items-center gap-1.5 text-[#22C55E] text-xs mt-2">
                <CheckCircle2 size={13} /> 인증 완료! 대시보드로 이동합니다…
              </p>
            )}
          </div>

          <button
            type="submit"
            disabled={loading || success}
            className="w-full flex items-center justify-center gap-2 bg-[#5E6AD2] hover:bg-[#7C85E0] disabled:opacity-50 text-white rounded-xl px-5 py-3 font-medium text-sm transition-all duration-150 hover:shadow-[0_0_20px_rgba(94,106,210,0.25)]"
          >
            {loading ? (
              <Loader2 size={16} className="animate-spin" />
            ) : success ? (
              <CheckCircle2 size={16} />
            ) : (
              <>
                인증하기 <ArrowRight size={16} />
              </>
            )}
          </button>
        </form>

        <div className="relative my-6">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-white/[0.06]" />
          </div>
          <div className="relative flex justify-center text-xs">
            <span className="bg-transparent px-3 text-[#4B5563]">또는</span>
          </div>
        </div>

        <button
          onClick={handleTrial}
          disabled={loading}
          className="w-full text-sm text-[#8A8F98] hover:text-[#EDEDEF] py-2 rounded-xl hover:bg-white/[0.05] transition-all disabled:opacity-50"
        >
          무료 체험 시작 (기능 제한 없음)
        </button>
      </div>

      <p className="text-center text-[#4B5563] text-xs mt-4">
        라이선스 구매 →{" "}
        <span className="text-[#5E6AD2]">bookengine.io</span>
      </p>
    </div>
  );
}
