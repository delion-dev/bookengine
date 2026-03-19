"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { open } from "@tauri-apps/plugin-dialog";
import {
  BookOpen, FolderOpen, FileText, Key,
  ArrowRight, ArrowLeft, CheckCircle2, Loader2, AlertCircle,
} from "lucide-react";
import { registry } from "@/lib/api";

interface Step1Data { book_id: string; display_name: string }
interface Step2Data { book_root: string; source_file: string }
interface Step3Data { gemini_api_key: string; openai_api_key: string }

const STEPS = ["기본 정보", "폴더 & 파일", "AI API 키"];

function StepIndicator({ current }: { current: number }) {
  return (
    <div className="flex items-center gap-2 mb-8">
      {STEPS.map((label, i) => (
        <div key={i} className="flex items-center gap-2">
          <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold transition-all
            ${i < current ? "bg-[#22C55E] text-white" :
              i === current ? "bg-[#5E6AD2] text-white shadow-[0_0_12px_rgba(94,106,210,0.4)]" :
              "bg-white/[0.08] text-[#4B5563]"}`}>
            {i < current ? <CheckCircle2 size={14} /> : i + 1}
          </div>
          <span className={`text-xs hidden sm:block ${i === current ? "text-[#EDEDEF]" : "text-[#4B5563]"}`}>
            {label}
          </span>
          {i < STEPS.length - 1 && (
            <div className={`h-px w-6 ${i < current ? "bg-[#22C55E]/50" : "bg-white/[0.08]"}`} />
          )}
        </div>
      ))}
    </div>
  );
}

export function BookWizard() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [step1, setStep1] = useState<Step1Data>({ book_id: "", display_name: "" });
  const [step2, setStep2] = useState<Step2Data>({ book_root: "", source_file: "" });
  const [step3, setStep3] = useState<Step3Data>({ gemini_api_key: "", openai_api_key: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // book_id 자동 생성
  const handleDisplayNameChange = (name: string) => {
    const auto = name.toLowerCase().replace(/[^a-z0-9가-힣]/g, "_").replace(/_+/g, "_").slice(0, 30);
    setStep1({ display_name: name, book_id: auto });
  };

  const pickFolder = async () => {
    const selected = await open({ directory: true, title: "책 작업 폴더 선택" });
    if (typeof selected === "string") setStep2((p) => ({ ...p, book_root: selected }));
  };

  const pickFile = async () => {
    const selected = await open({
      filters: [{ name: "Markdown/Text", extensions: ["md", "txt", "pdf"] }],
      title: "기획안 파일 선택",
    });
    if (typeof selected === "string") setStep2((p) => ({ ...p, source_file: selected }));
  };

  const validateStep = (): boolean => {
    setError("");
    if (step === 0) {
      if (!step1.display_name.trim()) { setError("책 제목을 입력해 주세요."); return false; }
      if (!step1.book_id.trim()) { setError("Book ID를 입력해 주세요."); return false; }
    }
    if (step === 1) {
      if (!step2.book_root) { setError("작업 폴더를 선택해 주세요."); return false; }
      if (!step2.source_file) { setError("기획안 파일을 선택해 주세요."); return false; }
    }
    return true;
  };

  const handleNext = () => {
    if (!validateStep()) return;
    setStep((s) => s + 1);
  };

  const handleSubmit = async () => {
    if (!validateStep()) return;
    setLoading(true);
    setError("");
    try {
      // 설정에 API 키 저장
      if (step3.gemini_api_key || step3.openai_api_key) {
        const { settings } = await import("@/lib/api");
        await settings.update({
          gemini_api_key: step3.gemini_api_key,
          openai_api_key: step3.openai_api_key,
        });
      }
      // 책 등록
      await registry.bootstrapBook({
        book_id: step1.book_id,
        display_name: step1.display_name,
        book_root: step2.book_root,
        source_file: step2.source_file,
      });
      router.push("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : "책 등록에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-lg mx-auto">
      <div className="mb-6">
        <h1 className="text-xl font-bold text-[#EDEDEF]">새 책 등록</h1>
        <p className="text-[#8A8F98] text-sm mt-1">작업 정보를 입력하고 AI 파이프라인을 시작하세요.</p>
      </div>

      <StepIndicator current={step} />

      <div className="backdrop-blur-md bg-white/5 border border-white/[0.08] rounded-2xl p-8">
        {/* Step 1 */}
        {step === 0 && (
          <div className="space-y-5">
            <div className="flex items-center gap-2 text-[#5E6AD2] mb-4">
              <BookOpen size={18} />
              <span className="font-semibold text-[#EDEDEF]">책 기본 정보</span>
            </div>
            <div>
              <label className="block text-xs text-[#8A8F98] mb-1.5">책 제목 *</label>
              <input
                type="text"
                value={step1.display_name}
                onChange={(e) => handleDisplayNameChange(e.target.value)}
                placeholder="예: 왕과 사는 남자"
                className="w-full bg-white/[0.05] border border-white/[0.08] focus:border-[#5E6AD2] focus:ring-2 focus:ring-[#5E6AD2]/25 rounded-xl px-4 py-2.5 text-[#EDEDEF] text-sm outline-none transition-all placeholder:text-[#4B5563]"
              />
            </div>
            <div>
              <label className="block text-xs text-[#8A8F98] mb-1.5">Book ID (자동 생성)</label>
              <input
                type="text"
                value={step1.book_id}
                onChange={(e) => setStep1((p) => ({ ...p, book_id: e.target.value }))}
                placeholder="book_id"
                className="w-full bg-white/[0.05] border border-white/[0.08] focus:border-[#5E6AD2] focus:ring-2 focus:ring-[#5E6AD2]/25 rounded-xl px-4 py-2.5 text-[#EDEDEF] font-mono text-sm outline-none transition-all"
              />
              <p className="text-[#4B5563] text-xs mt-1">영문 소문자, 숫자, 언더스코어만 허용</p>
            </div>
          </div>
        )}

        {/* Step 2 */}
        {step === 1 && (
          <div className="space-y-5">
            <div className="flex items-center gap-2 mb-4">
              <FolderOpen size={18} className="text-[#5E6AD2]" />
              <span className="font-semibold text-[#EDEDEF]">폴더 & 기획안 파일</span>
            </div>
            <div>
              <label className="block text-xs text-[#8A8F98] mb-1.5">작업 폴더 *</label>
              <div className="flex gap-2">
                <input
                  readOnly
                  value={step2.book_root}
                  placeholder="폴더를 선택하세요"
                  className="flex-1 bg-white/[0.05] border border-white/[0.08] rounded-xl px-4 py-2.5 text-[#EDEDEF] text-sm font-mono outline-none truncate placeholder:text-[#4B5563]"
                />
                <button
                  onClick={pickFolder}
                  className="flex items-center gap-1.5 px-4 py-2.5 bg-white/[0.08] hover:bg-white/[0.12] rounded-xl text-sm text-[#EDEDEF] transition-all"
                >
                  <FolderOpen size={15} /> 선택
                </button>
              </div>
            </div>
            <div>
              <label className="block text-xs text-[#8A8F98] mb-1.5">기획안 파일 *</label>
              <div className="flex gap-2">
                <input
                  readOnly
                  value={step2.source_file}
                  placeholder=".md / .txt / .pdf"
                  className="flex-1 bg-white/[0.05] border border-white/[0.08] rounded-xl px-4 py-2.5 text-[#EDEDEF] text-sm font-mono outline-none truncate placeholder:text-[#4B5563]"
                />
                <button
                  onClick={pickFile}
                  className="flex items-center gap-1.5 px-4 py-2.5 bg-white/[0.08] hover:bg-white/[0.12] rounded-xl text-sm text-[#EDEDEF] transition-all"
                >
                  <FileText size={15} /> 선택
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Step 3 */}
        {step === 2 && (
          <div className="space-y-5">
            <div className="flex items-center gap-2 mb-4">
              <Key size={18} className="text-[#5E6AD2]" />
              <span className="font-semibold text-[#EDEDEF]">AI API 키</span>
            </div>
            <p className="text-[#8A8F98] text-xs">나중에 설정에서 변경할 수 있습니다. 지금 건너뛰려면 비워두세요.</p>
            <div>
              <label className="block text-xs text-[#8A8F98] mb-1.5">Gemini API 키</label>
              <input
                type="password"
                value={step3.gemini_api_key}
                onChange={(e) => setStep3((p) => ({ ...p, gemini_api_key: e.target.value }))}
                placeholder="AIzaSy..."
                className="w-full bg-white/[0.05] border border-white/[0.08] focus:border-[#5E6AD2] focus:ring-2 focus:ring-[#5E6AD2]/25 rounded-xl px-4 py-2.5 text-[#EDEDEF] font-mono text-sm outline-none transition-all placeholder:text-[#4B5563]"
              />
            </div>
            <div>
              <label className="block text-xs text-[#8A8F98] mb-1.5">OpenAI API 키</label>
              <input
                type="password"
                value={step3.openai_api_key}
                onChange={(e) => setStep3((p) => ({ ...p, openai_api_key: e.target.value }))}
                placeholder="sk-..."
                className="w-full bg-white/[0.05] border border-white/[0.08] focus:border-[#5E6AD2] focus:ring-2 focus:ring-[#5E6AD2]/25 rounded-xl px-4 py-2.5 text-[#EDEDEF] font-mono text-sm outline-none transition-all placeholder:text-[#4B5563]"
              />
            </div>
          </div>
        )}

        {error && (
          <p className="flex items-center gap-1.5 text-[#EF4444] text-xs mt-4">
            <AlertCircle size={13} /> {error}
          </p>
        )}

        {/* 버튼 */}
        <div className="flex items-center justify-between mt-8">
          <button
            onClick={() => setStep((s) => s - 1)}
            disabled={step === 0}
            className="flex items-center gap-1.5 px-4 py-2 text-sm text-[#8A8F98] hover:text-[#EDEDEF] disabled:opacity-30 transition-all"
          >
            <ArrowLeft size={15} /> 이전
          </button>

          {step < 2 ? (
            <button
              onClick={handleNext}
              className="flex items-center gap-2 bg-[#5E6AD2] hover:bg-[#7C85E0] text-white rounded-xl px-6 py-2.5 text-sm font-medium transition-all hover:shadow-[0_0_20px_rgba(94,106,210,0.25)]"
            >
              다음 <ArrowRight size={15} />
            </button>
          ) : (
            <button
              onClick={handleSubmit}
              disabled={loading}
              className="flex items-center gap-2 bg-[#5E6AD2] hover:bg-[#7C85E0] disabled:opacity-50 text-white rounded-xl px-6 py-2.5 text-sm font-medium transition-all"
            >
              {loading ? <Loader2 size={15} className="animate-spin" /> : <CheckCircle2 size={15} />}
              {loading ? "등록 중…" : "등록 완료"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
