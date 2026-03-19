"use client";

import { useEffect, useRef } from "react";

type SlotType = "sidebar" | "leaderboard";

interface AdSenseSlotProps {
  type: SlotType;
  className?: string;
}

const SLOT_CONFIG: Record<SlotType, { width: number; height: number; label: string }> = {
  sidebar:     { width: 160, height: 600, label: "광고" },
  leaderboard: { width: 728, height: 90,  label: "광고" },
};

const CLIENT_ID = process.env.NEXT_PUBLIC_ADSENSE_CLIENT_ID ?? "";
const SLOT_IDS: Record<SlotType, string> = {
  sidebar:     process.env.NEXT_PUBLIC_ADSENSE_SLOT_SIDEBAR ?? "",
  leaderboard: process.env.NEXT_PUBLIC_ADSENSE_SLOT_LEADERBOARD ?? "",
};

export function AdSenseSlot({ type, className = "" }: AdSenseSlotProps) {
  const insRef = useRef<HTMLModElement>(null);
  const config = SLOT_CONFIG[type];
  const isDev = process.env.NODE_ENV === "development" || !CLIENT_ID;

  useEffect(() => {
    if (isDev || !insRef.current) return;
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ((window as any).adsbygoogle = (window as any).adsbygoogle || []).push({});
    } catch {
      // AdSense not loaded
    }
  }, [isDev]);

  if (isDev) {
    return (
      <div
        className={`flex items-center justify-center bg-white/[0.03] border border-dashed border-white/[0.06] rounded-xl text-[#4B5563] text-xs ${className}`}
        style={{ width: config.width, height: config.height, minWidth: config.width }}
      >
        AdSense ({config.width}×{config.height})
      </div>
    );
  }

  return (
    <div className={className} style={{ minWidth: config.width }}>
      <ins
        ref={insRef}
        className="adsbygoogle"
        style={{ display: "block", width: config.width, height: config.height }}
        data-ad-client={CLIENT_ID}
        data-ad-slot={SLOT_IDS[type]}
        data-ad-format="fixed"
      />
    </div>
  );
}
