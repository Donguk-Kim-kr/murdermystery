import { useEffect, useRef, useState } from "react";

import { http } from "../api/client";

interface Check {
  정상: boolean;
  오류: string | null;
  줄: number | null;
  함수: string[];
}

interface Reference {
  함수: string[];
  상수: string[];
  기본_함수: string[];
}

interface Props {
  value: string;
  onChange(value: string): void;
  /** 검사 결과가 바뀔 때마다 알린다(오류가 있으면 false). 검사 중에는 false. */
  onValid(valid: boolean): void;
}

const DELAY_MS = import.meta.env.MODE === "test" ? 20 : 500;

/** 진행단계 스크립트 입력칸. 입력을 멈추면 서버에서 검사하고(실행은 하지 않는다) 문법 오류와 없는 이름을 줄 번호와 함께 알린다. */
export function ScriptEditor({ value, onChange, onValid }: Props) {
  const [check, setCheck] = useState<Check | null>(null);
  const [failed, setFailed] = useState(false);
  const [reference, setReference] = useState<Reference | null>(null);
  const seq = useRef(0);

  useEffect(() => {
    const mine = ++seq.current;
    onValid(false);
    setFailed(false);
    const id = setTimeout(async () => {
      const res = await http<Check>("POST", "/api/scripts/check", { 스크립트: value });
      if (mine !== seq.current) return; // 더 새 입력의 검사가 진행 중이다
      if (res.data) {
        setCheck(res.data);
        onValid(res.data.정상);
      } else {
        setCheck(null);
        setFailed(true);
      }
    }, DELAY_MS);
    return () => clearTimeout(id);
    // onValid 는 부모가 매번 새로 만들 수 있어 의존성에서 뺀다(값이 바뀔 때만 검사한다).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  async function loadReference() {
    if (reference) return;
    const res = await http<Reference>("GET", "/api/scripts/reference");
    if (res.data) setReference(res.data);
  }

  const blank = value.trim() === "";
  return (
    <div className="script-editor">
      <label>
        스크립트 (비워 두면 이 진행단계는 아무 일도 하지 않습니다)
        <textarea
          rows={10}
          spellCheck={false}
          className="code"
          aria-label="스크립트"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={"def 실행(카드):\n    모두.보이기(글(\"안녕하세요\"))"}
        />
      </label>
      {failed && <p role="alert" className="error">스크립트를 검사하지 못했습니다. 네트워크를 확인해 주세요.</p>}
      {check && !check.정상 && (
        <p role="alert" className="error">
          {check.줄 ? `${check.줄}번째 줄: ` : ""}
          {check.오류}
        </p>
      )}
      {check?.정상 && !blank && (
        <p role="status" className="muted">
          검사 통과 · 정의한 함수: {check.함수.join(", ") || "없음"}
          {!check.함수.includes("실행") && " (실행 함수가 없어 페이즈가 시작해도 아무 일도 하지 않습니다)"}
        </p>
      )}
      <details onToggle={() => void loadReference()}>
        <summary>쓸 수 있는 이름</summary>
        {reference ? (
          <p className="muted">
            함수: {reference.함수.join(", ")}
            <br />
            값: {reference.상수.join(", ")}
            <br />
            파이썬 기본: {reference.기본_함수.join(", ")}
          </p>
        ) : (
          <p className="muted">불러오는 중…</p>
        )}
      </details>
    </div>
  );
}
