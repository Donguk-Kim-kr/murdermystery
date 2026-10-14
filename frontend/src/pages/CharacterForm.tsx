import { useState, type FormEvent } from "react";

import { api, errorMessage } from "../api/client";
import type { components } from "../api/schema";

export type Character = components["schemas"]["CharacterOut"];

const TEXT_FIELDS = ["직업", "성별", "타임라인", "능력", "비밀", "목표"] as const;
const LONG = new Set<string>(["타임라인", "능력", "비밀", "목표"]);

/** 빈 칸은 null(값 없음)로 보낸다. */
const orNull = (s: string) => (s.trim() === "" ? null : s);

interface Props {
  workId: number;
  /** 있으면 수정, 없으면 새 인물 */
  character?: Character;
  onSaved: () => void;
  onCancel: () => void;
}

export function CharacterForm({ workId, character, onSaved, onCancel }: Props) {
  const [name, setName] = useState(character?.이름 ?? "");
  const [age, setAge] = useState(character?.나이?.toString() ?? "");
  const [story, setStory] = useState(character?.서사 ?? "");
  const [texts, setTexts] = useState<Record<string, string>>(
    Object.fromEntries(TEXT_FIELDS.map((f) => [f, character?.[f] ?? ""])),
  );
  const [culprit, setCulprit] = useState(character?.범인 ?? false);
  const [npc, setNpc] = useState(character?.NPC ?? false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body = {
      이름: name,
      나이: age.trim() === "" ? null : Number(age),
      서사: story,
      직업: orNull(texts.직업),
      성별: orNull(texts.성별),
      타임라인: orNull(texts.타임라인),
      능력: orNull(texts.능력),
      비밀: orNull(texts.비밀),
      목표: orNull(texts.목표),
      범인: culprit,
      NPC: npc,
    };
    const params = { params: { path: { work_id: workId } } };
    const res = character
      ? await api.PATCH("/api/works/{work_id}/characters/{order}", {
          params: { path: { work_id: workId, order: character.순서 } },
          body,
        })
      : await api.POST("/api/works/{work_id}/characters", { ...params, body });
    setBusy(false);
    if (res.error) setError(errorMessage(res.error, "인물을 저장하지 못했습니다"));
    else onSaved();
  }

  return (
    <form onSubmit={onSubmit} className="subform" aria-label={character ? "인물 수정" : "인물 추가"}>
      <div className="field-grid two">
        <label>
          이름
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={50} required />
        </label>
        <label>
          나이
          <input type="number" min={0} max={200} value={age} onChange={(e) => setAge(e.target.value)} />
        </label>
        {TEXT_FIELDS.map((f) => (
          <label key={f} className={LONG.has(f) ? "wide" : undefined}>
            {f}
            {LONG.has(f) ? (
              <textarea rows={2} value={texts[f]} onChange={(e) => setTexts({ ...texts, [f]: e.target.value })} />
            ) : (
              <input value={texts[f]} onChange={(e) => setTexts({ ...texts, [f]: e.target.value })} />
            )}
          </label>
        ))}
        <label className="wide">
          서사
          <textarea rows={4} value={story} onChange={(e) => setStory(e.target.value)} />
        </label>
      </div>
      <div className="row start">
        <label className="check">
          <input type="checkbox" checked={culprit} onChange={(e) => setCulprit(e.target.checked)} />
          범인
        </label>
        <label className="check">
          <input type="checkbox" checked={npc} onChange={(e) => setNpc(e.target.checked)} />
          NPC (플레이할 수 없는 인물)
        </label>
      </div>
      {error && <p role="alert" className="error">{error}</p>}
      <div className="row start">
        <button type="submit" disabled={busy}>저장</button>
        <button type="button" className="secondary" onClick={onCancel}>취소</button>
      </div>
    </form>
  );
}
