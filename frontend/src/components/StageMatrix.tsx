"use client";

import clsx from "clsx";
import type { ChapterInfo } from "@/lib/api";
import { StatusBadge } from "./StatusBadge";

const CHAPTER_STAGES = [
  "S3","S4","S4A","S5","S6","S6A","S6B","S7","S8","S8A",
];

interface Props {
  chapterSequence: string[];
  chapters: Record<string, ChapterInfo>;
  onRunStage?: (stageId: string, chapterId: string) => void;
  running?: { stageId: string; chapterId: string } | null;
}

export function StageMatrix({ chapterSequence, chapters, onRunStage, running }: Props) {
  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200 shadow-sm">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="bg-gray-50 border-b border-gray-200">
            <th className="sticky left-0 bg-gray-50 text-left px-3 py-2 font-semibold text-gray-700 min-w-[160px] border-r border-gray-200">
              챕터
            </th>
            {CHAPTER_STAGES.map((s) => (
              <th
                key={s}
                className="text-center px-2 py-2 font-mono text-xs font-semibold text-gray-600 min-w-[64px]"
              >
                {s}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {chapterSequence.map((chapterId, i) => {
            const chapter = chapters[chapterId];
            if (!chapter) return null;
            return (
              <tr
                key={chapterId}
                className={clsx(
                  "border-b border-gray-100 hover:bg-gray-50 transition-colors",
                  i % 2 === 0 ? "bg-white" : "bg-gray-50/40"
                )}
              >
                <td className="sticky left-0 bg-inherit px-3 py-2 border-r border-gray-200">
                  <div className="font-mono text-xs text-gray-500">{chapterId}</div>
                  <div className="text-gray-800 font-medium truncate max-w-[150px]" title={chapter.title}>
                    {chapter.title}
                  </div>
                </td>
                {CHAPTER_STAGES.map((stageId) => {
                  const st = chapter.stages[stageId];
                  const status = st?.status ?? "blocked";
                  const isRunning =
                    running?.stageId === stageId && running?.chapterId === chapterId;
                  return (
                    <td key={stageId} className="text-center px-1 py-2">
                      <button
                        onClick={() =>
                          status === "pending" && onRunStage?.(stageId, chapterId)
                        }
                        disabled={status !== "pending" || isRunning}
                        title={st?.note ?? status}
                        className={clsx(
                          "w-full flex justify-center",
                          status === "pending" && "cursor-pointer hover:scale-110 transition-transform"
                        )}
                      >
                        <StatusBadge status={isRunning ? "in_progress" : status} size="xs" />
                      </button>
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
