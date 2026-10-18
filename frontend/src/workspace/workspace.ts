import { useCallback, useEffect, useState } from "react";

import { errorMessage, http } from "../api/client";

export interface FieldMeta {
  name: string;
  kind: "text" | "long" | "int" | "bool" | "json" | "ref" | "libref" | "ts";
  required: boolean;
  max: number | null;
  min: number | null;
  ref: string | null;
  label: string;
  help: string | null;
  default: unknown;
}

export interface ResourceMeta {
  key: string;
  label: string;
  key_col: string;
  title_fields: string[];
  group_by: string | null;
  help: string | null;
  /** 화면에 따로 보이지 않는 항목(다른 항목의 입력 화면에 합쳐져 있다) */
  hidden?: boolean;
  /** 조합처럼 재료 목록을 함께 입력받는 항목 */
  has_parts?: boolean;
  fields: FieldMeta[];
}

export interface Part {
  종류: "단서" | "증언" | "조합";
  순서: number;
}

export interface Schema {
  resources: ResourceMeta[];
  external: { key: string; label: string; key_col: string; title_fields: string[] }[];
}

export type Row = Record<string, unknown>;

export interface LibraryRef {
  번호: number;
  이름: string;
  버전: number;
  설명: string | null;
  삭제됨: boolean;
  /** 스크립트가 읽는 카드 설정 이름(설정 화면이 보여 줄 입력을 정한다). 기믹에는 없다. */
  사용설정?: string[];
  /** 진행단계 스크립트가 설정정의로 정한 입력칸(없으면 null: 옛 방식) */
  설정정의?: SettingDef[] | null;
  /** 진행단계 스크립트가 조건정의로 정한, 엔딩·후일담 조건으로 고를 수 있는 항목 */
  조건정의?: ConditionDef[];
}

export interface SettingDef {
  키: string;
  이름: string;
  종류: "숫자" | "선택" | "켜짐" | "글" | "여러선택" | "서사" | "공통서사" | "후보" | "질문";
  기본?: unknown;
  최소?: number;
  선택?: [string | number, string][];
  설명?: string;
}

export interface ArgDef {
  키: string;
  이름: string;
  종류: "인물" | "선택" | "기타후보" | "질문인물" | "질문답" | "대상";
  선택?: [string | number, string][];
  /** 질문답: 같은 조건에서 앞서 고르는 인물 인자의 키. 그 밖의 종류: 읽을 카드 설정의 키 */
  인물?: string;
  설정?: string;
}

export interface ConditionDef {
  이름: string;
  식: string;
  인자: ArgDef[];
}

export interface Bundle {
  [key: string]: unknown;
  /** 공통 스토리를 나눈 부분 수(공통 스토리 카드가 보여 줄 부분을 고르는 범위) */
  story?: { 공통스토리_부분수: number };
  /** 시간 칸(타임라인 등)을 어디까지 적을지. 작품 기본정보에서 고른다 */
  time_format?: string;
  library: { phases: Record<string, LibraryRef>; gimmicks: Record<string, LibraryRef> };
}

export interface Workspace {
  schema: Schema;
  bundle: Bundle;
  reload: () => Promise<void>;
}

export function rowsOf(ws: Workspace, key: string): Row[] {
  return (ws.bundle[key] as Row[] | undefined) ?? [];
}

export function metaOf(ws: Workspace, key: string): ResourceMeta {
  const meta = ws.schema.resources.find((r) => r.key === key);
  if (!meta) throw new Error(`알 수 없는 항목 종류: ${key}`);
  return meta;
}

const clip = (s: string, n = 40) => (s.length > n ? `${s.slice(0, n)}…` : s);
/** "페이즈(진행 순서)" 처럼 괄호 설명이 붙은 이름은 앞부분만 쓴다. */
export const shortLabel = (label: string) => label.replace(/\(.*\)/, "").trim();

export function titleOf(titleFields: string[], row: Row): string | null {
  for (const f of titleFields) {
    const v = row[f];
    if (typeof v === "string" && v.trim() !== "") return clip(v);
  }
  return null;
}

/** 다른 항목을 가리키는 값(`순서`)을 사람이 읽는 이름으로 바꾼다. 아직 없는 항목이면 번호만 보여 준다. */
export function refLabel(ws: Workspace, key: string, order: number): string {
  if (key === "phases") return phaseLabel(ws, order);
  const ext = ws.schema.external.find((e) => e.key === key);
  const meta = ext ?? ws.schema.resources.find((r) => r.key === key);
  if (!meta) return String(order);
  const row = rowsOf(ws, key).find((r) => r[meta.key_col] === order);
  const title = row ? titleOf(meta.title_fields, row) : null;
  return title ? `${order}. ${title}` : `${shortLabel(meta.label)} ${order}`;
}

/** 페이즈는 칸 번호가 아니라 흐름 안의 위치(1부터)로 부른다. 칸 번호는 끼워 넣기·옮기기로 위치와 달라질 수 있다. */
export function phaseLabel(ws: Workspace, order: number): string {
  const phases = rowsOf(ws, "phases");
  const i = phases.findIndex((p) => p.순서 === order);
  if (i < 0) return `페이즈 ${order}`;
  const name = phases[i].이름;
  return typeof name === "string" && name.trim() !== "" ? `${i + 1}. ${name}` : `페이즈 ${i + 1}`;
}

export function useWorkspace(workId: number): { ws: Workspace | null; error: string | null } {
  const [schema, setSchema] = useState<Schema | null>(null);
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const res = await http<Bundle>("GET", `/api/works/${workId}/content`);
    if (res.data) setBundle(res.data);
    else setError(errorMessage(res.error, "작업공간을 불러오지 못했습니다"));
  }, [workId]);

  useEffect(() => {
    void (async () => {
      const [s, b] = await Promise.all([
        http<Schema>("GET", "/api/content/schema"),
        http<Bundle>("GET", `/api/works/${workId}/content`),
      ]);
      if (s.data && b.data) {
        setSchema(s.data);
        setBundle(b.data);
      } else setError(errorMessage(s.error ?? b.error, "작업공간을 불러오지 못했습니다"));
    })();
  }, [workId]);

  return { ws: schema && bundle ? { schema, bundle, reload } : null, error };
}
