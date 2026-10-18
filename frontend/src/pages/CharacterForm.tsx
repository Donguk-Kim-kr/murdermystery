import { useState, type FormEvent } from "react";

import { api, errorMessage } from "../api/client";
import type { components } from "../api/schema";
import { josa } from "../josa";

export type Character = components["schemas"]["CharacterOut"];

const TEXT_FIELDS = ["직업", "성별", "캐릭터설명", "소개", "타임라인", "능력", "비밀", "목표"] as const;
const LONG = new Set<string>(["캐릭터설명", "소개", "타임라인", "능력", "비밀", "목표"]);
// 화면에 보이는 이름(칸 이름과 다른 것만)
const LABEL: Record<string, string> = { 캐릭터설명: "캐릭터 설명", 소개: "자기소개 멘트" };
const HINT: Record<string, string> = {
  캐릭터설명: "캐릭터를 고를 때 인물 카드에 함께 보여 줄 수 있는 설명입니다(보일지는 흐름의 캐릭터 선택 카드 설정에서 정합니다)",
  소개: "자기소개 단계에서 이 인물을 소개할 때 보여 주는 멘트입니다. 비우면 플레이어가 스스로 소개합니다",
};

// 서사는 부분으로 나누어 쓴다. 전체 글자 수는 10000자이고 부분이 늘수록 각 부분의 제한이 줄어든다(서버 narrative.py 와 같은 규칙).
const MAX_PARTS = 5;
const TOTAL_LIMIT = 10000;
const partLimit = (count: number) => Math.floor(TOTAL_LIMIT / Math.max(count, 1));
const length = (text: string) => Array.from(text).length;

interface PartDraft {
  key: number;
  id: string | null;
  text: string;
}

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
  const [parts, setParts] = useState<PartDraft[]>(() => {
    const saved = character?.서사_부분 ?? [];
    return (saved.length > 0 ? saved : [{ ID: null, 본문: "" }]).map((p, key) => ({ key, id: p.ID ?? null, text: p.본문 }));
  });
  const [nextKey, setNextKey] = useState(100);
  const [texts, setTexts] = useState<Record<string, string>>(
    Object.fromEntries(TEXT_FIELDS.map((f) => [f, character?.[f] ?? ""])),
  );
  const [culprit, setCulprit] = useState(character?.범인 ?? false);
  // 인물 종류: 플레이하는 인물 / NPC 가 될 수 있는 인물(인원이 모자라면 순위대로 NPC 가 된다) / 항상 NPC(예: 시작부터 죽은 피해자)
  const [kind, setKind] = useState<"player" | "maybe" | "npc">(character?.NPC ? "npc" : character?.NPC순위 != null ? "maybe" : "player");
  const [rank, setRank] = useState(character?.NPC순위?.toString() ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const limit = partLimit(parts.length);
  const nextLimit = partLimit(parts.length + 1);
  const overAfterAdd = parts.flatMap((p, i) => (length(p.text) > nextLimit ? [i + 1] : []));

  function addPart() {
    if (parts.length >= MAX_PARTS) return;
    if (
      overAfterAdd.length > 0 &&
      !window.confirm(
        `서사를 ${parts.length + 1}개로 나누면 각 서사는 ${nextLimit}자까지 쓸 수 있습니다. ` +
          `${josa(`지금 서사 ${overAfterAdd.join(", ")}`, "이/가")} 넘으므로 줄여야 저장할 수 있습니다. 추가할까요?`,
      )
    )
      return;
    setParts([...parts, { key: nextKey, id: null, text: "" }]);
    setNextKey(nextKey + 1);
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body = {
      이름: name,
      나이: age.trim() === "" ? null : Number(age),
      // 비어 있는 서사 하나뿐이면 서사가 없는 것으로 저장한다
      서사_부분: parts.length === 1 && parts[0].text.trim() === "" ? [] : parts.map((p) => ({ ID: p.id, 본문: p.text })),
      직업: orNull(texts.직업),
      성별: orNull(texts.성별),
      소개: orNull(texts.소개),
      캐릭터설명: orNull(texts.캐릭터설명),
      타임라인: orNull(texts.타임라인),
      능력: orNull(texts.능력),
      비밀: orNull(texts.비밀),
      목표: orNull(texts.목표),
      범인: culprit,
      NPC: kind === "npc",
      NPC순위: kind === "maybe" ? (rank.trim() === "" ? null : Number(rank)) : null,
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
      <p className="muted">이름은 임시로 정해도 됩니다. 나중에 바꿀 수 있습니다.</p>
      <div className="field-grid two">
        <label>
          <span className="req-label">이름</span>
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={50} required />
        </label>
        <label>
          나이
          <input type="number" min={0} max={200} value={age} onChange={(e) => setAge(e.target.value)} />
        </label>
        {TEXT_FIELDS.map((f) => (
          <div key={f} className={LONG.has(f) ? "field wide" : "field"}>
            <label>
              {LABEL[f] ?? f}
              {LONG.has(f) ? (
                <textarea rows={2} value={texts[f]} onChange={(e) => setTexts({ ...texts, [f]: e.target.value })} />
              ) : (
                <input value={texts[f]} onChange={(e) => setTexts({ ...texts, [f]: e.target.value })} />
              )}
            </label>
            {HINT[f] && <span className="hint">{HINT[f]}</span>}
          </div>
        ))}
        <div className="wide story-parts">
          {parts.map((p, i) => (
            <div key={p.key} className="story-part">
              <label>
                <span className="row">
                  <span>서사 {i + 1}</span>
                  <span className={length(p.text) > limit ? "error" : "muted"}>
                    {length(p.text)}/{limit}자
                  </span>
                </span>
                <textarea
                  rows={4}
                  value={p.text}
                  onChange={(e) => setParts(parts.map((q) => (q.key === p.key ? { ...q, text: e.target.value } : q)))}
                />
              </label>
              {parts.length > 1 && (
                <button type="button" className="small secondary" onClick={() => setParts(parts.filter((q) => q.key !== p.key))}>
                  서사 {i + 1} 삭제
                </button>
              )}
            </div>
          ))}
          <div className="row start">
            <button type="button" className="small secondary" disabled={parts.length >= MAX_PARTS} onClick={addPart}>
              서사 추가하기
            </button>
            <span className="muted">
              {parts.length >= MAX_PARTS
                ? `서사는 ${MAX_PARTS}개까지 나눌 수 있습니다.`
                : `서사를 ${parts.length + 1}개로 나누면 각 서사는 ${nextLimit}자까지 쓸 수 있습니다.` +
                  (overAfterAdd.length > 0 ? ` ${josa(`지금 서사 ${overAfterAdd.join(", ")}`, "이/가")} 넘습니다.` : "")}
            </span>
          </div>
        </div>
      </div>
      <div className="row start">
        <label className="check">
          <input type="checkbox" checked={culprit} onChange={(e) => setCulprit(e.target.checked)} />
          범인
        </label>
      </div>
      <fieldset className="npc-kind">
        <legend>인물 종류</legend>
        <label className="check">
          <input type="radio" name="npc-kind" checked={kind === "player"} onChange={() => setKind("player")} />
          플레이하는 인물
        </label>
        <label className="check">
          <input type="radio" name="npc-kind" checked={kind === "maybe"} onChange={() => setKind("maybe")} />
          NPC가 될 수 있는 인물
        </label>
        {kind === "maybe" && (
          <label className="inline">
            NPC 순위
            <input type="number" min={1} max={100} value={rank} onChange={(e) => setRank(e.target.value)} required />
            <span className="muted">
              인원이 모자랄 때 숫자가 작은 인물부터 NPC가 됩니다(예: 8인 게임을 7인으로 하면 순위 1, 6인으로 하면 순위 1과 2). 순위는 인물마다 달라야 합니다
            </span>
          </label>
        )}
        <label className="check">
          <input type="radio" name="npc-kind" checked={kind === "npc"} onChange={() => setKind("npc")} />
          항상 NPC (플레이할 수 없는 인물, 예: 시작부터 죽은 피해자)
        </label>
      </fieldset>
      {error && <p role="alert" className="error">{error}</p>}
      <div className="row start">
        <button type="submit" disabled={busy}>저장</button>
        <button type="button" className="secondary" onClick={onCancel}>취소</button>
      </div>
    </form>
  );
}
