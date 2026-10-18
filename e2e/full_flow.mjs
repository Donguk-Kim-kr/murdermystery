// 실제 브라우저 3개로 공통 진행단계 12개 전체(공통 스토리 … 전체 공개)를 진행하는 시험. 사용법은 e2e/README.md
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

// ---- 작품 만들기(제작 API) ----
for (let i = 0; i < 3; i++) await api("/api/auth/signup", { method: "POST", body: { 아이디: ids[i], 패스워드: "password123", 닉네임: nicks[i] } });
const tok = (await api("/api/auth/login", { method: "POST", body: { 아이디: ids[0], 패스워드: "password123", 접속환경: "PC" } })).토큰;
const latest = {};
for (const p of (await api("/api/library/phases", { token: tok })).filter((p) => p.공통)) if (!latest[p.이름] || latest[p.이름].버전 < p.버전) latest[p.이름] = p;
const lib = Object.fromEntries(Object.entries(latest).map(([n, p]) => [n, p.번호]));
const flow = [["공통 스토리"], ["캐릭터 선택"], ["프로필 숙지"], ["자기소개"], ["조사", { 횟수: 2 }], ["토론"], ["밀담"], ["추리 발표"], ["최종 투표", { 후보: [1, 2, 3, "사고사"] }], ["엔딩"], ["후일담"], ["전체 공개"]];
for (const [n] of flow) if (!lib[n]) throw new Error("공통 진행단계가 없습니다: " + n);
const w = await api("/api/works", { method: "POST", token: tok, body: { 제목: "전체 흐름 시험", 시놉시스: "시험", 공통스토리: "폭풍우가 치는 밤, 저택에 손님들이 모였다." } });
const W = w.번호;
const names = ["의사", "집사", "하녀"];
for (const [i, n] of names.entries()) await api(`/api/works/${W}/characters`, { method: "POST", token: tok, body: { 이름: n, 직업: n, 소개: i === 0 ? "마을의 의사입니다." : null, 서사_부분: [{ 본문: `${n}의 서사 첫째` }, { 본문: `${n}의 서사 둘째` }] } });
const content = (kind, body) => api(`/api/works/${W}/content/${kind}`, { method: "POST", token: tok, body });
const mansion = (await content("places", { 이름: "저택" })).순서;
const study = (await content("places", { 이름: "서재", 상위_장소_순서: mansion })).순서;
const kitchen = (await content("places", { 이름: "주방", 상위_장소_순서: mansion })).순서;
const garden = (await content("places", { 이름: "정원" })).순서;
await content("clues", { 이름: "찢어진 편지", 공개이름: "서랍 속 종이", 내용: "편지 내용입니다", 장소_순서: study });
await content("clues", { 이름: "깨진 안경", 내용: "안경 내용입니다", 장소_순서: study });
await content("clues", { 이름: "독이 든 컵", 내용: "컵 내용입니다", 장소_순서: kitchen });
await content("testimonies", { 이름: "정원사의 증언", 공개이름: "정원사", 내용: "그날 밤 누군가를 보았습니다", 장소_순서: garden });
await content("endings", { 이름: "구속 성공", 조건: { 식: '결과_인물("최종 투표") is not None' }, 내용: "범인이 잡혔습니다." });
await content("endings", { 이름: "구속 실패", 조건: { 식: '결과_인물("최종 투표") is None' }, 내용: "범인이 달아났습니다." });
await content("epilogues", { 내용: "모두의 이후 이야기" });
for (const [i, [n, settings]] of flow.entries()) {
  const made = await api(`/api/works/${W}/phases/insert`, { method: "POST", token: tok, body: { position: i + 1 } });
  await api(`/api/works/${W}/content/phase-steps`, { method: "POST", token: tok, body: { 진행순서_순서: made.phases[i].순서, 진행단계_번호: lib[n], ...(settings ? { 설정: settings } : {}) } });
}
await api(`/api/works/${W}/confirm`, { method: "POST", token: tok, body: {} });

// ---- 브라우저 ----
const b = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? "/opt/pw-browsers/chromium" });
const mk = async (vp) => { const c = await b.newContext({ viewport: vp }); const p = await c.newPage(); p.on("pageerror", (e) => { failures++; log("PAGEERROR " + e.message); }); p.on("dialog", (d) => d.accept()); return p; };
const login = async (p, id) => { await p.goto(BASE); await p.getByLabel("아이디").fill(id); await p.getByLabel("패스워드").fill("password123"); await p.getByRole("button", { name: "로그인" }).click(); await p.getByRole("heading", { name: "플레이", exact: true }).waitFor(); };
const pages = [await mk({ width: 1100, height: 900 }), await mk({ width: 390, height: 800 }), await mk({ width: 1000, height: 800 })];
for (const [i, p] of pages.entries()) await login(p, ids[i]);
const [host, p1, p2] = pages;
await host.getByRole("link", { name: "방 만들기" }).first().click();
await host.getByRole("button", { name: "방 만들기" }).click();
const code = (await host.getByLabel("입장코드", { exact: false }).locator("xpath=self::strong").textContent()).trim();
for (const p of pages.slice(1)) { await p.goto(BASE + "/rooms/join"); await p.getByLabel("입장코드").fill(code); await p.getByRole("button", { name: "입장하기" }).click(); await p.getByRole("region", { name: "참가자" }).waitFor(); }
await host.getByText("플레이어 3/3명").waitFor({ timeout: 8000 });
await host.getByRole("button", { name: "게임 시작" }).click();

const title = (p) => p.locator("h1").first().textContent();
const waitTitle = async (name) => { for (const p of pages) await p.locator("h1", { hasText: name }).first().waitFor({ timeout: 10000 }); };
const next = async (name) => { await host.getByRole("button", { name: "다음 단계" }).click(); await waitTitle(name); };
const text = (p) => p.locator("main").innerText();

await waitTitle("공통 스토리");
for (const p of pages) await p.getByRole("button", { name: "확인", exact: true }).click();
await host.getByText("확인 3/3").waitFor({ timeout: 8000 });
check(true, "프롤로그: 전원 확인 3/3");
await next("캐릭터 선택");
for (const [i, p] of pages.entries()) { await p.getByRole("button", { name: new RegExp(names[i]) }).first().click(); await p.getByRole("button", { name: "확인", exact: true }).click(); await p.getByText("내 인물").waitFor({ timeout: 8000 }); }
check(true, "캐릭터 선택: 각자 다른 인물을 확정");
await next("프로필 숙지");
for (const [i, p] of pages.entries()) check((await text(p)).includes(`${names[i]}의 서사 첫째`) && !(await text(p)).includes(`${names[(i + 1) % 3]}의 서사 첫째`), `프로필 숙지: ${nicks[i]} 는 자기 서사만 본다`);
await next("자기소개");
await pages[2].getByRole("tab", { name: "자기소개" }).click();
check((await text(pages[2])).includes("마을의 의사입니다."), "자기소개: 소개 멘트가 모두에게 보인다");
await next("조사");
const pick = async (p, item) => { await p.getByRole("button", { name: new RegExp(item) }).click(); };      // 장소가 아니라 단서·증언을 직접 고른다
await pick(host, "서랍 속 종이"); await host.getByText("'서랍 속 종이'를 획득했습니다").first().waitFor({ timeout: 8000 }).catch(() => {});
let greyed = false;
for (let i = 0; i < 40 && !greyed; i++) { greyed = await p1.getByRole("button", { name: /서랍 속 종이/ }).isDisabled().catch(() => false); if (!greyed) await p1.waitForTimeout(200); }
check(greyed, "조사: 다른 사람이 가져간 단서는 회색(고를 수 없음)이다");
await pick(p1, "깨진 안경"); await pick(p2, "정원사");
const openFolds = async (p) => { const closed = p.locator(".fold-head[aria-expanded=false]"); while (await closed.count() > 0) await closed.first().click(); };
const openCards = async (p) => { const closed = p.getByRole("button", { name: /눌러서 내용 보기/ }); while (await closed.count() > 0) await closed.first().click(); };
await host.getByRole("tab", { name: "내 단서" }).click();
check((await text(host)).includes("서랍 속 종이") && !(await text(host)).includes("편지 내용입니다"), "조사: 방장이 단서를 얻었고 공개이름만 먼저 보이며 내용은 접혀 있다");
await openCards(host);
check((await text(host)).includes("편지 내용입니다") && (await text(host)).includes("찢어진 편지"), "조사: 카드를 누르면 진짜 이름과 내용이 보인다");
await p1.getByRole("tab", { name: "내 단서" }).click(); await openCards(p1);
check((await text(p1)).includes("안경 내용입니다") && !(await text(p1)).includes("편지 내용입니다"), "조사: 둘째는 다음 단서(깨진 안경)만 얻었다");
await p2.getByRole("tab", { name: "내 단서" }).click(); await openCards(p2);
check((await text(p2)).includes("그날 밤 누군가를 보았습니다") && !(await text(p2)).includes("편지 내용입니다"), "조사: 셋째는 정원의 증언을 얻었고 남의 단서는 모른다");
await pages[0].screenshot({ path: `${OUT}/full-investigate.png` });
await next("토론");
// 방장이 편지를 둘째에게 보여 준다
await host.getByRole("tab", { name: "내 단서" }).click();
await host.getByRole("button", { name: "보여 주기" }).click();
await host.getByRole("checkbox", { name: "둘째" }).check();
await host.getByRole("button", { name: "적용" }).click();
await p1.getByRole("tab", { name: "공개 단서" }).click();
await p1.getByRole("button", { name: /눌러서 내용 보기/ }).first().waitFor({ timeout: 8000 }); await openCards(p1);
await p1.getByText("편지 내용입니다").waitFor({ timeout: 8000 });
check(true, "토론: 방장이 보여 준 단서가 둘째에게만 보인다");
await p2.getByRole("tab", { name: "공개 단서" }).click(); await openCards(p2);
check(!(await text(p2)).includes("편지 내용입니다"), "토론: 셋째에게는 보이지 않는다");
// 셋째에게 양도
await host.getByRole("button", { name: "양도" }).click();
await host.getByRole("radio", { name: "셋째" }).check();
await host.getByRole("button", { name: "넘기기" }).click();
await p2.getByRole("tab", { name: "내 단서" }).click();
await p2.getByRole("button", { name: /눌러서 내용 보기/ }).first().waitFor({ timeout: 8000 }); await openCards(p2);
await p2.getByText("편지 내용입니다").waitFor({ timeout: 8000 });
check(true, "토론: 양도하면 바로 셋째의 단서가 된다");
await p1.getByRole("tab", { name: "공개 단서" }).click();
check(!(await text(p1)).includes("편지 내용입니다"), "토론: 양도하면 둘째에게 보여 준 공개는 사라진다");
await pages[1].screenshot({ path: `${OUT}/full-discussion-mobile.png` });
await next("밀담");
check((await text(p1)).includes("밀담 가능"), "밀담: 밀담 가능 표시");
await next("추리 발표");
check((await text(p1)).includes("추리 발표 중"), "추리 발표: 추리 발표 중 표시");
await next("최종 투표");
const vote = async (p, who) => { try { await p.getByRole("button", { name: new RegExp(who) }).first().click({ timeout: 8000 }); } catch (e) { console.log("투표 화면:", (await text(p)).slice(0, 2000)); await p.screenshot({ path: `${OUT}/vote-fail.png` }); throw e; } await p.getByRole("button", { name: /^투표/ }).click(); };
await vote(host, "사고사"); await host.getByText("사고사에게 투표했습니다").waitFor({ timeout: 8000 });
await p1.getByText("투표 완료").first().waitFor({ timeout: 8000 });
check((await text(p1)).includes("1/3"), "최종 투표: 한 명이 투표하면 다른 사람 화면에 1/3 이 보인다");
await vote(p1, "사고사"); await vote(p2, "사고사");
await host.getByText("3/3").first().waitFor({ timeout: 8000 });
check(!(await text(p2)).includes("내 투표: 집사"), "최종 투표: 남이 누구에게 투표했는지는 보이지 않는다");
await vote(host, "집사"); await host.getByText("집사에게 투표했습니다").waitFor({ timeout: 8000 });
await vote(host, "사고사"); await host.getByText("사고사에게 투표했습니다").waitFor({ timeout: 8000 });
check(true, "최종 투표: 다음 단계 전에는 바꿀 수 있다");
await pages[0].screenshot({ path: `${OUT}/full-vote.png` });
await next("엔딩");
for (const [i, p] of pages.entries()) { const t = await text(p); check(t.includes("범인이 달아났습니다.") && !t.includes("범인이 잡혔습니다."), `엔딩: ${nicks[i]} 화면에 조건에 맞는 엔딩만 보인다`); }
await next("후일담");
check((await text(p1)).includes("모두의 이후 이야기"), "후일담: 조건 없는 후일담이 보인다");
await p1.getByRole("tab", { name: "결말" }).click();
check(await p1.getByRole("group", { name: "엔딩" }).isVisible() && await p1.getByRole("group", { name: "후일담" }).isVisible(), "결말: 엔딩과 후일담이 한 탭의 두 구역에 모인다");
await next("전체 공개");
await p1.getByRole("tab", { name: "전체 단서" }).click(); await openFolds(p1);
const all = await text(p1);
check(all.includes("편지 내용입니다") && all.includes("컵 내용입니다") && all.includes("그날 밤 누군가를 보았습니다"), "전체 공개: 아무도 얻지 못한 단서까지 모든 단서가 보인다");
await p1.screenshot({ path: `${OUT}/full-all-clues.png` });
await p1.getByRole("tab", { name: "전체 서사" }).click(); await openFolds(p1);
const story = await text(p1);
check(story.includes("의사의 서사 둘째") && story.includes("하녀의 서사 둘째"), "전체 공개: 모든 인물의 서사가 보인다");
check((await host.getByText("게임 종료").count()) > 0 && (await host.getByRole("button", { name: "다음 단계" }).count()) === 0, "전체 공개: 게임 종료 표시, 진행 버튼 없음");
await pages[0].screenshot({ path: `${OUT}/full-end.png` });
await b.close();
log(failures ? `실패 ${failures}건` : "모두 통과");
process.exit(failures ? 1 : 0);
