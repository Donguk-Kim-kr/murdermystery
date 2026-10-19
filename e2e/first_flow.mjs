// 실제 브라우저 3개로 프롤로그 → 캐릭터 선택 → 프로필 숙지를 진행하는 시험. 사용법은 e2e/README.md
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE ?? "playwright");
const OUT = process.argv[2];
const rnd = () => Math.random().toString(36).slice(2, 7);
const BASE = process.env.BASE_URL ?? "http://localhost:8000";
const ids = ["h" + rnd(), "p" + rnd(), "q" + rnd()];
const nicks = ["방장님", "둘째", "셋째"];
const log = (m) => console.log(m);
let failures = 0;
const check = (ok, m) => { log((ok ? "OK   " : "FAIL ") + m); if (!ok) failures++; };
const api = async (path, { method = "GET", token, body } = {}) => {
  const r = await fetch(BASE + path, { method, headers: { "content-type": "application/json", ...(token ? { authorization: "Bearer " + token } : {}) }, body: body ? JSON.stringify(body) : undefined });
  const text = await r.text();
  if (!r.ok) throw new Error(`${method} ${path} ${r.status} ${text}`);
  return text ? JSON.parse(text) : null;
};

const PROLOGUE = `def 실행(카드):
    모두.탭("공통 스토리", 글("공통 스토리", 공통스토리()))
    읽기(모두, "공통 스토리", 공통스토리())
`;
const SELECT = `def 실행(카드):
    모두.보이기(선택지("캐릭터 선택", 인물들(), 1, True))
    모두.보이기(현황("선택 완료", 배정된_플레이어수(), 플레이어수()))
    while 인물_없는_플레이어가_있다():
        입력 = 기다리기("확인")
        if 배정(입력.플레이어, 입력.값):
            모두.보이기(현황("선택 완료", 배정된_플레이어수(), 플레이어수()))
        else:
            입력.플레이어.알림("이미 다른 사람이 고른 인물입니다")

def 진행조건(카드):
    if 인물_없는_플레이어가_있다():
        return 거부("캐릭터 선택이 완료되지 않았습니다.")
    return 통과
`;
const PROFILE = `def 실행(카드):
    for 플레이어 in 플레이어들():
        if 플레이어.인물 is None:
            continue
        내용 = 서사들(플레이어.인물, [1])
        플레이어.탭("개인 서사", 글("개인 서사", 내용))
        읽기(플레이어, "개인 서사", 내용)
`;

// ---- 준비(API) ----
for (let i = 0; i < 3; i++) await api("/api/auth/signup", { method: "POST", body: { 아이디: ids[i], 패스워드: "password123", 닉네임: nicks[i] } });
const tok = (await api("/api/auth/login", { method: "POST", body: { 아이디: ids[0], 패스워드: "password123", 접속환경: "PC" } })).토큰;
const w = await api("/api/works", { method: "POST", token: tok, body: { 제목: "자동 시험 저택", 시놉시스: "시험", 공통스토리: "폭풍우가 치는 밤, 저택에 손님들이 모였다." } });
const secrets = ["서사-의사만의 이야기", "서사-집사만의 이야기", "서사-하녀만의 이야기"];
for (const [i, n] of ["의사", "집사", "하녀"].entries()) await api(`/api/works/${w.번호}/characters`, { method: "POST", token: tok, body: { 이름: n, 직업: n, 서사: secrets[i] } });
const cards = [["프롤로그", PROLOGUE], ["캐릭터 선택", SELECT], ["프로필 숙지", PROFILE]];
for (const [pos, [name, script]] of cards.entries()) {
  const lib = await api("/api/library/phases", { method: "POST", token: tok, body: { 이름: `${name}-${w.번호}`, 설명: name, 규칙: { 스크립트: script } } });
  const made = await api(`/api/works/${w.번호}/phases/insert`, { method: "POST", token: tok, body: { position: pos + 1 } });
  const slot = made.phases[pos].순서;
  await api(`/api/works/${w.번호}/content/phase-steps`, { method: "POST", token: tok, body: { 진행순서_순서: slot, 진행단계_번호: lib.번호 } });
}
await api(`/api/works/${w.번호}/confirm`, { method: "POST", token: tok, body: {} });

const b = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? "/opt/pw-browsers/chromium" });
const mk = async (vp) => { const c = await b.newContext({ viewport: vp }); const p = await c.newPage(); p.on("pageerror", (e) => { failures++; log("PAGEERROR " + e.message); }); p.on("dialog", (d) => d.accept()); return p; };
const login = async (p, id) => { await p.goto(BASE); await p.getByLabel("아이디").fill(id); await p.getByLabel("패스워드").fill("password123"); await p.getByRole("button", { name: "로그인" }).click(); await p.getByRole("heading", { name: "플레이", exact: true }).waitFor(); };
const pages = [await mk({ width: 1100, height: 900 }), await mk({ width: 390, height: 800 }), await mk({ width: 1000, height: 800 })];
for (const [i, p] of pages.entries()) await login(p, ids[i]);

// ---- 방 ----
const host = pages[0];
await host.getByRole("link", { name: "방 만들기" }).first().click();
await host.getByRole("button", { name: "방 만들기" }).click();
const code = (await host.getByLabel("입장코드", { exact: false }).locator("xpath=self::strong").textContent()).trim();
for (const p of pages.slice(1)) {
  await p.goto(BASE + "/rooms/join");
  await p.getByLabel("입장코드").fill(code);
  await p.getByRole("button", { name: "입장" }).click();
  await p.getByRole("region", { name: "참가자" }).waitFor();
}
await host.getByText("3/3명").waitFor({ timeout: 8000 });
log("방 준비 완료: " + code);

// ---- 시작 ----
await host.getByRole("button", { name: "게임 시작" }).click();
for (const p of pages) await p.getByRole("heading", { name: "프롤로그" }).waitFor({ timeout: 8000 }).catch(() => {});
const titles = await Promise.all(pages.map((p) => p.locator("h1").textContent()));
check(titles.every((t) => t.includes("프롤로그")), "시작하면 모두의 화면이 프롤로그로 바뀐다: " + titles.join(" / "));

// 프롤로그
for (const p of pages) await p.getByText("폭풍우가 치는 밤").first().waitFor({ timeout: 5000 });
check(true, "공통 스토리가 모두에게 보인다");
await pages[1].getByRole("button", { name: "확인" }).click();
await host.getByText("확인 1/3").waitFor({ timeout: 5000 });
check(true, "다른 사람이 확인하면 내 화면의 현황이 실시간으로 바뀐다(1/3)");
await pages[0].getByRole("button", { name: "확인" }).click();
await pages[2].getByRole("button", { name: "확인" }).click();
await pages[1].getByText("확인 3/3").waitFor({ timeout: 5000 });
check(true, "전원 확인 3/3, 단계는 저절로 넘어가지 않는다: " + (await pages[1].locator("h1").textContent()));

// 캐릭터 선택
await host.getByRole("button", { name: "다음 단계" }).click();
for (const p of pages) await p.getByRole("heading", { name: "캐릭터 선택" }).first().waitFor({ timeout: 8000 });
await host.getByRole("button", { name: "다음 단계" }).click();
await host.getByRole("alert").filter({ hasText: "캐릭터 선택이 완료되지 않았습니다" }).waitFor({ timeout: 5000 });
check(true, "아무도 고르기 전에는 넘어갈 수 없고 이유가 보인다");

// 같은 인물을 동시에 확인(먼저 확정되면 다른 사람 화면에서는 그 인물이 곧바로 잠긴다)
for (const p of pages) await p.locator("button.choice", { hasText: /의사/ }).click();
await Promise.allSettled(pages.map((p) => p.getByRole("button", { name: "확인", exact: true }).click({ timeout: 3000 })));
await new Promise((r) => setTimeout(r, 1000));
const mine = await Promise.all(pages.map((p) => p.getByText("내 인물").count()));
check(mine.reduce((a, c) => a + c, 0) === 1, "같은 인물을 동시에 확인해도 한 명만 갖는다: " + mine.join(","));
const losers = pages.filter((_, i) => mine[i] === 0);
const winner = pages.find((_, i) => mine[i] === 1);
for (const p of losers) await p.locator("button.choice", { hasText: /의사/ }).isDisabled().then((d) => check(d, "다른 사람이 고른 인물은 내 화면에서 잠긴다"));
check((await winner.getByText("이미 다른 사람이 고른 인물입니다").count()) === 0, "이긴 사람 화면에는 안내가 없다");

// 나머지 둘이 서로 다른 인물
await losers[0].locator("button.choice", { hasText: /집사/ }).click();
await losers[0].getByRole("button", { name: "확인", exact: true }).click();
await losers[1].locator("button.choice", { hasText: /하녀/ }).click();
await losers[1].getByRole("button", { name: "확인", exact: true }).click();
for (const p of pages) await p.getByText("선택 완료").first().waitFor();
await host.getByText("3/3").first().waitFor({ timeout: 8000 });
await pages[0].screenshot({ path: `${OUT}/game-select-desktop.png` });
await pages[1].screenshot({ path: `${OUT}/game-select-mobile.png` });

// 프로필 숙지
await host.getByRole("button", { name: "다음 단계" }).click();
for (const p of pages) await p.getByRole("heading", { name: "프로필 숙지" }).waitFor({ timeout: 8000 });
const chars = {};
for (const [i, p] of pages.entries()) {
  const t = await p.locator(".game-main").innerText();
  const own = secrets.filter((s) => t.includes(s));
  chars[i] = own[0];
  check(own.length === 1, `${nicks[i]} 화면에는 서사가 정확히 하나만 보인다: ${own[0]}`);
  const whole = await p.content();
  check(secrets.filter((s) => whole.includes(s)).length === 1, `${nicks[i]} 화면 어디에도 다른 사람의 서사가 없다`);
}
check(new Set(Object.values(chars)).size === 3, "세 사람의 서사가 모두 다르다");

// 새로고침 후 복원
await pages[1].reload();
await pages[1].getByRole("heading", { name: "프로필 숙지" }).waitFor({ timeout: 8000 });
check((await pages[1].locator(".game-main").innerText()).includes(chars[1]), "새로고침 후에도 같은 화면과 내 서사가 복원된다");
await pages[1].getByRole("tab", { name: "공통 스토리" }).click();
check((await pages[1].getByText("폭풍우가 치는 밤").count()) > 0, "프롤로그의 공통 스토리가 탭으로 남아 있다");
await pages[0].screenshot({ path: `${OUT}/game-profile-desktop.png` });
await pages[1].screenshot({ path: `${OUT}/game-profile-mobile.png` });

await b.close();
log(failures ? `실패 ${failures}건` : "모두 통과");
process.exit(failures ? 1 : 0);
