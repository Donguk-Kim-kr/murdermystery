// 페이즈 카드를 끌기 시작하는 순간(0.3초 안)에 다른 카드가 밀리거나 빈자리가 엉뚱하게 열리지 않는지 보는 시험. 사용법은 e2e/README.md
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE ?? "playwright");
const BASE = process.env.BASE_URL ?? "http://localhost:8000";
const id = "d" + Math.random().toString(36).slice(2, 7);
let failures = 0;
const check = (ok, m) => { console.log((ok ? "OK   " : "FAIL ") + m); if (!ok) failures++; };
const api = async (path, { method = "GET", token, body } = {}) => {
  const r = await fetch(BASE + path, { method, headers: { "content-type": "application/json", ...(token ? { authorization: "Bearer " + token } : {}) }, body: body ? JSON.stringify(body) : undefined });
  const text = await r.text();
  if (!r.ok) throw new Error(`${method} ${path} ${r.status} ${text}`);
  return text ? JSON.parse(text) : null;
};
await api("/api/auth/signup", { method: "POST", body: { 아이디: id, 패스워드: "password123", 닉네임: "끌기" } });
const tok = (await api("/api/auth/login", { method: "POST", body: { 아이디: id, 패스워드: "password123", 접속환경: "PC" } })).토큰;
const lib = (await api("/api/library/phases", { token: tok })).filter((p) => p.공통).sort((a, b) => b.버전 - a.버전);
const pick = (n) => lib.find((p) => p.이름 === n).번호;
const w = (await api("/api/works", { method: "POST", token: tok, body: { 제목: "끌기 시험" } })).번호;
for (const [i, n] of ["프롤로그", "캐릭터 선택", "프로필 숙지", "자기소개", "조사"].entries()) {
  const made = await api(`/api/works/${w}/phases/insert`, { method: "POST", token: tok, body: { position: i + 1 } });
  await api(`/api/works/${w}/content/phase-steps`, { method: "POST", token: tok, body: { 진행순서_순서: made.phases[i].순서, 진행단계_번호: pick(n) } });
}
const b = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? "/opt/pw-browsers/chromium" });
const p = await (await b.newContext({ viewport: { width: 1100, height: 900 } })).newPage();
await p.goto(BASE);
await p.getByLabel("아이디").fill(id); await p.getByLabel("패스워드").fill("password123");
await p.getByRole("button", { name: "로그인" }).click();
await p.getByRole("heading", { name: "플레이", exact: true }).waitFor();
await p.goto(`${BASE}/works/${w}`);
const tile = p.getByRole("listitem", { name: "페이즈 2" });
await tile.waitFor();
const box = await tile.boundingBox();
const state = () => p.evaluate(() => ({
  open: [...document.querySelectorAll(".flow-slot.open")].map((s) => s.dataset.index),
  collapsed: document.querySelectorAll("li.phase.collapsed").length,
  widths: [...document.querySelectorAll("ol.flow > li.phase")].map((t) => Math.round(t.getBoundingClientRect().width)),
}));
// 카드의 오른쪽 절반을 잡고 조금(8px)만 움직인다: 제자리를 벗어나지 않았으므로 아무것도 옮겨지면 안 된다
for (const grab of [0.8, 0.2, 0.5]) {
  await p.mouse.move(box.x + box.width * grab, box.y + 30);
  await p.mouse.down();
  await p.mouse.move(box.x + box.width * grab + 8, box.y + 30, { steps: 2 });
  const seen = [];
  for (let i = 0; i < 8; i++) { seen.push(await state()); await p.waitForTimeout(40); }
  const moved = seen.some((s) => s.collapsed > 0 || s.open.some((o) => o !== "1"));
  check(!moved, `카드의 ${Math.round(grab * 100)}% 지점을 잡고 8px 움직여도 다른 카드가 밀리지 않는다 ${moved ? JSON.stringify(seen.find((s) => s.collapsed > 0 || s.open.some((o) => o !== "1"))) : ""}`);
  await p.mouse.up();
  await p.waitForTimeout(300);
}
// 실제로 다른 자리로 옮기면 순서가 바뀐다(위의 고침이 끌기 자체를 막지 않았는지)
const order = () => p.evaluate(() => [...document.querySelectorAll("ol.flow > li.phase .tile-name")].map((t) => t.textContent));
const before = await order();
const target = await p.getByRole("listitem", { name: "페이즈 4" }).boundingBox();
await p.mouse.move(box.x + box.width * 0.8, box.y + 30);
await p.mouse.down();
await p.mouse.move(target.x + target.width * 0.8, target.y + 30, { steps: 12 });
await p.waitForTimeout(400);
await p.mouse.up();
await p.waitForTimeout(600);
const after = await order();
check(JSON.stringify(after) === JSON.stringify([before[0], before[2], before[3], before[1], before[4]]), `둘째 카드를 넷째 카드 뒤로 옮기면 순서가 바뀐다 (${before.join(" · ")} → ${after.join(" · ")})`);
await b.close();
console.log(failures ? `실패 ${failures}건` : "모두 통과");
process.exit(failures ? 1 : 0);
