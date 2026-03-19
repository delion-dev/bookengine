"use client";

import type { HealingStatus, GateFailure } from "@/lib/api";

interface Props {
  status: HealingStatus;
  onHeal?: () => void;
  healing?: boolean;
}

export function HealthCard({ status, onHeal, healing }: Props) {
  const pct = Math.round(status.completion_rate * 100);
  const barColor =
    pct >= 90 ? "bg-emerald-500" : pct >= 60 ? "bg-amber-500" : "bg-red-500";

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-gray-800">파이프라인 건강도</h3>
        {status.gate_failed_count > 0 && (
          <button
            onClick={onHeal}
            disabled={healing}
            className="text-xs px-3 py-1 rounded bg-red-600 text-white hover:bg-red-700 disabled:opacity-50"
          >
            {healing ? "복구중…" : "자동 복구"}
          </button>
        )}
      </div>

      {/* Progress bar */}
      <div className="w-full bg-gray-100 rounded-full h-2.5 mb-3">
        <div
          className={`h-2.5 rounded-full transition-all ${barColor}`}
          style={{ width: `${pct}%` }}
        />
      </div>

      <div className="grid grid-cols-3 gap-2 text-center text-sm">
        <Stat label="완료" value={status.completed} color="text-emerald-600" />
        <Stat label="대기" value={status.pending} color="text-amber-600" />
        <Stat label="실패" value={status.gate_failed_count} color="text-red-600" />
      </div>

      {status.gate_failed.length > 0 && (
        <div className="mt-3 space-y-1">
          <p className="text-xs font-semibold text-red-700">Gate 실패 항목</p>
          {status.gate_failed.slice(0, 5).map((f: GateFailure, i: number) => (
            <div key={i} className="text-xs text-red-600 font-mono">
              {f.chapter_id} / {f.stage_id}
            </div>
          ))}
          {status.gate_failed.length > 5 && (
            <div className="text-xs text-gray-400">
              외 {status.gate_failed.length - 5}건…
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div>
      <div className={`text-2xl font-bold ${color}`}>{value}</div>
      <div className="text-xs text-gray-500">{label}</div>
    </div>
  );
}
