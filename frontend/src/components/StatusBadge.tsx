import clsx from "clsx";

const STATUS_STYLES: Record<string, string> = {
  completed:   "bg-emerald-100 text-emerald-800 border-emerald-200",
  in_progress: "bg-blue-100 text-blue-800 border-blue-200 animate-pulse",
  pending:     "bg-amber-100 text-amber-800 border-amber-200",
  gate_failed: "bg-red-100 text-red-800 border-red-200",
  blocked:     "bg-gray-100 text-gray-500 border-gray-200",
  not_started: "bg-gray-50 text-gray-400 border-gray-100",
};

const STATUS_LABEL: Record<string, string> = {
  completed:   "완료",
  in_progress: "진행중",
  pending:     "대기",
  gate_failed: "실패",
  blocked:     "차단",
  not_started: "미시작",
};

export function StatusBadge({
  status,
  size = "sm",
}: {
  status: string;
  size?: "xs" | "sm";
}) {
  return (
    <span
      className={clsx(
        "inline-block border rounded font-mono font-semibold whitespace-nowrap",
        size === "xs" ? "text-[10px] px-1 py-0.5" : "text-xs px-2 py-0.5",
        STATUS_STYLES[status] ?? "bg-gray-100 text-gray-600 border-gray-200"
      )}
    >
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}
