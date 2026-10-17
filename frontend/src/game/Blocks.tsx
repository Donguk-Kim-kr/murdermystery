import { useState } from "react";

import type { GameState } from "./useGame";

/** 서버가 화면에 보내는 블록. 종류마다 쓰는 필드가 달라서 느슨하게 받고, 모르는 종류는 그리지 않는다. */
export type Block = Record<string, unknown> & { 종류?: string; 이름?: string };

interface Item {
  값: unknown;
  이름?: string | null;
  직업?: string | null;
  나이?: number | null;
  성별?: string | null;
  선택한_계정?: number | null;
  /** 장소: 종류와 설명, 이 사람이 지금 고를 수 없는지 */
  유형?: string | null;
  특징?: string | null;
  비활성?: boolean;
}

interface Card {
  종류: string;
  이름: string;
  내용: string;
  장소: string;
}

interface Props {
  block: Block;
  state: GameState;
  /** 서버로 답을 보낸다. 받아들여졌으면 true */
  onAnswer(questionId: string, value: unknown): Promise<boolean>;
}

const text = (v: unknown) => (typeof v === "string" ? v : v == null ? "" : String(v));

export function BlockView({ block, state, onAnswer }: Props) {
  switch (block.종류) {
    case "글":
      return <TextBlock block={block} />;
    case "읽기":
      return <ReadBlock block={block} onAnswer={onAnswer} isPlayer={state.나.역할 === "플레이어"} />;
    case "선택지":
      return <ChoiceBlock block={block} state={state} onAnswer={onAnswer} />;
    case "입력":
      return <InputBlock block={block} onAnswer={onAnswer} isPlayer={state.나.역할 === "플레이어"} />;
    case "카드목록":
      return <CardsBlock block={block} />;
    case "현황":
      return <ProgressBlock block={block} />;
    default:
      return null;
  }
}

function Title({ block }: { block: Block }) {
  const name = text(block.이름);
  return name && name !== "글" ? <h3>{name}</h3> : null;
}

function TextBlock({ block }: { block: Block }) {
  return (
    <section className="block" aria-label={text(block.이름) || "글"}>
      <Title block={block} />
      <p className="prose">{text(block.내용)}</p>
    </section>
  );
}

/** 단서·증언 카드를 앞면이 보이게 늘어놓는다. 위에는 어느 장소에서 얻었는지, 종류가 보인다. */
function CardsBlock({ block }: { block: Block }) {
  const cards = (block.항목 as Card[] | undefined) ?? [];
  return (
    <section className="block" aria-label={text(block.이름)}>
      <Title block={block} />
      {cards.length === 0 && <p className="muted">아직 얻은 것이 없습니다.</p>}
      <ul className="clue-cards">
        {cards.map((c, i) => (
          <li key={i} className="clue-card">
            <span className="clue-meta">
              <span className="chip">{c.종류}</span>
              {c.장소 && <span className="muted">{c.장소}</span>}
            </span>
            <strong>{c.이름}</strong>
            <p className="prose">{c.내용}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

function ProgressBar({ done, total, label }: { done: number; total: number; label: string }) {
  const percent = total > 0 ? Math.round((done / total) * 100) : 0;
  return (
    <div className="progress" role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={total} aria-valuenow={done}>
      <div className="bar" style={{ width: `${percent}%` }} />
    </div>
  );
}

function ProgressBlock({ block }: { block: Block }) {
  const done = Number(block.완료 ?? 0);
  const total = Number(block.전체 ?? 0);
  return (
    <section className="block" aria-label={text(block.이름)}>
      <div className="row">
        <strong>{text(block.이름)}</strong>
        <span className="chip">{done}/{total}</span>
      </div>
      <ProgressBar done={done} total={total} label={text(block.이름)} />
    </section>
  );
}

function InputBlock({ block, onAnswer, isPlayer }: { block: Block; onAnswer: Props["onAnswer"]; isPlayer: boolean }) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const limit = Number(block.글자수 ?? 300);
  const length = Array.from(value).length;
  return (
    <section className="block" aria-label={text(block.이름)}>
      <Title block={block} />
      <label>
        {text(block.질문)}
        <textarea rows={3} value={value} disabled={!isPlayer} onChange={(e) => setValue(e.target.value)} />
      </label>
      {isPlayer ? (
        <div className="row start">
          <button
            type="button"
            disabled={busy || value.trim() === "" || length > limit}
            onClick={async () => {
              setBusy(true);
              await onAnswer(text(block.질문ID), value);
              setBusy(false);
            }}
          >
            보내기
          </button>
          <span className={length > limit ? "error" : "muted"}>{length}/{limit}자</span>
        </div>
      ) : (
        <p className="muted">관전 중에는 답할 수 없습니다.</p>
      )}
    </section>
  );
}

function ReadBlock({ block, onAnswer, isPlayer }: { block: Block; onAnswer: Props["onAnswer"]; isPlayer: boolean }) {
  const [busy, setBusy] = useState(false);
  const progress = (block.현황 as { 완료: number; 전체: number } | undefined) ?? { 완료: 0, 전체: 0 };
  const needed = block.확인필요 === true;
  const done = block.확인함 === true;
  return (
    <section className="block" aria-label={text(block.이름)}>
      <Title block={block} />
      <p className="prose">{text(block.내용)}</p>
      <div className="row">
        <span className="chip">확인 {progress.완료}/{progress.전체}</span>
        {done && <span className="chip success">확인했습니다</span>}
        {needed && isPlayer && (
          <button
            type="button"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              await onAnswer(text(block.질문ID), true);
              setBusy(false);
            }}
          >
            확인
          </button>
        )}
      </div>
      <ProgressBar done={progress.완료} total={progress.전체} label={`${text(block.이름)} 확인 현황`} />
    </section>
  );
}

function ChoiceBlock({ block, state, onAnswer }: { block: Block; state: GameState; onAnswer: Props["onAnswer"] }) {
  const [picked, setPicked] = useState<unknown>(undefined);
  const [busy, setBusy] = useState(false);
  const items = (block.항목 as Item[] | undefined) ?? [];
  const isPlayer = state.나.역할 === "플레이어";
  const finished = block.내_선택_끝남 === true;
  const needConfirm = block.확인필요 === true;
  const nameOf = (account: number) => state.플레이어.find((p) => p.계정_번호 === account)?.닉네임 ?? "다른 참가자";
  const canPick = isPlayer && !finished;
  // 고른 항목을 다른 사람이 먼저 확정했으면 고른 것을 풀어 준다.
  const current = items.find((i) => i.값 === picked && i.선택한_계정 == null) ? picked : undefined;

  async function send(value: unknown) {
    setBusy(true);
    const ok = await onAnswer(text(block.질문ID), value);
    setBusy(false);
    if (ok) setPicked(undefined);
  }

  return (
    <section className="block" aria-label={text(block.이름)}>
      <Title block={block} />
      <ul className="choice-list">
        {items.map((item, index) => {
          const owner = item.선택한_계정 ?? null;
          const mine = owner !== null && owner === state.나.계정_번호;
          const taken = owner !== null;
          return (
            <li key={index}>
              <button
                type="button"
                className={`choice${current === item.값 ? " on" : ""}${mine ? " mine" : ""}`}
                aria-pressed={current === item.값}
                disabled={!canPick || taken || busy || item.비활성 === true}
                onClick={() => (needConfirm ? setPicked(item.값) : void send(item.값))}
              >
                <strong>{text(item.이름) || "이름 없음"}</strong>
                <span className="muted">
                  {[item.직업, item.나이 != null ? `${item.나이}세` : null, item.성별, item.유형, item.특징].filter(Boolean).join(" · ")}
                </span>
                {taken && <span className="chip accent">{mine ? "내 인물" : `${nameOf(owner!)} 선택`}</span>}
              </button>
            </li>
          );
        })}
      </ul>
      {isPlayer && needConfirm && (
        <div className="row start">
          <button type="button" disabled={finished || current === undefined || busy} onClick={() => void send(current)}>
            확인
          </button>
          <span className="muted">
            {finished ? "선택을 확정했습니다. 바꿀 수 없습니다." : current === undefined ? "인물을 고른 뒤 확인을 누르세요." : "확인하면 되돌릴 수 없습니다."}
          </span>
        </div>
      )}
      {!isPlayer && <p className="muted">관전 중에는 고를 수 없습니다.</p>}
    </section>
  );
}
