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
  fields: FieldMeta[];
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
}

export interface Bundle {
  [key: string]: unknown;
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
