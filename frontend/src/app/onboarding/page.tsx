"use client";

import { LicenseKeyForm } from "@/components/onboarding/LicenseKeyForm";

export default function OnboardingPage() {
  return (
    <div className="min-h-[calc(100vh-3rem)] flex items-center justify-center px-4">
      {/* 배경 글로우 */}
      <div
        className="fixed inset-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse 60% 40% at 50% 0%, rgba(94,106,210,0.12) 0%, transparent 70%)",
        }}
      />
      <LicenseKeyForm />
    </div>
  );
}
