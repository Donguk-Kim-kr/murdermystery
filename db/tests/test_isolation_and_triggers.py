"""제작용 콘텐츠 ↔ 게임 기록 분리(요구사항 4, 5), 삭제 정책, 트리거, JSONB 자유 형식 테스트."""
from __future__ import annotations

import unittest

from builders import Builders

CONTENT_TABLES = [
    "진행순서", "진행구성", "기믹적용", "인물", "관계", "장소", "단서", "증언", "조합", "조합재료",
    "사건", "사건설명", "엔딩분기", "후일담", "타임라인", "투표", "미디어", "자료",
]
RUNTIME_TABLES = ["방", "진행", "참여", "기믹실행", "투표결과", "엔딩", "획득"]


class Scenario(Builders):
    """모든 제작용 콘텐츠 테이블에 데이터가 있는 작품을 만든다."""

    def full_content(self, w):
        phase, gim = self.phase(), self.gimmick()
        self.step(w, 1), self.step(w, 2)
        self.ins("진행구성", 작품_번호=w, 진행순서_순서=1, 진행단계_번호=phase)
        self.applied_gimmick(w, 1, 1, gim)
        self.character(w, 1), self.character(w, 2, NPC=True)
        self.ins("관계", 작품_번호=w, 인물_순서=1, 대상_인물_순서=2, 관계="친구")
        self.place(w, 1), self.place(w, 2, 상위_장소_순서=1)
        self.clue(w, 1, 인물_순서=1, 장소_순서=1)
        self.witness(w, 1, 인물_순서=2, 장소_순서=2)
        self.combo(w, 1), self.combo(w, 2)
        self.ins("조합재료", 작품_번호=w, 결과_조합_순서=2, 단서_순서=1)
        self.ins("조합재료", 작품_번호=w, 결과_조합_순서=2, 조합_순서=1)
        self.incident(w, 1, 설명="살인")
        self.ins("사건설명", 작품_번호=w, 사건_순서=1, 인물_순서=2, 상태="사망")
        self.ins("엔딩분기", 작품_번호=w, 순서=1, 이름="엔딩", 조건={}, 내용="엔딩")
        self.ins("후일담", 작품_번호=w, 순서=1, 인물_순서=1, 내용="후일담")
        self.ins("타임라인", 작품_번호=w, 순서=1, 설명="진상")
        self.ins("자료", 작품_번호=w, 순서=1, 제목="프롤로그 이후", 내용="기믹이 보여 줄 글")
        self.vote(w, 1, 2)
        self.media(w, 1, 단서_순서=1, 증언_순서=1, 조합_순서=1, 진행순서_순서=1)
        for t in CONTENT_TABLES:
            self.assertGreater(self.count(t, f'"작품_번호"={w}'), 0, f"{t} 에 데이터가 없음")
        return phase, gim

    def wipe_content(self, w):
        """제작자가 콘텐츠를 모두 지우는 상황. FK 의존 순서(자식 → 부모)대로 삭제한다."""
        for t in ["자료", "미디어", "투표", "조합재료", "사건설명", "후일담", "엔딩분기", "타임라인", "관계",
                  "기믹적용", "진행구성", "증언", "단서", "조합", "사건", "장소", "인물", "진행순서"]:
            self.db.ok(f'DELETE FROM "{t}" WHERE "작품_번호"={w}')


class TestRuntimeIsIndependentFromAuthoringContent(Scenario):
    def play_records(self, w):
        """확정 버전 + 게임 + 모든 종류의 실행 기록을 만든다."""
        self.version(w, "1.0", scenario={"인물": [{"순서": 1}, {"순서": 2}], "단서": [{"순서": 1}]})
        room = self.room(w, "1.0")
        g = self.game(room, w, "1.0", 진행순서_순서=1)
        pa, pb = self.participant(w, g, 인물_순서=1), self.participant(w, g, 인물_순서=2)
        self.ins("획득", 작품_번호=w, 진행_번호=g, 참여_번호=pa, 단서_순서=1, 진행순서_순서=1, 획득방법="조사")
        self.ins("획득", 작품_번호=w, 진행_번호=g, 참여_번호=pb, 증언_순서=1, 진행순서_순서=1, 획득방법="조사")
        self.ins("획득", 작품_번호=w, 진행_번호=g, 참여_번호=pb, 조합_순서=1, 진행순서_순서=2, 획득방법="조합")
        self.ins("기믹실행", 작품_번호=w, 진행_번호=g, 기믹적용_순서=1, 실행여부=True, 결과={"ok": True})
        self.ins("투표결과", 작품_번호=w, 투표이름="투표1", 참여_번호=pa, 선택="인물2")
        self.ins("엔딩", 작품_번호=w, 진행_번호=g, 순서=1, 엔딩분기_순서=1)
        self.ins("엔딩", 작품_번호=w, 진행_번호=g, 순서=2, 후일담_순서=1)
        return g

    def snapshot_of_records(self):
        out = {}
        for t in RUNTIME_TABLES + ["버전"]:
            out[t] = self.db.val(
                f'SELECT md5(coalesce(string_agg(x::text, \'|\' ORDER BY "번호"), \'\')) FROM "{t}" x')
        return out

    def test_runtime_tables_have_no_fk_to_authoring_content(self):
        rows = self.db.rows(
            """SELECT cl.relname, fcl.relname
               FROM pg_constraint c
               JOIN pg_class cl  ON cl.oid = c.conrelid
               JOIN pg_class fcl ON fcl.oid = c.confrelid
               WHERE c.contype='f' AND cl.relname = ANY(%s)""" % ("ARRAY[" + ",".join(f"'{t}'" for t in RUNTIME_TABLES) + "]")
        )
        content = set(CONTENT_TABLES) | {"진행단계", "기믹"}
        bad = [(c, p) for c, p in rows if p in content]
        self.assertEqual(bad, [], "게임 실행 테이블이 제작용 콘텐츠 테이블을 참조함")

    def test_wiping_all_authoring_content_does_not_touch_play_records(self):
        w = self.work()
        phase, gim = self.full_content(w)
        self.play_records(w)
        before = self.snapshot_of_records()
        self.wipe_content(w)                                   # 제작용 콘텐츠 전부 삭제
        self.db.ok(f'DELETE FROM "진행단계" WHERE "번호"={phase}')   # 라이브러리 항목도 삭제
        self.db.ok(f'DELETE FROM "기믹" WHERE "번호"={gim}')
        self.assertEqual(self.snapshot_of_records(), before)
        for t in CONTENT_TABLES:
            self.assertEqual(self.count(t, f'"작품_번호"={w}'), 0)

    def test_editing_authoring_content_does_not_touch_play_records(self):
        w = self.work()
        self.full_content(w)
        self.play_records(w)
        before = self.snapshot_of_records()
        self.db.ok(f'''UPDATE "인물" SET "이름"='개명', "범인"=TRUE, "비밀"='바뀜' WHERE "작품_번호"={w};
                       UPDATE "단서" SET "이름"='바뀐 단서', "내용"='바뀜' WHERE "작품_번호"={w};
                       UPDATE "엔딩분기" SET "내용"='바뀜', "조건"='{{"new": 1}}' WHERE "작품_번호"={w};
                       UPDATE "작품" SET "제목"='바뀐 제목', "최신버전"='2.0', "상태"='수정' WHERE "번호"={w};''')
        self.assertEqual(self.snapshot_of_records(), before)

    def test_new_version_does_not_change_games_on_old_version(self):
        w = self.work()
        self.version(w, "1.0", scenario={"v": 1})
        g = self.game(self.room(w, "1.0"), w, "1.0")
        self.version(w, "1.1", scenario={"v": 2}, 변경사항="수정")
        self.assertEqual(self.db.val(f'SELECT "버전_버전" FROM "진행" WHERE "번호"={g}'), "1.0")
        self.assertEqual(self.db.val(f'SELECT "시나리오"->>\'v\' FROM "버전" WHERE "작품_번호"={w} AND "버전"=\'1.0\''), "1")

    def test_work_with_games_cannot_be_deleted(self):
        w = self.work()
        self.full_content(w)
        self.play_records(w)
        err = self.db.fails(f'DELETE FROM "작품" WHERE "번호"={w}')
        self.assertIn("foreign key constraint", err)
        self.assertGreater(self.count("버전", f'"작품_번호"={w}'), 0)
        self.assertGreater(self.count("인물", f'"작품_번호"={w}'), 0)    # 실패했으므로 아무것도 지워지지 않음
        self.db.fails(f'DELETE FROM "버전" WHERE "작품_번호"={w}', "foreign key constraint")


class TestDeletePolicies(Scenario):
    def test_deleting_work_without_games_removes_all_its_content_and_versions(self):
        """작품 삭제 CASCADE 가 NO ACTION/RESTRICT 참조와 충돌하지 않는지 확인 (미디어/투표/기믹적용 포함)."""
        w, other = self.work(), self.work()
        self.full_content(w)
        self.version(w)
        self.full_content(other)
        self.db.ok(f'DELETE FROM "작품" WHERE "번호"={w}')
        for t in CONTENT_TABLES + ["버전"]:
            self.assertEqual(self.count(t, f'"작품_번호"={w}'), 0, t)
            self.assertGreater(self.count(t, f'"작품_번호"={other}') if t != "버전" else 1, 0, t)   # 다른 작품은 그대로

    def test_referenced_character_cannot_be_deleted_until_references_removed(self):
        w = self.work()
        self.character(w, 1), self.clue(w, 1, 인물_순서=1)
        self.db.fails(f'DELETE FROM "인물" WHERE "작품_번호"={w} AND "순서"=1', "foreign key constraint")
        self.db.ok(f'DELETE FROM "단서" WHERE "작품_번호"={w}')
        self.db.ok(f'DELETE FROM "인물" WHERE "작품_번호"={w} AND "순서"=1')

    def test_deleting_character_removes_its_relationships(self):
        w = self.work()
        self.character(w, 1), self.character(w, 2), self.character(w, 3)
        self.ins("관계", 작품_번호=w, 인물_순서=1, 대상_인물_순서=2, 관계="a")
        self.ins("관계", 작품_번호=w, 인물_순서=2, 대상_인물_순서=1, 관계="b")
        self.ins("관계", 작품_번호=w, 인물_순서=2, 대상_인물_순서=3, 관계="c")
        self.db.ok(f'DELETE FROM "인물" WHERE "작품_번호"={w} AND "순서"=1')
        self.assertEqual(self.db.val('SELECT "관계" FROM "관계"'), "c")

    def test_deleting_combo_removes_its_recipe_but_not_when_used_as_material(self):
        w = self.work()
        self.combo(w, 1), self.combo(w, 2), self.clue(w, 1)
        self.ins("조합재료", 작품_번호=w, 결과_조합_순서=1, 단서_순서=1)
        self.ins("조합재료", 작품_번호=w, 결과_조합_순서=2, 조합_순서=1)
        self.db.fails(f'DELETE FROM "조합" WHERE "작품_번호"={w} AND "순서"=1', "foreign key constraint")  # 재료로 사용 중
        self.db.ok(f'DELETE FROM "조합" WHERE "작품_번호"={w} AND "순서"=2')    # 결과 조합 삭제 → 레시피 삭제
        self.assertEqual(self.count("조합재료", f'"결과_조합_순서"=2'), 0)
        self.db.ok(f'DELETE FROM "조합" WHERE "작품_번호"={w} AND "순서"=1')    # 이제 삭제 가능
        self.assertEqual(self.count("조합재료"), 0)

    def test_deleting_incident_removes_its_details(self):
        w = self.work()
        self.incident(w, 1)
        self.ins("사건설명", 작품_번호=w, 사건_순서=1, 설명="x")
        self.db.ok(f'DELETE FROM "사건" WHERE "작품_번호"={w}')
        self.assertEqual(self.count("사건설명"), 0)

    def test_step_used_by_vote_media_or_gimmick_cannot_be_deleted_but_phase_mapping_goes(self):
        w = self.work()
        phase = self.phase()
        self.step(w, 1)
        self.ins("진행구성", 작품_번호=w, 진행순서_순서=1, 진행단계_번호=phase)
        self.db.ok(f'DELETE FROM "진행순서" WHERE "작품_번호"={w}')          # 진행구성만 매달린 경우는 함께 삭제
        self.assertEqual(self.count("진행구성"), 0)
        self.step(w, 1)
        self.vote(w, 1, 1)
        self.db.fails(f'DELETE FROM "진행순서" WHERE "작품_번호"={w}', "foreign key constraint")
        self.db.ok(f'DELETE FROM "투표" WHERE "작품_번호"={w}')
        self.media(w, 1, 진행순서_순서=1)
        self.db.fails(f'DELETE FROM "진행순서" WHERE "작품_번호"={w}', "foreign key constraint")

    def test_library_items_in_use_cannot_be_deleted(self):
        w = self.work()
        self.step(w, 1)
        phase, gim = self.phase(), self.gimmick()
        self.ins("진행구성", 작품_번호=w, 진행순서_순서=1, 진행단계_번호=phase)
        self.applied_gimmick(w, 1, 1, gim)
        self.db.fails(f'DELETE FROM "진행단계" WHERE "번호"={phase}', "foreign key constraint")
        self.db.fails(f'DELETE FROM "기믹" WHERE "번호"={gim}', "foreign key constraint")

    def test_deleting_game_removes_its_records_only(self):
        w = self.work()
        self.version(w)
        room1, room2 = self.room(w), self.room(w)
        g1, g2 = self.game(room1, w), self.game(room2, w)
        for g in (g1, g2):
            p = self.participant(w, g)
            self.ins("획득", 작품_번호=w, 진행_번호=g, 참여_번호=p, 단서_순서=1, 진행순서_순서=1, 획득방법="조사")
            self.ins("기믹실행", 작품_번호=w, 진행_번호=g, 기믹적용_순서=1)
            self.ins("투표결과", 작품_번호=w, 투표이름="투표1", 참여_번호=p, 선택="a")
            self.ins("엔딩", 작품_번호=w, 진행_번호=g, 순서=1, 엔딩분기_순서=1)
        self.db.ok(f'DELETE FROM "진행" WHERE "번호"={g1}')
        for t in ("참여", "획득", "기믹실행", "투표결과", "엔딩"):
            self.assertEqual(self.count(t), 1, t)
        self.db.fails(f'DELETE FROM "방" WHERE "번호"={room2}', "foreign key constraint")   # 진행이 남아 있으면 방 삭제 불가
        self.db.ok(f'DELETE FROM "방" WHERE "번호"={room1}')                                  # 판이 지워진 방은 삭제 가능

    def test_account_with_play_history_cannot_be_deleted(self):
        w, g = self.playable_game()
        a = self.account()
        self.participant(w, g, a)
        self.db.fails(f'DELETE FROM "계정" WHERE "번호"={a}', "foreign key constraint")


class TestTriggers(Builders):
    def test_version_snapshot_is_immutable(self):
        w = self.work()
        v = self.version(w, "1.0", scenario={"a": 1}, 변경사항="최초")
        err = self.db.fails(f'UPDATE "버전" SET "시나리오"=\'{{"a": 2}}\' WHERE "번호"={v}')
        self.assertIn("변경할 수 없습니다", err)
        self.db.fails(f'UPDATE "버전" SET "버전"=\'9.9\' WHERE "번호"={v}', "변경할 수 없습니다")
        w2 = self.work()
        self.db.fails(f'UPDATE "버전" SET "작품_번호"={w2} WHERE "번호"={v}', "변경할 수 없습니다")
        # 같은 값으로의 UPDATE 와 변경사항 수정은 허용
        self.db.ok(f'UPDATE "버전" SET "시나리오"="시나리오", "변경사항"=\'정정\' WHERE "번호"={v}')
        self.assertEqual(self.db.val(f'SELECT "시나리오"->>\'a\' FROM "버전" WHERE "번호"={v}'), "1")

    def test_version_with_games_cannot_be_deleted_but_unused_can(self):
        w = self.work()
        used, unused = self.version(w, "1.0"), self.version(w, "1.1")
        self.game(self.room(w, "1.0"), w, "1.0")
        self.db.fails(f'DELETE FROM "버전" WHERE "번호"={used}', "foreign key constraint")
        self.db.ok(f'DELETE FROM "버전" WHERE "번호"={unused}')

    def test_room_timestamps_follow_status(self):
        r = self.room()
        t0 = self.db.rows(f'SELECT "상태변경일시" = "생성일시", "종료일시" IS NULL FROM "방" WHERE "번호"={r}')[0]
        self.assertEqual(t0, ["t", "t"])
        # 별도 트랜잭션으로 시간이 흐른 뒤 상태를 바꾼다
        self.db.ok("SELECT pg_sleep(0.05)")
        self.db.ok(f'UPDATE "방" SET "상태"=\'진행\' WHERE "번호"={r}')
        row = self.db.rows(f'SELECT "상태변경일시" > "생성일시", "종료일시" IS NULL FROM "방" WHERE "번호"={r}')[0]
        self.assertEqual(row, ["t", "t"])
        self.db.ok(f'UPDATE "방" SET "상태"=\'종료\' WHERE "번호"={r}')
        row = self.db.rows(f'SELECT "종료일시" IS NOT NULL, "종료일시" = "상태변경일시" FROM "방" WHERE "번호"={r}')[0]
        self.assertEqual(row, ["t", "t"])

    def test_room_status_change_time_unchanged_when_status_same(self):
        r = self.room()
        before = self.db.val(f'SELECT "상태변경일시" FROM "방" WHERE "번호"={r}')
        self.db.ok("SELECT pg_sleep(0.05)")
        self.db.ok(f'UPDATE "방" SET "입장코드"=\'NEWCODE\' WHERE "번호"={r}')
        self.assertEqual(self.db.val(f'SELECT "상태변경일시" FROM "방" WHERE "번호"={r}'), before)

    def test_room_created_as_ended_gets_end_time(self):
        r = self.room(상태="종료")
        self.assertEqual(self.db.val(f'SELECT "종료일시" IS NOT NULL FROM "방" WHERE "번호"={r}'), "t")

    def test_game_end_time_recorded_when_ended(self):
        w, g = self.playable_game()
        self.assertEqual(self.db.val(f'SELECT "종료일시" IS NULL FROM "진행" WHERE "번호"={g}'), "t")
        self.db.ok(f'UPDATE "진행" SET "상태"=\'종료\' WHERE "번호"={g}')
        self.assertEqual(self.db.val(f'SELECT "종료일시" IS NOT NULL FROM "진행" WHERE "번호"={g}'), "t")
        # 이미 값이 있으면 덮어쓰지 않는다
        self.db.ok(f'UPDATE "진행" SET "종료일시"=\'2030-01-01 00:00:00+00\' WHERE "번호"={g}')
        self.db.ok(f'UPDATE "진행" SET "상태"=\'종료\' WHERE "번호"={g}')
        self.assertEqual(self.db.val(f'SELECT "종료일시" = \'2030-01-01 00:00:00+00\' FROM "진행" WHERE "번호"={g}'), "t")


class TestJsonbColumnsAreFreeForm(Scenario):
    """JSONB 내부 구조는 확정되지 않았으므로 어떤 JSON 값이든 저장되고, SQL NULL 만 NOT NULL 컬럼에서 거부된다."""

    EXPECTED = {
        ("버전", "시나리오"): False,       # NULL 허용 여부
        ("미디어", "조건"): True,
        ("엔딩분기", "조건"): False,
        ("후일담", "조건"): True,
        ("진행단계", "규칙"): False,
        ("기믹", "조건"): False,
        ("기믹", "결과"): False,
        ("기믹실행", "결과"): True,
        ("투표", "규칙"): False,
        ("진행구성", "설정"): True,
        ("기믹적용", "설정"): True,
    }

    def test_jsonb_column_inventory_matches_spec(self):
        rows = {(t, c): n for t, c, n in self.db.rows(
            """SELECT table_name, column_name, is_nullable='YES' FROM information_schema.columns
               WHERE table_schema='public' AND data_type='jsonb'""")}
        self.assertEqual({k: v == "t" for k, v in rows.items()}, self.EXPECTED)

    def row_with(self, table, col, value_sql):
        """value_sql 은 이미 SQL 식 (예: '{"a":1}'::jsonb 또는 NULL)."""
        w = self.work()
        self.step(w, 1)
        if table == "버전":
            return f'INSERT INTO "버전"("작품_번호","버전","시나리오") VALUES ({w},\'{self.db.n()}\',{value_sql})'
        if table == "미디어":
            return f'INSERT INTO "미디어"("작품_번호","순서","유형","경로","조건") VALUES ({w},1,\'이미지\',\'p\',{value_sql})'
        if table == "엔딩분기":
            return f'INSERT INTO "엔딩분기"("작품_번호","순서","이름","조건","내용") VALUES ({w},1,\'n\',{value_sql},\'x\')'
        if table == "후일담":
            return f'INSERT INTO "후일담"("작품_번호","순서","내용","조건") VALUES ({w},1,\'x\',{value_sql})'
        if table == "진행단계":
            return f'INSERT INTO "진행단계"("이름","규칙","설명") VALUES (\'x\',{value_sql},\'d\')'
        if table == "기믹" and col == "조건":
            return f'INSERT INTO "기믹"("이름","조건","결과") VALUES (\'x\',{value_sql},\'{{}}\')'
        if table == "기믹" and col == "결과":
            return f'INSERT INTO "기믹"("이름","조건","결과") VALUES (\'x\',\'{{}}\',{value_sql})'
        if table == "투표":
            return f'INSERT INTO "투표"("작품_번호","순서","진행순서_순서","이름","내용","규칙") VALUES ({w},1,1,\'x\',\'y\',{value_sql})'
        if table == "진행구성":
            p = self.phase()
            return f'INSERT INTO "진행구성"("작품_번호","진행순서_순서","진행단계_번호","설정") VALUES ({w},1,{p},{value_sql})'
        if table == "기믹적용":
            g = self.gimmick()
            return f'INSERT INTO "기믹적용"("작품_번호","순서","기믹_번호","진행순서_순서","설정") VALUES ({w},1,{g},1,{value_sql})'
        if table == "기믹실행":
            self.version(w)
            g = self.game(self.room(w), w)
            return f'INSERT INTO "기믹실행"("작품_번호","진행_번호","기믹적용_순서","결과") VALUES ({w},{g},1,{value_sql})'
        raise KeyError(table)

    def test_any_json_value_is_accepted_and_sql_null_follows_nullability(self):
        json_values = ["'{}'::jsonb", "'[]'::jsonb", "'[1,\"a\",null]'::jsonb",
                       "'{\"nested\":{\"deep\":[1,2,{\"x\":null}]}}'::jsonb", "'\"문자열\"'::jsonb",
                       "'123'::jsonb", "'true'::jsonb", "'null'::jsonb"]    # 마지막은 JSON null (SQL NULL 아님)
        for (table, col), nullable in self.EXPECTED.items():
            for v in json_values:
                with self.subTest(table=table, col=col, value=v):
                    self.db.ok(self._truncate_sql)
                    self.db.ok(self.row_with(table, col, v))
            with self.subTest(table=table, col=col, value="SQL NULL"):
                self.db.ok(self._truncate_sql)
                sql = self.row_with(table, col, "NULL")
                if nullable:
                    self.db.ok(sql)
                else:
                    self.db.fails(sql, "null value")

    def test_no_check_constraint_mentions_jsonb_columns(self):
        """JSONB 내부 형식 검증용 CHECK 가 어디에도 없어야 한다 (내부 구조 임의 확정 금지)."""
        rows = self.db.rows(
            """SELECT cl.relname, c.conname, pg_get_constraintdef(c.oid)
               FROM pg_constraint c JOIN pg_class cl ON cl.oid=c.conrelid
               JOIN pg_namespace n ON n.oid=cl.relnamespace
               WHERE n.nspname='public' AND c.contype='c'""")
        jsonb_cols = {c for (_, c) in self.EXPECTED}
        offenders = [r for r in rows if any(f'"{c}"' in r[2] and r[0] in {t for (t, cc) in self.EXPECTED if cc == c}
                                            for c in jsonb_cols)]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
