/**
 * 한국어 조사(을/를, 이/가, 은/는, 과/와, 으로/로 …)를 앞 낱말의 받침에 맞게 붙인다. 서버의 `app/josa.py` 와 같은 규칙이다.
 * 낱말 끝의 따옴표·괄호 같은 기호는 건너뛰고 마지막 글자로 판단한다. 한글은 받침을 보고, 숫자와 영어 글자는 읽는 소리로 본다.
 */
const PAIRS = {
  "을/를": ["을", "를"], "이/가": ["이", "가"], "은/는": ["은", "는"], "과/와": ["과", "와"],
  "으로/로": ["으로", "로"], "이나/나": ["이나", "나"], "이라/라": ["이라", "라"], "이랑/랑": ["이랑", "랑"], "아/야": ["아", "야"],
} as const;
export type JosaPair = keyof typeof PAIRS;

const DIGIT_FINAL: Record<string, boolean> = { "0": true, "1": true, "2": false, "3": true, "4": false, "5": false, "6": true, "7": true, "8": true, "9": false };
const LATIN_FINAL = new Set(["L", "M", "N", "R"]);   // 엘 엠 엔 알 만 받침이 있다
const LIEUL = 8;                                       // 한글 받침 ㄹ 의 번호

function lastSound(word: string): { hasFinal: boolean; lieul: boolean } | null {
  for (const ch of Array.from(word).reverse()) {
    const code = ch.charCodeAt(0);
    if (code >= 0xac00 && code <= 0xd7a3) {
      const final = (code - 0xac00) % 28;
      return { hasFinal: final !== 0, lieul: final === LIEUL };
    }
    if (ch in DIGIT_FINAL) return { hasFinal: DIGIT_FINAL[ch], lieul: "178".includes(ch) };
    if (/^[A-Za-z]$/.test(ch)) return { hasFinal: LATIN_FINAL.has(ch.toUpperCase()), lieul: ch.toUpperCase() === "L" || ch.toUpperCase() === "R" };
  }
  return null;
}

/** 낱말에 맞는 조사 쪽만. */
export function particle(word: string, pair: JosaPair): string {
  const [withFinal, without] = PAIRS[pair];
  const sound = lastSound(word);
  if (sound === null) return without;
  if (pair === "으로/로") return !sound.hasFinal || sound.lieul ? without : withFinal;
  return sound.hasFinal ? withFinal : without;
}

/** 낱말 뒤에 알맞은 조사를 붙여 돌려준다. 예: josa("커터칼", "을/를") → "커터칼을". */
export function josa(word: string, pair: JosaPair): string {
  return `${word}${particle(word, pair)}`;
}
