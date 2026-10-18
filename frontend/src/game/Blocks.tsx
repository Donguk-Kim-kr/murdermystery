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
  /** 투표: 인물이 아닌 선택지(예: 사고사) */
  기타?: boolean;
}

interface Card {
  종류: string;
  /** 진짜 이름 */
  이름: string;
  /** 남들에게 보이는 이름. 비어 있으면 진짜 이름만 보인다 */
  공개이름?: string;
  내용: string;
  장소: string;
  /** 단서만: 단서 번호, 지금 누구에게 공개했는지("전체" 또는 계정 번호 목록), 양도할 수 있는지 */
  순서?: number;
  공개?: "전체" | number[];
  양도가능?: boolean;
  /** 공개된 단서: 누가 보여 준 것인지 */
  주인?: string;
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
    case "투표":
      return <VoteBlock block={block} state={state} onAnswer={onAnswer} />;
    case "카드목록":
      return <CardsBlock block={block} state={state} onAnswer={onAnswer} />;
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

/** 비공개 투표. 후보를 고르고 "투표"를 누르며, 다음 단계로 넘어가기 전에는 다시 골라 바꿀 수 있다. 남의 표는 보이지 않는다. */
function VoteBlock({ block, state, onAnswer }: { block: Block; state: GameState; onAnswer: Props["onAnswer"] }) {
  const items = (block.항목 as Item[] | undefined) ?? [];
  const mine = typeof block.내_선택 === "number" || typeof block.내_선택 === "string" ? block.내_선택 : null;
  const [picked, setPicked] = useState<number | string | null>(null);
  const [busy, setBusy] = useState(false);
  const isPlayer = state.나.역할 === "플레이어";
  const chosen = picked ?? mine;
  const nameOf = (value: unknown) => items.find((i) => i.값 === value)?.이름 ?? "";

  return (
    <section className="block" aria-label={text(block.이름)}>
      <Title block={block} />
      {text(block.질문) && <p>{text(block.질문)}</p>}
      <ul className="choice-list">
        {items.map((item, index) => (
          <li key={index}>
            <button
              type="button"
              className={`choice${chosen === item.값 ? " on" : ""}`}
              aria-pressed={chosen === item.값}
              disabled={!isPlayer || item.비활성 === true || busy}
              onClick={() => setPicked(item.값 as number | string)}
            >
              <strong>{text(item.이름) || "이름 없음"}</strong>
              {!item.기타 && (
                <span className="muted">{[item.직업, item.나이 != null ? `${item.나이}세` : null, item.성별].filter(Boolean).join(" · ")}</span>
              )}
              {mine === item.값 && <span className="chip accent">내 투표</span>}
            </button>
          </li>
        ))}
      </ul>
      {isPlayer ? (
        <div className="row start">
          <button
            type="button"
            disabled={busy || chosen === null || chosen === mine}
            onClick={async () => {
              setBusy(true);
              const ok = await onAnswer(text(block.질문ID), chosen);
              setBusy(false);
              if (ok) setPicked(null);
            }}
          >
            {mine === null ? "투표" : "투표 바꾸기"}
          </button>
          <span className="muted">
            {mine === null ? "아직 투표하지 않았습니다." : `${nameOf(mine)}에게 투표했습니다. 다음 단계로 넘어가기 전에는 바꿀 수 있습니다.`}
          </span>
        </div>
      ) : (
        <p className="muted">관전 중에는 투표할 수 없습니다.</p>
      )}
    </section>
  );
}

/** 단서·증언 카드를 앞면이 보이게 늘어놓는다. 위에는 어느 장소에서 얻었는지, 종류가 보인다. 동작이 있으면 카드마다 버튼이 생긴다. */
function CardsBlock({ block, state, onAnswer }: { block: Block; state: GameState; onAnswer: Props["onAnswer"] }) {
  const cards = (block.항목 as Card[] | undefined) ?? [];
  const actions = (block.동작 as string[] | undefined) ?? [];
  const canAct = state.나.역할 === "플레이어" && actions.length > 0 && typeof block.질문ID === "string";
  return (
    <section className="block" aria-label={text(block.이름)}>
      <Title block={block} />
      {cards.length === 0 && <p className="muted">아직 얻은 것이 없습니다.</p>}
      <ul className="clue-cards">
        {cards.map((c, i) => (
          <ClueCard
            key={`${c.종류}-${c.순서 ?? i}`}
            card={c}
            state={state}
            actions={canAct && c.순서 !== undefined && c.공개 !== undefined ? actions : []}
            onSend={(value) => onAnswer(text(block.질문ID), value)}
          />
        ))}
      </ul>
    </section>
  );
}

/** 카드 한 장. 남들에게 보이는 이름 아래에 진짜 이름이 있고, 누르면 내용이 펼쳐진다(내용이 길 수 있어서 처음에는 접혀 있다). */
function ClueCard({ card: c, state, actions, onSend }: {
  card: Card; state: GameState; actions: string[]; onSend: (value: unknown) => Promise<boolean>;
}) {
  const [open, setOpen] = useState(false);
  const shown = c.공개이름 || c.이름;
  const title = (
    <>
      <strong>{shown}</strong>
      {shown !== c.이름 && <span className="muted real-name">{c.이름}</span>}
    </>
  );
  return (
    <li className="clue-card">
      <span className="clue-meta">
        <span className="chip">{c.종류}</span>
        {c.장소 && <span className="muted">{c.장소}</span>}
        {c.주인 && <span className="chip accent">{c.주인}</span>}
      </span>
      {c.내용 ? (
        <button type="button" className="clue-head" aria-expanded={open} onClick={() => setOpen(!open)}>
          {title}
          <span className="muted">{open ? "접기" : "눌러서 내용 보기"}</span>
        </button>
      ) : (
        <div className="clue-head">{title}</div>
      )}
      {open && <p className="prose">{c.내용}</p>}
      {c.공개 !== undefined && <SharedWith card={c} state={state} />}
      {actions.length > 0 && <CardActions card={c} actions={actions} state={state} onSend={onSend} />}
    </li>
  );
}

const nickname = (state: GameState, account: number) => state.플레이어.find((p) => p.계정_번호 === account)?.닉네임 ?? "알 수 없음";

function SharedWith({ card, state }: { card: Card; state: GameState }) {
  if (card.공개 === "전체") return <span className="muted">모두에게 공개 중</span>;
  if (!card.공개 || card.공개.length === 0) return <span className="muted">공개하지 않음</span>;
  return <span className="muted">공개 대상: {card.공개.map((a) => nickname(state, a)).join(", ")}</span>;
}

function CardActions({ card, actions, state, onSend }: {
  card: Card; actions: string[]; state: GameState; onSend: (value: unknown) => Promise<boolean>;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const others = state.플레이어.filter((p) => p.계정_번호 !== state.나.계정_번호);
  const [shown, setShown] = useState<number[]>(Array.isArray(card.공개) ? card.공개 : []);
  const [everyone, setEveryone] = useState(card.공개 === "전체");
  const [receiver, setReceiver] = useState<number | null>(null);

  async function send(value: unknown) {
    setBusy(true);
    const ok = await onSend(value);
    setBusy(false);
    if (ok) setOpen(null);
  }

  return (
    <div className="clue-actions">
      <div className="row start">
        {actions.includes("보여주기") && (
          <button type="button" className="small secondary" aria-pressed={open === "보여주기"} onClick={() => setOpen(open === "보여주기" ? null : "보여주기")}>
            보여 주기
          </button>
        )}
        {actions.includes("양도") && card.양도가능 !== false && (
          <button type="button" className="small secondary" aria-pressed={open === "양도"} onClick={() => setOpen(open === "양도" ? null : "양도")}>
            양도
          </button>
        )}
      </div>
      {open === "보여주기" && (
        <fieldset className="clue-panel">
          <legend>{card.이름}을(를) 볼 수 있는 사람</legend>
          <label className="check">
            <input type="checkbox" checked={everyone} onChange={(e) => setEveryone(e.target.checked)} />
            모두
          </label>
          {others.map((p) => (
            <label key={p.계정_번호} className="check">
              <input
                type="checkbox"
                disabled={everyone}
                checked={everyone || shown.includes(p.계정_번호)}
                onChange={(e) => setShown(e.target.checked ? [...shown, p.계정_번호] : shown.filter((a) => a !== p.계정_번호))}
              />
              {p.닉네임}
            </label>
          ))}
          <p className="muted">아무도 고르지 않고 적용하면 공개를 취소합니다.</p>
          <button type="button" className="small" disabled={busy} onClick={() => void send({ 동작: "보여주기", 단서: card.순서, 대상: everyone ? "전체" : shown })}>
            적용
          </button>
        </fieldset>
      )}
      {open === "양도" && (
        <fieldset className="clue-panel">
          <legend>{card.이름}을(를) 넘길 사람</legend>
          {others.map((p) => (
            <label key={p.계정_번호} className="check">
              <input type="radio" name={`receiver-${card.순서}`} checked={receiver === p.계정_번호} onChange={() => setReceiver(p.계정_번호)} />
              {p.닉네임}
            </label>
          ))}
          <p className="muted">넘기면 바로 상대의 단서가 되고, 이 단서에 걸린 공개는 사라집니다.</p>
          <button type="button" className="small" disabled={busy || receiver === null} onClick={() => void send({ 동작: "양도", 단서: card.순서, 대상: [receiver] })}>
            넘기기
          </button>
        </fieldset>
      )}
    </div>
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
