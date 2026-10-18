"""제약조건 동작 테스트: 잘못된 데이터는 거부되고 올바른 데이터는 들어가는지 확인한다."""
from __future__ import annotations

import unittest

from builders import Builders, Raw


class TestAccountsAndSessions(Builders):
    def test_account_defaults_and_status_check(self):
        a = self.account()
        self.assertEqual(self.db.val(f'SELECT "상태" FROM "계정" WHERE "번호"={a}'), "정상")
        for ok in ("정지", "탈퇴"):
            self.ins("계정", 아이디=f"u_{ok}", 패스워드="h", 닉네임="n", 상태=ok)
        self.ins_fails("계정", "ck_계정_상태", 아이디="bad", 패스워드="h", 닉네임="n", 상태="휴면")

    def test_account_login_id_unique(self):
        self.ins("계정", 아이디="same", 패스워드="h", 닉네임="a")
        self.ins_fails("계정", "uq_계정_아이디", 아이디="same", 패스워드="h2", 닉네임="b")

    def test_account_required_columns(self):
        for missing in ("아이디", "패스워드", "닉네임"):
            cols = dict(아이디="x", 패스워드="h", 닉네임="n")
            cols[missing] = None
            self.ins_fails("계정", "null value", **cols)

    def test_session_checks(self):
        a = self.account()
        base = dict(계정_번호=a, 접속환경="PC")
        self.ins("로그인세션", 토큰="t1", 만료일시=Raw("CURRENT_TIMESTAMP + interval '6 hours'"), **base)
        self.ins("로그인세션", 토큰="t2", 만료일시=Raw("CURRENT_TIMESTAMP + interval '30 days'"),
                 **{**base, "접속환경": "모바일"})
        self.ins_fails("로그인세션", "uq_로그인세션_토큰", 토큰="t1",
                       만료일시=Raw("CURRENT_TIMESTAMP + interval '1 hour'"), **base)
        self.ins_fails("로그인세션", "ck_로그인세션_환경", 토큰="t3",
                       만료일시=Raw("CURRENT_TIMESTAMP + interval '1 hour'"), 계정_번호=a, 접속환경="태블릿")
        # 만료일시 <= 생성일시 는 거부 (같은 값도 거부)
        self.ins_fails("로그인세션", "ck_로그인세션_만료", 토큰="t4",
                       만료일시=Raw("CURRENT_TIMESTAMP - interval '1 hour'"), **base)
        self.ins_fails("로그인세션", "ck_로그인세션_만료", 토큰="t5", 생성일시=Raw("'2030-01-01 00:00:00+00'"),
                       만료일시=Raw("'2030-01-01 00:00:00+00'"), **base)

    def test_session_revocation_is_nullable_and_account_fk(self):
        a = self.account()
        s = self.ins("로그인세션", 계정_번호=a, 토큰="tk", 접속환경="PC",
                     만료일시=Raw("CURRENT_TIMESTAMP + interval '1 day'"))
        self.assertEqual(self.db.val(f'SELECT "폐기일시" IS NULL FROM "로그인세션" WHERE "번호"={s}'), "t")
        self.db.ok(f'UPDATE "로그인세션" SET "폐기일시"=CURRENT_TIMESTAMP WHERE "번호"={s}')
        self.ins_fails("로그인세션", "fk_로그인세션_계정", 계정_번호=99999, 토큰="zz", 접속환경="PC",
                       만료일시=Raw("CURRENT_TIMESTAMP + interval '1 day'"))

    def test_deleting_account_removes_its_sessions(self):
        a = self.account()
        self.ins("로그인세션", 계정_번호=a, 토큰="tk", 접속환경="PC",
                 만료일시=Raw("CURRENT_TIMESTAMP + interval '1 day'"))
        self.db.ok(f'DELETE FROM "계정" WHERE "번호"={a}')
        self.assertEqual(self.count("로그인세션"), 0)


class TestWorksAndVersions(Builders):
    def test_work_defaults(self):
        w = self.work()
        row = self.db.rows(
            f'''SELECT "최소인원","최대인원","예상시간","상태","최신버전","공개여부","수정일시" IS NULL
                FROM "작품" WHERE "번호"={w}''')[0]
        self.assertEqual(row, ["4", "4", "3시간", "개발", "1.0", "f", "t"])

    def test_work_checks(self):
        a = self.account()
        base = dict(제목="t", 시놉시스="s", 장르="g", 계정_번호=a)
        self.ins_fails("작품", "ck_작품_최소인원", **{**base, "최소인원": 0})
        self.ins_fails("작품", "ck_작품_최대인원", **{**base, "최소인원": 5, "최대인원": 4})
        self.ins_fails("작품", "ck_작품_상태", **{**base, "상태": "삭제"})
        self.ins("작품", **{**base, "최소인원": 1, "최대인원": 1})        # 경계값 허용
        self.ins("작품", **{**base, "최소인원": 4, "최대인원": 4})        # 최대 == 최소 허용
        for st in ("수정", "개발", "완료"):
            self.ins("작품", **{**base, "상태": st})

    def test_work_owner_must_exist_and_blocks_account_delete(self):
        self.ins_fails("작품", "fk_작품_계정", 제목="t", 시놉시스="s", 장르="g", 계정_번호=99999)
        a = self.account()
        self.work(a)
        self.db.fails(f'DELETE FROM "계정" WHERE "번호"={a}', "fk_작품_계정")

    def test_version_unique_per_work_and_default(self):
        w1, w2 = self.work(), self.work()
        v = self.version(w1)
        self.assertEqual(self.db.val(f'SELECT "버전" FROM "버전" WHERE "번호"={v}'), "1.0")
        self.ins_fails("버전", "uq_버전_작품_버전", 작품_번호=w1, 버전="1.0", 시나리오={})
        self.version(w1, "1.1")
        self.version(w2, "1.0")                                           # 다른 작품은 같은 버전 문자열 가능

    def test_version_requires_snapshot_and_existing_work(self):
        w = self.work()
        self.ins_fails("버전", "null value", 작품_번호=w, 버전="2.0", 시나리오=None)
        self.ins_fails("버전", "fk_버전_작품", 작품_번호=99999, 버전="1.0", 시나리오={})


class TestOrderChecksAndUniqueness(Builders):
    """'순서 >= 1' CHECK 와 (작품_번호, 순서) 복합 UNIQUE 를 작품 내부 번호 테이블 전부에 적용해 본다."""

    def maker(self, table):
        w = self.w

        def mk(n):
            if table == "진행순서":
                return dict(작품_번호=w, 순서=n)
            if table == "기믹적용":
                return dict(작품_번호=w, 순서=n, 기믹_번호=self.gid, 진행순서_순서=1)
            if table == "인물":
                return dict(작품_번호=w, 순서=n, 이름="a", 서사="b")
            if table == "장소":
                return dict(작품_번호=w, 순서=n, 이름="a")
            if table == "단서":
                return dict(작품_번호=w, 순서=n, 이름="a")
            if table == "증언":
                return dict(작품_번호=w, 순서=n, 화자="a", 내용="b")
            if table == "조합":
                return dict(작품_번호=w, 순서=n, 이름="a")
            if table == "사건":
                return dict(작품_번호=w, 순서=n)
            if table == "엔딩분기":
                return dict(작품_번호=w, 순서=n, 이름="a", 조건={}, 내용="a")
            if table == "후일담":
                return dict(작품_번호=w, 순서=n, 내용="a")
            if table == "타임라인":
                return dict(작품_번호=w, 순서=n, 설명="a")
            if table == "투표":
                return dict(작품_번호=w, 순서=n, 진행순서_순서=1, 이름="a", 내용="b", 규칙={})
            if table == "미디어":
                return dict(작품_번호=w, 순서=n, 유형="이미지", 경로="p")
            if table == "자료":
                return dict(작품_번호=w, 순서=n, 제목="a", 내용="b")
            raise KeyError(table)
        return mk

    TABLES = ["진행순서", "기믹적용", "인물", "장소", "단서", "증언", "조합", "사건",
              "엔딩분기", "후일담", "타임라인", "투표", "미디어", "자료"]

    def test_order_must_be_positive_and_unique_per_work(self):
        for table in self.TABLES:
            with self.subTest(table=table):
                self.db.ok(self._truncate_sql)
                self.w = self.work()
                self.step(self.w, 1)
                self.gid = self.gimmick()
                mk = self.maker(table)
                if table == "진행순서":
                    self.db.ok(self._truncate_sql)
                    self.w = self.work()
                self.ins_fails(table, f"ck_{table}_순서", **mk(0))
                self.ins_fails(table, f"ck_{table}_순서", **mk(-3))
                n = 2 if table == "진행순서" else 1
                self.ins(table, **mk(n))
                self.ins_fails(table, f"uq_{table}_작품_순서", **mk(n))   # 같은 작품 같은 순서 중복
                other = self.work()                                      # 다른 작품은 같은 순서 허용
                self.step(other, 1)
                cols = mk(n)
                cols["작품_번호"] = other
                self.ins(table, **cols)

    def test_step_duration_check(self):
        w = self.work()
        self.ins_fails("진행순서", "ck_진행순서_진행시간", 작품_번호=w, 순서=1, 진행시간=-1)
        self.ins("진행순서", 작품_번호=w, 순서=1, 진행시간=0)
        s = self.step(w, 2)
        self.assertEqual(self.db.val(f'SELECT "진행시간" FROM "진행순서" WHERE "번호"={s}'), "30")


class TestCompositeForeignKeys(Builders):
    """복합 FK 는 같은 작품의 순서만 참조할 수 있어야 한다. 순서가 NULL 이면 검사하지 않는다."""

    def setUp(self):
        super().setUp()
        self.a, self.b = self.work(), self.work()      # 작품 A: 모든 부모가 있음 / 작품 B: 아무것도 없음
        self.step(self.a, 1)
        self.character(self.a, 1)
        self.place(self.a, 1)
        self.clue(self.a, 1)
        self.witness(self.a, 1)
        self.combo(self.a, 1)
        self.incident(self.a, 1)

    # (자식 테이블, FK 컬럼, 기본 컬럼 생성기)
    def cases(self, w):
        return [
            ("단서", "인물_순서", dict(작품_번호=w, 순서=50, 이름="x")),
            ("단서", "장소_순서", dict(작품_번호=w, 순서=51, 이름="x")),
            ("증언", "인물_순서", dict(작품_번호=w, 순서=50, 화자="x", 내용="y")),
            ("증언", "장소_순서", dict(작품_번호=w, 순서=51, 화자="x", 내용="y")),
            ("장소", "상위_장소_순서", dict(작품_번호=w, 순서=50, 이름="x")),
            ("사건설명", "인물_순서", dict(작품_번호=w, 사건_순서=1)),
            ("후일담", "인물_순서", dict(작품_번호=w, 순서=50, 내용="x")),
            ("미디어", "단서_순서", dict(작품_번호=w, 순서=50, 유형="영상", 경로="p")),
            ("미디어", "증언_순서", dict(작품_번호=w, 순서=51, 유형="영상", 경로="p")),
            ("미디어", "조합_순서", dict(작품_번호=w, 순서=52, 유형="영상", 경로="p")),
            ("미디어", "진행순서_순서", dict(작품_번호=w, 순서=53, 유형="영상", 경로="p")),
            ("관계", "인물_순서", dict(작품_번호=w, 대상_인물_순서=1, 관계="r")),
            ("관계", "대상_인물_순서", dict(작품_번호=w, 인물_순서=1, 관계="r")),
            ("조합재료", "단서_순서", dict(작품_번호=w, 결과_조합_순서=1)),
            ("조합재료", "증언_순서", dict(작품_번호=w, 결과_조합_순서=1)),
            ("조합재료", "조합_순서", dict(작품_번호=w, 결과_조합_순서=1)),
            ("진행구성", "진행순서_순서", dict(작품_번호=w, 진행단계_번호=None)),
            ("기믹적용", "진행순서_순서", dict(작품_번호=w, 순서=50, 기믹_번호=None)),
            ("투표", "진행순서_순서", dict(작품_번호=w, 순서=50, 이름="x", 내용="y", 규칙={})),
        ]

    def test_same_work_reference_ok_other_work_rejected(self):
        phase, gimmick = self.phase(), self.gimmick()
        for table, col, base in self.cases(self.a):
            with self.subTest(table=table, col=col):
                base = dict(base)
                if base.get("진행단계_번호", 0) is None:
                    base["진행단계_번호"] = phase
                if base.get("기믹_번호", 0) is None:
                    base["기믹_번호"] = gimmick
                # 같은 작품(A)의 순서 1 참조 → 성공 (바로 지워서 이후 실패 케이스가 UNIQUE 에 먼저 걸리지 않게 한다)
                rid = self.ins(table, **{**base, col: 1})
                self.db.ok(f'DELETE FROM "{table}" WHERE "번호"={rid}')
                # 존재하지 않는 순서 → 거부
                self.ins_fails(table, "foreign key constraint", **{**base, col: 999})
                # 다른 작품(B)이 A 의 순서 1 을 참조 → 거부 (작품 간 교차 참조 금지)
                crossed = dict(base)
                crossed["작품_번호"] = self.b
                crossed[col] = 1
                self.ins_fails(table, "foreign key constraint", **crossed)

    def test_null_reference_is_not_checked(self):
        self.ins("단서", 작품_번호=self.b, 순서=1, 이름="x", 인물_순서=None, 장소_순서=None)
        self.ins("후일담", 작품_번호=self.b, 순서=1, 내용="전체 후일담", 인물_순서=None)
        self.ins("장소", 작품_번호=self.b, 순서=1, 이름="최상위", 상위_장소_순서=None)


class TestExactlyOneReference(Builders):
    """조합재료 / 엔딩 / 획득: 지정한 컬럼 중 정확히 하나만 값이 있어야 한다."""

    def test_combo_material_exactly_one(self):
        w = self.work()
        self.combo(w, 1), self.combo(w, 2), self.clue(w, 1), self.witness(w, 1)
        base = dict(작품_번호=w, 결과_조합_순서=1)
        self.ins_fails("조합재료", "ck_조합재료_재료하나", **base)                               # 0개
        self.ins_fails("조합재료", "ck_조합재료_재료하나", **base, 단서_순서=1, 증언_순서=1)   # 2개
        self.ins_fails("조합재료", "ck_조합재료_재료하나", **base, 단서_순서=1, 증언_순서=1, 조합_순서=2)  # 3개
        self.ins("조합재료", **base, 단서_순서=1)
        self.ins("조합재료", **base, 증언_순서=1)
        self.ins("조합재료", **base, 조합_순서=2)

    def test_ending_exactly_one(self):
        w, g = self.playable_game()
        base = dict(작품_번호=w, 진행_번호=g)
        self.ins_fails("엔딩", "ck_엔딩_하나", 순서=1, **base)
        self.ins_fails("엔딩", "ck_엔딩_하나", 순서=1, 엔딩분기_순서=1, 후일담_순서=1, **base)
        self.ins_fails("엔딩", "ck_엔딩_순서", 순서=0, 엔딩분기_순서=1, **base)
        self.ins("엔딩", 순서=1, 엔딩분기_순서=1, **base)
        self.ins("엔딩", 순서=2, 후일담_순서=3, **base)
        self.ins_fails("엔딩", "uq_엔딩_진행_순서", 순서=1, 엔딩분기_순서=2, **base)

    def test_acquisition_exactly_one(self):
        w, g = self.playable_game()
        p = self.participant(w, g)
        base = dict(작품_번호=w, 진행_번호=g, 참여_번호=p, 진행순서_순서=1, 획득방법="조사")
        self.ins_fails("획득", "ck_획득_하나", **base)
        self.ins_fails("획득", "ck_획득_하나", 단서_순서=1, 증언_순서=2, **base)
        self.ins_fails("획득", "ck_획득_하나", 단서_순서=1, 증언_순서=2, 조합_순서=3, **base)
        for col in ("단서_순서", "증언_순서", "조합_순서"):
            self.ins("획득", **base, **{col: 1})
        self.assertEqual(self.db.val('SELECT DISTINCT "보유여부" FROM "획득"'), "t")   # 기본값 TRUE


class TestMediaVoteGimmick(Builders):
    def test_media_type_and_required_path(self):
        w = self.work()
        self.media(w, 1, 유형="이미지")
        self.media(w, 2, 유형="영상")
        self.ins_fails("미디어", "ck_미디어_유형", 작품_번호=w, 순서=3, 유형="음성", 경로="p")
        self.ins_fails("미디어", "null value", 작품_번호=w, 순서=3, 유형="이미지", 경로=None)
        # 조건은 NULL 허용
        self.assertEqual(self.db.val('SELECT count(*) FROM "미디어" WHERE "조건" IS NULL'), "2")

    def test_phase_composition_unique(self):
        w = self.work()
        self.step(w, 1)
        p1, p2 = self.phase(), self.phase(이름="수색")
        self.ins("진행구성", 작품_번호=w, 진행순서_순서=1, 진행단계_번호=p1)
        self.ins("진행구성", 작품_번호=w, 진행순서_순서=1, 진행단계_번호=p2)
        self.ins_fails("진행구성", "uq_진행구성_작품_순서_단계", 작품_번호=w, 진행순서_순서=1, 진행단계_번호=p1)

    def test_library_items_have_optional_owner(self):
        a = self.account()
        self.phase()                  # 공통(소유자 없음)
        self.phase(계정_번호=a)
        self.gimmick()
        self.gimmick(계정_번호=a)
        self.ins_fails("기믹", "fk_기믹_계정", 이름="x", 조건={}, 결과={}, 계정_번호=99999)
        self.ins_fails("진행단계", "fk_진행단계_계정", 이름="x", 규칙={}, 설명="d", 계정_번호=99999)


class TestRuntimeConstraints(Builders):
    def test_room_checks_and_unique_code_among_open_rooms(self):
        r = self.room(code="ABC123")
        self.assertEqual(self.db.val(f'SELECT "상태" FROM "방" WHERE "번호"={r}'), "대기")
        w = self.db.val(f'SELECT "작품_번호" FROM "방" WHERE "번호"={r}')
        # 종료되지 않은 방끼리는 같은 코드를 쓸 수 없다. 종료된 방의 코드는 다시 쓸 수 있다(0022).
        self.ins_fails("방", "uq_방_입장코드_사용중", 계정_번호=self.account(), 입장코드="ABC123", 작품_번호=w, 버전_버전="1.0")
        self.db.ok(f'UPDATE "방" SET "상태"=\'종료\' WHERE "번호"={r}')
        again = self.ins("방", 계정_번호=self.account(), 입장코드="ABC123", 작품_번호=w, 버전_버전="1.0")
        self.assertEqual(self.db.val(f'SELECT "상태" FROM "방" WHERE "번호"={again}'), "대기")
        self.ins_fails("방", "uq_방_입장코드_사용중", 계정_번호=self.account(), 입장코드="ABC123", 작품_번호=w, 버전_버전="1.0")
        self.ins_fails("방", "ck_방_상태", 계정_번호=self.account(), 입장코드="X1", 작품_번호=w, 버전_버전="1.0", 상태="폐쇄")
        for st in ("대기", "진행", "종료"):
            self.room(code=f"S_{st}", 상태=st)

    def test_room_must_reference_existing_confirmed_version(self):
        w = self.work()
        acc = self.account()
        # 확정 버전이 없으면 방을 만들 수 없다 (개발 중인 작품으로는 진행 불가)
        self.ins_fails("방", "fk_방_버전", 계정_번호=acc, 입장코드="NOVER", 작품_번호=w, 버전_버전="1.0")
        self.version(w, "1.0")
        self.ins_fails("방", "fk_방_버전", 계정_번호=acc, 입장코드="BADVER", 작품_번호=w, 버전_버전="9.9")
        self.ins_fails("방", "fk_방_작품", 계정_번호=acc, 입장코드="NOWORK", 작품_번호=99999, 버전_버전="1.0")
        self.room(w, "1.0")

    def test_game_must_match_the_room_work_and_version(self):
        w1, w2 = self.work(), self.work()
        self.version(w1, "1.0")
        self.version(w1, "1.1")
        self.version(w2, "2.0")
        room = self.room(w1, "1.0")
        # 방과 다른 작품·버전으로는 게임을 만들 수 없다
        self.ins_fails("진행", "fk_진행_방_작품_버전", 방_번호=room, 작품_번호=w1, 버전_버전="1.1")   # 같은 작품의 다른 버전
        self.ins_fails("진행", "fk_진행_방_작품_버전", 방_번호=room, 작품_번호=w2, 버전_버전="2.0")   # 다른 작품
        g = self.game(room, w1, "1.0")
        self.assertEqual(self.db.val(f'SELECT "상태" FROM "진행" WHERE "번호"={g}'), "진행")

    def test_game_state_check(self):
        w = self.work()
        self.version(w)
        self.ins_fails("진행", "ck_진행_상태", 방_번호=self.room(w), 작품_번호=w, 버전_버전="1.0", 상태="일시정지")

    def test_one_room_hosts_only_one_game(self):
        w = self.work()
        self.version(w)
        room = self.room(w)
        g1 = self.game(room, w)
        self.db.ok(f'UPDATE "진행" SET "상태"=\'종료\' WHERE "번호"={g1}')
        # 게임이 끝난 방에서도 새 게임은 만들 수 없다 (한 번 더 하려면 새 방)
        self.ins_fails("진행", "uq_진행_방", 방_번호=room, 작품_번호=w, 버전_버전="1.0")
        self.assertEqual(self.count("진행", f'"방_번호"={room}'), 1)

    def test_rooms_of_the_same_work_each_get_their_own_game(self):
        w = self.work()
        self.version(w)
        self.game(self.room(w), w)
        self.game(self.room(w), w)
        self.assertEqual(self.count("진행", f'"작품_번호"={w}'), 2)

    def test_participation_uniqueness(self):
        w, g = self.playable_game()
        a1, a2 = self.account(), self.account()
        self.participant(w, g, a1, 인물_순서=1)
        self.ins_fails("참여", "uq_참여_진행_계정", 작품_번호=w, 진행_번호=g, 계정_번호=a1)         # 한 계정 한 배역
        self.ins_fails("참여", "uq_참여_진행_인물", 작품_번호=w, 진행_번호=g, 계정_번호=a2, 인물_순서=1)  # 한 배역 한 계정
        self.participant(w, g, a2, 인물_순서=None)                                                   # 배역 선택 전 NULL
        self.participant(w, g, self.account(), 인물_순서=None)                                        # NULL 은 여러 명 가능
        # 다른 판에서는 같은 계정·같은 배역이 가능
        g2 = self.game(self.room(w), w)
        self.participant(w, g2, a1, 인물_순서=1)
        self.assertEqual(self.db.val('SELECT "후기공개" FROM "참여" LIMIT 1'), "t")  # 후기는 기본적으로 공개

    def test_participation_record_columns(self):
        """평점·난이도: 0~5, 0.5 단위, 비워 둘 수 있다(비어 있음 = 기록 안 함, 0 과 다르다). 메모·후기는 자유 글."""
        w, g = self.playable_game()
        for v in ("0", "0.5", "2.5", "5"):
            p = self.participant(w, g, self.account(), 평점=v, 난이도=v)
            self.assertEqual(self.db.val(f'SELECT "평점"::text FROM "참여" WHERE "번호"={p}'), f"{float(v):.1f}")
        # 후기만 쓰고 평점·난이도를 비워도, 반대로 평점만 남겨도 된다 (서로 묶지 않는다)
        a = self.participant(w, g, self.account(), 후기="오류가 있어요", 후기공개=False, 메모="내 메모")
        self.assertEqual(self.db.val(f'SELECT "평점" IS NULL, "난이도" IS NULL, "후기공개", "메모" FROM "참여" WHERE "번호"={a}'), "t|t|f|내 메모")
        self.participant(w, g, self.account(), 평점="4.5")
        # 0 과 비어 있음은 다르다: 평균은 비어 있는 값을 건너뛴다
        avg = self.db.val(f'SELECT round(avg("난이도"), 2) FROM "참여" WHERE "작품_번호"={w}')
        self.assertEqual(avg, "2.00")  # (0 + 0.5 + 2.5 + 5) / 4, 비어 있는 2개는 제외
        for col in ("평점", "난이도"):
            for bad in ("5.5", "-0.5", "2.3", "0.25"):
                self.ins_fails("참여", f"ck_참여_{col}", 작품_번호=w, 진행_번호=g, 계정_번호=self.account(), **{col: bad})

    def test_gimmick_execution_unique_per_game(self):
        w, g = self.playable_game()
        e = self.ins("기믹실행", 작품_번호=w, 진행_번호=g, 기믹적용_순서=1)
        self.assertEqual(self.db.val(f'SELECT "실행여부", "결과" IS NULL FROM "기믹실행" WHERE "번호"={e}'), "f|t")
        self.ins_fails("기믹실행", "uq_기믹실행_진행_적용", 작품_번호=w, 진행_번호=g, 기믹적용_순서=1)
        self.ins("기믹실행", 작품_번호=w, 진행_번호=g, 기믹적용_순서=2)

    def test_vote_result_unique_per_voter(self):
        w, g = self.playable_game()
        p1, p2 = self.participant(w, g), self.participant(w, g)
        self.ins("투표결과", 작품_번호=w, 투표_순서=1, 참여_번호=p1, 선택="A")
        self.ins("투표결과", 작품_번호=w, 투표_순서=1, 참여_번호=p2, 선택="B")
        self.ins("투표결과", 작품_번호=w, 투표_순서=2, 참여_번호=p1, 선택="A")
        self.ins_fails("투표결과", "uq_투표결과_투표_참여", 작품_번호=w, 투표_순서=1, 참여_번호=p1, 선택="C")
        self.ins_fails("투표결과", "null value", 작품_번호=w, 투표_순서=3, 참여_번호=p1, 선택=None)

    def test_acquisition_default_holding_and_history_rows(self):
        """A→B 양도 후 B→A 반환 같은 이력을 행으로 쌓을 수 있다. (보유 중복 방지는 백엔드 규칙)"""
        w, g = self.playable_game()
        pa, pb = self.participant(w, g), self.participant(w, g)
        base = dict(작품_번호=w, 진행_번호=g, 단서_순서=1, 진행순서_순서=1)
        self.ins("획득", 참여_번호=pa, 획득방법="조사", 보유여부=False, **base)
        self.ins("획득", 참여_번호=pb, 획득방법="양도", 보유여부=False, **base)
        self.ins("획득", 참여_번호=pa, 획득방법="양도", **base)
        self.assertEqual(self.count("획득", f'"참여_번호"={pa}'), 2)


if __name__ == "__main__":
    unittest.main()


class TestMaterials(Builders):
    """자료: 기믹이 불러 쓰는 글. 제목과 내용은 필수이고 작품과 함께 삭제된다."""

    def test_title_and_body_are_required(self):
        w = self.work()
        self.ins("자료", 작품_번호=w, 순서=1, 제목="프롤로그 이후", 내용="글")
        self.ins_fails("자료", "null value", 작품_번호=w, 순서=2, 제목=None, 내용="글")
        self.ins_fails("자료", "null value", 작품_번호=w, 순서=2, 제목="제목", 내용=None)

    def test_materials_are_removed_with_their_work_only(self):
        w, other = self.work(), self.work()
        self.ins("자료", 작품_번호=w, 순서=1, 제목="a", 내용="b")
        self.ins("자료", 작품_번호=other, 순서=1, 제목="c", 내용="d")
        self.db.ok(f'DELETE FROM "작품" WHERE "번호"={w}')
        self.assertEqual(self.count("자료", f'"작품_번호"={w}'), 0)
        self.assertEqual(self.count("자료", f'"작품_번호"={other}'), 1)
