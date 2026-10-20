import { useEffect, useRef, useState, useSyncExternalStore } from "react";

import { errorMessage, http } from "../api/client";
import { getToken } from "../api/token";
import { useConfirm } from "../confirm/ConfirmContext";
import { josa } from "../josa";

/** 작품에 붙은 이미지·영상 한 건(서버가 만든 서명된 주소 포함). */
export interface MediaItem {
  순서: number;
  대상: "단서" | "인물" | "공통스토리";
  번호: number | null;
  유형: "이미지" | "영상";
  주소: string | null;
}

export type MediaTarget = MediaItem["대상"];

const MB = 1024 * 1024;
/** 서버와 같은 제한(서버가 한 번 더 검사한다). 이미지는 jpg·png·webp, 영상은 mp4. */
export const RULES = {
  이미지: { accept: "image/jpeg,image/png,image/webp", types: ["image/jpeg", "image/png", "image/webp"], max: 5 * MB, hint: "jpg·png·webp, 5MB 까지" },
  영상: { accept: "video/mp4", types: ["video/mp4"], max: 100 * MB, hint: "mp4, 100MB 까지" },
} as const;

// 작품마다 한 번만 불러 모든 입력칸이 나눠 쓴다(단서가 많아도 요청은 하나이다).
const lists = new Map<number, MediaItem[] | "loading" | "error">();
const listeners = new Set<() => void>();
const notify = () => listeners.forEach((l) => l());

async function load(workId: number): Promise<void> {
  lists.set(workId, "loading");
  try {
    const res = await http("GET", `/api/works/${workId}/media`);
    lists.set(workId, res.error ? "error" : ((res.data as MediaItem[] | undefined) ?? []));
  } catch {
    lists.set(workId, "error");                  // 연결이 끊겼을 때: 목록 없이 올리기 칸만 보인다
  }
  notify();
}

export function reloadMedia(workId: number): Promise<void> {
  return load(workId);
}

/** 테스트에서 작품 사이에 상태가 새지 않게 비운다. */
export function resetMediaCache(): void {
  lists.clear();
  notify();
}

function useMedia(workId: number): MediaItem[] | null {
  const value = useSyncExternalStore(
    (cb) => { listeners.add(cb); return () => { listeners.delete(cb); }; },
    () => lists.get(workId),
  );
  useEffect(() => {
    if (!lists.has(workId)) void load(workId);
  }, [workId]);
  return Array.isArray(value) ? value : null;
}

interface Props {
  workId: number;
  target: MediaTarget;
  /** 단서·인물의 순서. 공통 스토리에는 없다 */
  order?: number;
  label: string;
}

/**
 * 이미지·영상 올리기. 단서·인물에는 이미지, 공통 스토리에는 영상을 한 건 붙인다. 다시 올리면 바뀌고 "지우기"로 뗀다.
 * 파일 내용을 그대로 PUT 으로 보내며(서버가 내용으로 형식을 다시 확인한다), 크기·형식은 보내기 전에 먼저 알려 준다.
 */
export function MediaField({ workId, target, order, label }: Props) {
  const confirm = useConfirm();
  const kind = target === "공통스토리" ? "영상" : "이미지";
  const rule = RULES[kind];
  const media = useMedia(workId);
  const current = media?.find((m) => m.대상 === target && (target === "공통스토리" || m.번호 === order)) ?? null;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  async function upload(file: File) {
    setError(null);
    if (!(rule.types as readonly string[]).includes(file.type)) {
      setError(`${josa(kind, "은/는")} ${rule.hint} 올릴 수 있습니다`);
      return;
    }
    if (file.size > rule.max) {
      setError(`파일이 너무 큽니다(${(file.size / MB).toFixed(1)}MB). ${rule.hint} 올릴 수 있습니다`);
      return;
    }
    setBusy(true);
    const query = new URLSearchParams({ 대상: target, ...(order !== undefined ? { 번호: String(order) } : {}) });
    try {
      const token = getToken();
      const res = await fetch(
        new Request(new URL(`/api/works/${workId}/media?${query}`, window.location.origin), {
          method: "PUT",
          headers: { "Content-Type": file.type, ...(token ? { Authorization: `Bearer ${token}` } : {}) },
          body: file,
        }),
      );
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        setError(errorMessage(body, `${josa(kind, "을/를")} 올리지 못했습니다`));
      } else {
        await reloadMedia(workId);
      }
    } catch {
      setError(`${josa(kind, "을/를")} 올리지 못했습니다. 연결을 확인해 주세요`);
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  async function remove() {
    if (!current || !(await confirm(`붙어 있는 ${josa(kind, "을/를")} 지울까요?`))) return;
    setError(null);
    setBusy(true);
    const res = await http("DELETE", `/api/works/${workId}/media/${current.순서}`);
    setBusy(false);
    if (res.error) setError(errorMessage(res.error, `${josa(kind, "을/를")} 지우지 못했습니다`));
    else await reloadMedia(workId);
  }

  return (
    <div className="media-field" role="group" aria-label={label}>
      <strong>{label}</strong>
      {current?.주소 &&
        (kind === "영상" ? (
          <video className="media-preview" controls preload="metadata" src={current.주소} aria-label={`${label} 미리보기`} />
        ) : (
          <img className="media-preview" src={current.주소} alt={`${label} 미리보기`} />
        ))}
      {current && !current.주소 && <p className="error">저장소에서 파일을 찾을 수 없습니다. 다시 올려 주세요.</p>}
      {!current && media !== null && <p className="muted">붙은 {josa(kind, "이/가")} 없습니다.</p>}
      <div className="row start">
        <label className="file-button">
          <input
            ref={input}
            type="file"
            accept={rule.accept}
            disabled={busy}
            aria-label={`${label} 파일 고르기`}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void upload(file);
            }}
          />
        </label>
        {current && (
          <button type="button" className="small secondary" disabled={busy} onClick={() => void remove()}>
            지우기
          </button>
        )}
        <span className="muted">{busy ? "올리는 중…" : rule.hint}</span>
      </div>
      {error && <p role="alert" className="error">{error}</p>}
    </div>
  );
}
