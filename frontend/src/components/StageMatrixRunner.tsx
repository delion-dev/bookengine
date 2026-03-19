"use client";

import { useState, useTransition } from "react";
import { StageMatrix } from "./StageMatrix";
import { stage as stageApi } from "@/lib/api";
import type { ChapterInfo } from "@/lib/api";

interface Props {
  bookId: string;
  chapterSequence: string[];
  chapters: Record<string, ChapterInfo>;
}

export function StageMatrixRunner({ bookId, chapterSequence, chapters }: Props) {
  const [chaptersState, setChaptersState] = useState(chapters);
  const [running, setRunning] = useState<{ stageId: string; chapterId: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [, startTransition] = useTransition();

  async function handleRunStage(stageId: string, chapterId: string) {
    setRunning({ stageId, chapterId });
    setError(null);
    try {
      const data = await stageApi.run(bookId, stageId, chapterId);
      // optimistic update
      startTransition(() => {
        setChaptersState((prev) => {
          const next = { ...prev };
          if (next[chapterId]) {
            next[chapterId] = {
              ...next[chapterId],
              stages: {
                ...next[chapterId].stages,
                [stageId]: {
                  status: data.status ?? "done",
                  updated_at: new Date().toISOString(),
                  note: "",
                },
              },
            };
          }
          return next;
        });
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "실행 실패");
    } finally {
      setRunning(null);
    }
  }

  return (
    <div className="space-y-2">
      {error && (
        <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
          {error}
        </div>
      )}
      <StageMatrix
        chapterSequence={chapterSequence}
        chapters={chaptersState}
        onRunStage={handleRunStage}
        running={running}
      />
    </div>
  );
}
