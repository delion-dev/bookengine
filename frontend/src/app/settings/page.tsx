"use client";

import { Settings } from "lucide-react";
import { ApiKeyManager } from "@/components/settings/ApiKeyManager";

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Settings size={22} className="text-[#5E6AD2]" />
        <div>
          <h1 className="text-xl font-bold text-[#EDEDEF]">설정</h1>
          <p className="text-[#8A8F98] text-sm">AI API 키 및 앱 설정을 관리합니다.</p>
        </div>
      </div>
      <ApiKeyManager />
    </div>
  );
}
