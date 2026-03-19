"use client";

import { useState, useEffect } from "react";
import { Eye, EyeOff, Save, CheckCircle2, Loader2, Key, Cpu, Info } from "lucide-react";
import { settings as settingsApi } from "@/lib/api";
import { useAppStore } from "@/lib/store";
import type { AppSettings } from "@/lib/api";

function MaskedInput({
  label, value, onChange, placeholder, hint,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  hint?: string;
}) {
  const [show, setShow] = useState(false);
  return (
    <div>
      <label className="block text-xs text-[#8A8F98] mb-1.5">{label}</label>
      <div className="relative">
        <input
          type={show ? "text" : "password"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full bg-white/[0.05] border border-white/[0.08] focus:border-[#5E6AD2] focus:ring-2 focus:ring-[#5E6AD2]/25 rounded-xl px-4 py-2.5 pr-10 text-[#EDEDEF] font-mono text-sm outline-none transition-all placeholder:text-[#4B5563]"
        />
        <button
          type="button"
          onClick={() => setShow(!show)}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-[#4B5563] hover:text-[#8A8F98] transition-colors"
        >
          {show ? <EyeOff size={15} /> : <Eye size={15} />}
        </button>
      </div>
      {hint && <p className="text-[#4B5563] text-xs mt-1">{hint}</p>}
    </div>
  );
}

export function ApiKeyManager() {
  const setStoreSettings = useAppStore((s) => s.setSettings);
  const [form, setForm] = useState<AppSettings>({
    gemini_api_key: "", openai_api_key: "", default_model: "gemini-2.0-flash", app_version: "0.1.0",
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    settingsApi.get().then((s) => { setForm(s); setLoading(false); }).catch(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setSaved(false);
    try {
      const updated = await settingsApi.update(form);
      setForm(updated);
      setStoreSettings(updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-40">
        <Loader2 size={20} className="animate-spin text-[#5E6AD2]" />
      </div>
    );
  }

  return (
    <div className="max-w-2xl space-y-6">
      {/* AI API 키 */}
      <div className="backdrop-blur-md bg-white/5 border border-white/[0.08] rounded-2xl p-6">
        <div className="flex items-center gap-2 mb-5">
          <Key size={18} className="text-[#5E6AD2]" />
          <h2 className="font-semibold text-[#EDEDEF]">AI API 키</h2>
        </div>
        <div className="space-y-4">
          <MaskedInput
            label="Gemini API 키"
            value={form.gemini_api_key}
            onChange={(v) => setForm((f) => ({ ...f, gemini_api_key: v }))}
            placeholder="AIzaSy..."
            hint="Google AI Studio에서 발급 — aistudio.google.com"
          />
          <MaskedInput
            label="OpenAI API 키"
            value={form.openai_api_key}
            onChange={(v) => setForm((f) => ({ ...f, openai_api_key: v }))}
            placeholder="sk-..."
            hint="platform.openai.com에서 발급"
          />
        </div>
      </div>

      {/* 모델 설정 */}
      <div className="backdrop-blur-md bg-white/5 border border-white/[0.08] rounded-2xl p-6">
        <div className="flex items-center gap-2 mb-5">
          <Cpu size={18} className="text-[#5E6AD2]" />
          <h2 className="font-semibold text-[#EDEDEF]">기본 모델</h2>
        </div>
        <div>
          <label className="block text-xs text-[#8A8F98] mb-1.5">기본 AI 모델</label>
          <select
            value={form.default_model}
            onChange={(e) => setForm((f) => ({ ...f, default_model: e.target.value }))}
            className="w-full bg-white/[0.05] border border-white/[0.08] focus:border-[#5E6AD2] rounded-xl px-4 py-2.5 text-[#EDEDEF] text-sm outline-none transition-all appearance-none"
          >
            <option value="gemini-2.0-flash">Gemini 2.0 Flash (권장)</option>
            <option value="gemini-2.0-pro">Gemini 2.0 Pro</option>
            <option value="gpt-4o">GPT-4o</option>
            <option value="gpt-4o-mini">GPT-4o Mini</option>
          </select>
        </div>
      </div>

      {/* 앱 정보 */}
      <div className="backdrop-blur-md bg-white/5 border border-white/[0.08] rounded-2xl p-6">
        <div className="flex items-center gap-2 mb-4">
          <Info size={18} className="text-[#5E6AD2]" />
          <h2 className="font-semibold text-[#EDEDEF]">앱 정보</h2>
        </div>
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-[#8A8F98]">버전</span>
            <span className="text-[#EDEDEF] font-mono">{form.app_version}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-[#8A8F98]">플랫폼</span>
            <span className="text-[#EDEDEF]">Windows (Tauri)</span>
          </div>
        </div>
      </div>

      {/* 저장 버튼 */}
      <button
        onClick={handleSave}
        disabled={saving}
        className="flex items-center gap-2 bg-[#5E6AD2] hover:bg-[#7C85E0] disabled:opacity-50 text-white rounded-xl px-6 py-2.5 text-sm font-medium transition-all hover:shadow-[0_0_20px_rgba(94,106,210,0.25)]"
      >
        {saving ? <Loader2 size={15} className="animate-spin" /> : saved ? <CheckCircle2 size={15} /> : <Save size={15} />}
        {saving ? "저장 중…" : saved ? "저장됨!" : "설정 저장"}
      </button>
    </div>
  );
}
