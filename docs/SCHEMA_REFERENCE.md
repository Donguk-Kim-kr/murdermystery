# 스키마 참조 (자동 생성)

> `db/scripts/dump_schema_md.py` 가 마이그레이션이 적용된 실제 DB 에서 추출한 문서입니다. 직접 수정하지 마세요.

테이블 35개 (생성 순서)

| 번호 | 테이블 |
|---|---|
| 1 | 계정 |
| 2 | 로그인세션 |
| 3 | 작품 |
| 4 | 버전 |
| 5 | 진행단계 |
| 6 | 기믹 |
| 7 | 진행구성 |
| 8 | 기믹적용 |
| 9 | 인물 |
| 10 | 관계 |
| 11 | 장소 |
| 12 | 단서 |
| 13 | 증언 |
| 14 | 조합 |
| 15 | 조합재료 |
| 16 | 사건 |
| 17 | 사건설명 |
| 18 | 타임라인 |
| 19 | 후일담 |
| 20 | 투표 |
| 21 | 미디어 |
| 22 | 방 |
| 23 | 진행 |
| 24 | 기믹실행 |
| 25 | 엔딩 |
| 26 | 획득 |
| 27 | 테스터 |
| 28 | 자료 |
| 29 | 참여 |
| 30 | 엔딩분기 |
| 31 | 진행순서 |
| 32 | 공개 |
| 33 | 투표결과 |
| 34 | 대화 |
| 35 | 대화수신 |

## 계정

| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |
|---|---|---|---|---|
| 1 | 번호 | integer | 불가 | IDENTITY (GENERATED ALWAYS) |
| 2 | 아이디 | text | 불가 |  |
| 3 | 패스워드 | text | 불가 |  |
| 4 | 닉네임 | text | 불가 |  |
| 5 | 가입일시 | timestamp with time zone | 불가 | CURRENT_TIMESTAMP |
| 6 | 상태 | text | 불가 | '정상'::text |
| 7 | 권한 | text | 불가 | '사용자'::text |

**제약조건**

| 종류 | 이름 | 정의 |
|---|---|---|
| PK | `pk_계정` | `PRIMARY KEY ("번호")` |
| UNIQUE | `uq_계정_아이디` | `UNIQUE ("아이디")` |
| CHECK | `ck_계정_권한` | `CHECK (("권한" = ANY (ARRAY['사용자'::text, '관리자'::text, '운영자'::text])))` |
| CHECK | `ck_계정_상태` | `CHECK (("상태" = ANY (ARRAY['정상'::text, '정지'::text, '탈퇴'::text])))` |

## 로그인세션

| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |
|---|---|---|---|---|
| 1 | 번호 | integer | 불가 | IDENTITY (GENERATED ALWAYS) |
| 2 | 계정_번호 | integer | 불가 |  |
| 3 | 토큰 | text | 불가 |  |
| 4 | 생성일시 | timestamp with time zone | 불가 | CURRENT_TIMESTAMP |
| 5 | 만료일시 | timestamp with time zone | 불가 |  |
| 6 | 폐기일시 | timestamp with time zone | 가능 |  |
| 7 | 접속환경 | text | 불가 |  |

**제약조건**

| 종류 | 이름 | 정의 |
|---|---|---|
| PK | `pk_로그인세션` | `PRIMARY KEY ("번호")` |
| UNIQUE | `uq_로그인세션_토큰` | `UNIQUE ("토큰")` |
| FK | `fk_로그인세션_계정` | `FOREIGN KEY ("계정_번호") REFERENCES "계정"("번호") ON DELETE CASCADE` |
| CHECK | `ck_로그인세션_만료` | `CHECK (("만료일시" > "생성일시"))` |
| CHECK | `ck_로그인세션_환경` | `CHECK (("접속환경" = ANY (ARRAY['PC'::text, '모바일'::text])))` |

**추가 인덱스** (PK/UNIQUE 제약이 만드는 인덱스는 제외)

- `ix_로그인세션_계정`: `CREATE INDEX "ix_로그인세션_계정" ON public."로그인세션" USING btree ("계정_번호")`

## 작품

| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |
|---|---|---|---|---|
| 1 | 번호 | integer | 불가 | IDENTITY (GENERATED ALWAYS) |
| 2 | 제목 | text | 불가 |  |
| 3 | 시놉시스 | text | 불가 |  |
| 4 | 장르 | text | 불가 |  |
| 5 | 최소인원 | integer | 불가 | 4 |
| 6 | 최대인원 | integer | 불가 | 4 |
| 7 | 예상시간 | text | 불가 | '3시간'::text |
| 8 | 상태 | text | 불가 | '개발'::text |
| 9 | 생성일시 | timestamp with time zone | 불가 | CURRENT_TIMESTAMP |
| 10 | 수정일시 | timestamp with time zone | 가능 |  |
| 11 | 최신버전 | text | 불가 | '1.0'::text |
| 12 | 계정_번호 | integer | 불가 |  |
| 13 | 공개여부 | boolean | 불가 | false |
| 14 | 공개권한 | text | 불가 | '제작자'::text |
| 15 | 공통스토리 | text | 가능 |  |
| 16 | 시간형식 | text | 불가 | '시간만'::text |

**제약조건**

| 종류 | 이름 | 정의 |
|---|---|---|
| PK | `pk_작품` | `PRIMARY KEY ("번호")` |
| FK | `fk_작품_계정` | `FOREIGN KEY ("계정_번호") REFERENCES "계정"("번호") ON DELETE RESTRICT` |
| CHECK | `ck_작품_공개권한` | `CHECK (("공개권한" = ANY (ARRAY['제작자'::text, '관리자'::text, '운영자'::text])))` |
| CHECK | `ck_작품_상태` | `CHECK (("상태" = ANY (ARRAY['수정'::text, '개발'::text, '완료'::text, '삭제'::text])))` |
| CHECK | `ck_작품_시간형식` | `CHECK (("시간형식" = ANY (ARRAY['시간만'::text, '일까지'::text, '월까지'::text, '연도까지'::text])))` |
| CHECK | `ck_작품_최대인원` | `CHECK (("최대인원" >= "최소인원"))` |
| CHECK | `ck_작품_최소인원` | `CHECK (("최소인원" >= 1))` |

**추가 인덱스** (PK/UNIQUE 제약이 만드는 인덱스는 제외)

- `ix_작품_계정`: `CREATE INDEX "ix_작품_계정" ON public."작품" USING btree ("계정_번호")`

## 버전

| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |
|---|---|---|---|---|
| 1 | 번호 | integer | 불가 | IDENTITY (GENERATED ALWAYS) |
| 2 | 작품_번호 | integer | 불가 |  |
| 3 | 시나리오 | jsonb | 불가 |  |
| 4 | 버전 | text | 불가 | '1.0'::text |
| 5 | 생성일시 | timestamp with time zone | 불가 | CURRENT_TIMESTAMP |
| 6 | 변경사항 | text | 가능 |  |

**제약조건**

| 종류 | 이름 | 정의 |
|---|---|---|
| PK | `pk_버전` | `PRIMARY KEY ("번호")` |
| UNIQUE | `uq_버전_작품_버전` | `UNIQUE ("작품_번호", "버전")` |
| FK | `fk_버전_작품` | `FOREIGN KEY ("작품_번호") REFERENCES "작품"("번호") ON DELETE CASCADE` |

**트리거**

- `tg_버전_불변`: `CREATE TRIGGER "tg_버전_불변" BEFORE UPDATE ON public."버전" FOR EACH ROW EXECUTE FUNCTION "fn_버전_불변"()`

## 진행단계

| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |
|---|---|---|---|---|
| 1 | 번호 | integer | 불가 | IDENTITY (GENERATED ALWAYS) |
| 2 | 이름 | text | 불가 |  |
| 3 | 규칙 | jsonb | 불가 |  |
| 4 | 설명 | text | 불가 |  |
| 5 | 계정_번호 | integer | 가능 |  |
| 6 | 버전 | integer | 불가 | 1 |
| 7 | 변경내역 | text | 가능 |  |
| 8 | 삭제일시 | timestamp with time zone | 가능 |  |
| 9 | 공개여부 | boolean | 불가 | false |

**제약조건**

| 종류 | 이름 | 정의 |
|---|---|---|
| PK | `pk_진행단계` | `PRIMARY KEY ("번호")` |
| UNIQUE | `uq_진행단계_계정_이름_버전` | `UNIQUE NULLS NOT DISTINCT ("계정_번호", "이름", "버전")` |
| FK | `fk_진행단계_계정` | `FOREIGN KEY ("계정_번호") REFERENCES "계정"("번호") ON DELETE RESTRICT` |
| CHECK | `ck_진행단계_버전` | `CHECK (("버전" >= 1))` |

**추가 인덱스** (PK/UNIQUE 제약이 만드는 인덱스는 제외)

- `ix_진행단계_계정`: `CREATE INDEX "ix_진행단계_계정" ON public."진행단계" USING btree ("계정_번호")`

**트리거**

- `tg_진행단계_불변`: `CREATE TRIGGER "tg_진행단계_불변" BEFORE UPDATE ON public."진행단계" FOR EACH ROW EXECUTE FUNCTION "fn_라이브러리_불변"()`

## 기믹

| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |
|---|---|---|---|---|
| 1 | 번호 | integer | 불가 | IDENTITY (GENERATED ALWAYS) |
| 2 | 계정_번호 | integer | 가능 |  |
| 3 | 이름 | text | 불가 |  |
| 4 | 설명 | text | 가능 |  |
| 5 | 조건 | jsonb | 불가 |  |
| 6 | 결과 | jsonb | 불가 |  |
| 7 | 버전 | integer | 불가 | 1 |
| 8 | 변경내역 | text | 가능 |  |
| 9 | 삭제일시 | timestamp with time zone | 가능 |  |
| 10 | 공개여부 | boolean | 불가 | false |

**제약조건**

| 종류 | 이름 | 정의 |
|---|---|---|
| PK | `pk_기믹` | `PRIMARY KEY ("번호")` |
| UNIQUE | `uq_기믹_계정_이름_버전` | `UNIQUE NULLS NOT DISTINCT ("계정_번호", "이름", "버전")` |
| FK | `fk_기믹_계정` | `FOREIGN KEY ("계정_번호") REFERENCES "계정"("번호") ON DELETE RESTRICT` |
| CHECK | `ck_기믹_버전` | `CHECK (("버전" >= 1))` |

**추가 인덱스** (PK/UNIQUE 제약이 만드는 인덱스는 제외)

- `ix_기믹_계정`: `CREATE INDEX "ix_기믹_계정" ON public."기믹" USING btree ("계정_번호")`

**트리거**

- `tg_기믹_불변`: `CREATE TRIGGER "tg_기믹_불변" BEFORE UPDATE ON public."기믹" FOR EACH ROW EXECUTE FUNCTION "fn_라이브러리_불변"()`

## 진행구성

| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |
|---|---|---|---|---|
| 1 | 번호 | integer | 불가 | IDENTITY (GENERATED ALWAYS) |
| 2 | 작품_번호 | integer | 불가 |  |
| 3 | 진행순서_순서 | integer | 불가 |  |
| 4 | 진행단계_번호 | integer | 불가 |  |
| 5 | 설정 | jsonb | 가능 |  |

**제약조건**

| 종류 | 이름 | 정의 |
|---|---|---|
| PK | `pk_진행구성` | `PRIMARY KEY ("번호")` |
| UNIQUE | `uq_진행구성_작품_순서_단계` | `UNIQUE ("작품_번호", "진행순서_순서", "진행단계_번호")` |
| FK | `fk_진행구성_작품` | `FOREIGN KEY ("작품_번호") REFERENCES "작품"("번호") ON DELETE CASCADE` |
| FK | `fk_진행구성_진행단계` | `FOREIGN KEY ("진행단계_번호") REFERENCES "진행단계"("번호") ON DELETE RESTRICT` |
| FK | `fk_진행구성_진행순서` | `FOREIGN KEY ("작품_번호", "진행순서_순서") REFERENCES "진행순서"("작품_번호", "순서") ON DELETE CASCADE` |

**추가 인덱스** (PK/UNIQUE 제약이 만드는 인덱스는 제외)

- `ix_진행구성_진행단계`: `CREATE INDEX "ix_진행구성_진행단계" ON public."진행구성" USING btree ("진행단계_번호")`

## 기믹적용

| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |
|---|---|---|---|---|
| 1 | 번호 | integer | 불가 | IDENTITY (GENERATED ALWAYS) |
| 2 | 작품_번호 | integer | 불가 |  |
| 3 | 순서 | integer | 불가 |  |
| 4 | 기믹_번호 | integer | 불가 |  |
| 5 | 진행순서_순서 | integer | 불가 |  |
| 6 | 설정 | jsonb | 가능 |  |

**제약조건**

| 종류 | 이름 | 정의 |
|---|---|---|
| PK | `pk_기믹적용` | `PRIMARY KEY ("번호")` |
| UNIQUE | `uq_기믹적용_작품_순서` | `UNIQUE ("작품_번호", "순서")` |
| FK | `fk_기믹적용_기믹` | `FOREIGN KEY ("기믹_번호") REFERENCES "기믹"("번호") ON DELETE RESTRICT` |
| FK | `fk_기믹적용_작품` | `FOREIGN KEY ("작품_번호") REFERENCES "작품"("번호") ON DELETE CASCADE` |
| FK | `fk_기믹적용_진행순서` | `FOREIGN KEY ("작품_번호", "진행순서_순서") REFERENCES "진행순서"("작품_번호", "순서") ON DELETE RESTRICT` |
| CHECK | `ck_기믹적용_순서` | `CHECK (("순서" >= 1))` |

**추가 인덱스** (PK/UNIQUE 제약이 만드는 인덱스는 제외)

- `ix_기믹적용_기믹`: `CREATE INDEX "ix_기믹적용_기믹" ON public."기믹적용" USING btree ("기믹_번호")`
- `ix_기믹적용_진행순서`: `CREATE INDEX "ix_기믹적용_진행순서" ON public."기믹적용" USING btree ("작품_번호", "진행순서_순서")`

## 인물

| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |
|---|---|---|---|---|
| 1 | 번호 | integer | 불가 | IDENTITY (GENERATED ALWAYS) |
| 2 | 작품_번호 | integer | 불가 |  |
| 3 | 순서 | integer | 불가 |  |
| 4 | 이름 | text | 불가 |  |
| 5 | 직업 | text | 가능 |  |
| 6 | 나이 | integer | 가능 |  |
| 7 | 성별 | text | 가능 |  |
| 8 | 서사 | text | 불가 |  |
| 9 | 타임라인 | text | 가능 |  |
| 10 | 능력 | text | 가능 |  |
| 11 | 비밀 | text | 가능 |  |
| 12 | 목표 | text | 가능 |  |
| 13 | 범인 | boolean | 불가 | false |
| 14 | NPC | boolean | 불가 | false |
| 15 | 소개 | text | 가능 |  |
| 16 | 캐릭터설명 | text | 가능 |  |
| 17 | NPC순위 | integer | 가능 |  |

**제약조건**

| 종류 | 이름 | 정의 |
|---|---|---|
| PK | `pk_인물` | `PRIMARY KEY ("번호")` |
| UNIQUE | `uq_인물_작품_순서` | `UNIQUE ("작품_번호", "순서")` |
| FK | `fk_인물_작품` | `FOREIGN KEY ("작품_번호") REFERENCES "작품"("번호") ON DELETE CASCADE` |
| CHECK | `ck_인물_NPC순위` | `CHECK ((("NPC순위" IS NULL) OR (("NPC순위" >= 1) AND (NOT "NPC"))))` |
| CHECK | `ck_인물_순서` | `CHECK (("순서" >= 1))` |

**추가 인덱스** (PK/UNIQUE 제약이 만드는 인덱스는 제외)

- `uq_인물_NPC순위`: `CREATE UNIQUE INDEX "uq_인물_NPC순위" ON public."인물" USING btree ("작품_번호", "NPC순위") WHERE ("NPC순위" IS NOT NULL)`

## 관계

| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |
|---|---|---|---|---|
| 1 | 번호 | integer | 불가 | IDENTITY (GENERATED ALWAYS) |
| 2 | 작품_번호 | integer | 불가 |  |
| 3 | 인물_순서 | integer | 불가 |  |
| 4 | 대상_인물_순서 | integer | 불가 |  |
| 5 | 관계 | text | 불가 |  |

**제약조건**

| 종류 | 이름 | 정의 |
|---|---|---|
| PK | `pk_관계` | `PRIMARY KEY ("번호")` |
| FK | `fk_관계_대상인물` | `FOREIGN KEY ("작품_번호", "대상_인물_순서") REFERENCES "인물"("작품_번호", "순서") ON DELETE CASCADE` |
| FK | `fk_관계_인물` | `FOREIGN KEY ("작품_번호", "인물_순서") REFERENCES "인물"("작품_번호", "순서") ON DELETE CASCADE` |
| FK | `fk_관계_작품` | `FOREIGN KEY ("작품_번호") REFERENCES "작품"("번호") ON DELETE CASCADE` |

**추가 인덱스** (PK/UNIQUE 제약이 만드는 인덱스는 제외)

- `ix_관계_대상인물`: `CREATE INDEX "ix_관계_대상인물" ON public."관계" USING btree ("작품_번호", "대상_인물_순서")`
- `ix_관계_인물`: `CREATE INDEX "ix_관계_인물" ON public."관계" USING btree ("작품_번호", "인물_순서")`

## 장소

| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |
|---|---|---|---|---|
| 1 | 번호 | integer | 불가 | IDENTITY (GENERATED ALWAYS) |
| 2 | 작품_번호 | integer | 불가 |  |
| 3 | 순서 | integer | 불가 |  |
| 4 | 상위_장소_순서 | integer | 가능 |  |
| 5 | 이름 | text | 불가 |  |
| 6 | 유형 | text | 가능 |  |
| 7 | 특징 | text | 가능 |  |

**제약조건**

| 종류 | 이름 | 정의 |
|---|---|---|
| PK | `pk_장소` | `PRIMARY KEY ("번호")` |
| UNIQUE | `uq_장소_작품_순서` | `UNIQUE ("작품_번호", "순서")` |
| FK | `fk_장소_상위장소` | `FOREIGN KEY ("작품_번호", "상위_장소_순서") REFERENCES "장소"("작품_번호", "순서") ON DELETE RESTRICT` |
| FK | `fk_장소_작품` | `FOREIGN KEY ("작품_번호") REFERENCES "작품"("번호") ON DELETE CASCADE` |
| CHECK | `ck_장소_순서` | `CHECK (("순서" >= 1))` |

**추가 인덱스** (PK/UNIQUE 제약이 만드는 인덱스는 제외)

- `ix_장소_상위장소`: `CREATE INDEX "ix_장소_상위장소" ON public."장소" USING btree ("작품_번호", "상위_장소_순서")`

## 단서

| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |
|---|---|---|---|---|
| 1 | 번호 | integer | 불가 | IDENTITY (GENERATED ALWAYS) |
| 2 | 작품_번호 | integer | 불가 |  |
| 3 | 순서 | integer | 불가 |  |
| 4 | 이름 | text | 불가 |  |
| 5 | 내용 | text | 가능 |  |
| 6 | 기능 | text | 가능 |  |
| 7 | 인물_순서 | integer | 가능 |  |
| 8 | 장소_순서 | integer | 가능 |  |
| 9 | 공개이름 | text | 가능 |  |

**제약조건**

| 종류 | 이름 | 정의 |
|---|---|---|
| PK | `pk_단서` | `PRIMARY KEY ("번호")` |
| UNIQUE | `uq_단서_작품_순서` | `UNIQUE ("작품_번호", "순서")` |
| FK | `fk_단서_인물` | `FOREIGN KEY ("작품_번호", "인물_순서") REFERENCES "인물"("작품_번호", "순서") ON DELETE RESTRICT` |
| FK | `fk_단서_작품` | `FOREIGN KEY ("작품_번호") REFERENCES "작품"("번호") ON DELETE CASCADE` |
| FK | `fk_단서_장소` | `FOREIGN KEY ("작품_번호", "장소_순서") REFERENCES "장소"("작품_번호", "순서") ON DELETE RESTRICT` |
| CHECK | `ck_단서_순서` | `CHECK (("순서" >= 1))` |

**추가 인덱스** (PK/UNIQUE 제약이 만드는 인덱스는 제외)

- `ix_단서_인물`: `CREATE INDEX "ix_단서_인물" ON public."단서" USING btree ("작품_번호", "인물_순서")`
- `ix_단서_장소`: `CREATE INDEX "ix_단서_장소" ON public."단서" USING btree ("작품_번호", "장소_순서")`

## 증언

| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |
|---|---|---|---|---|
| 1 | 번호 | integer | 불가 | IDENTITY (GENERATED ALWAYS) |
| 2 | 작품_번호 | integer | 불가 |  |
| 3 | 순서 | integer | 불가 |  |
| 4 | 공개이름 | text | 가능 |  |
| 5 | 내용 | text | 불가 |  |
| 6 | 인물_순서 | integer | 가능 |  |
| 7 | 장소_순서 | integer | 가능 |  |
| 8 | 이름 | text | 불가 |  |

**제약조건**

| 종류 | 이름 | 정의 |
|---|---|---|
| PK | `pk_증언` | `PRIMARY KEY ("번호")` |
| UNIQUE | `uq_증언_작품_순서` | `UNIQUE ("작품_번호", "순서")` |
| FK | `fk_증언_인물` | `FOREIGN KEY ("작품_번호", "인물_순서") REFERENCES "인물"("작품_번호", "순서") ON DELETE RESTRICT` |
| FK | `fk_증언_작품` | `FOREIGN KEY ("작품_번호") REFERENCES "작품"("번호") ON DELETE CASCADE` |
| FK | `fk_증언_장소` | `FOREIGN KEY ("작품_번호", "장소_순서") REFERENCES "장소"("작품_번호", "순서") ON DELETE RESTRICT` |
| CHECK | `ck_증언_순서` | `CHECK (("순서" >= 1))` |

**추가 인덱스** (PK/UNIQUE 제약이 만드는 인덱스는 제외)

- `ix_증언_인물`: `CREATE INDEX "ix_증언_인물" ON public."증언" USING btree ("작품_번호", "인물_순서")`
- `ix_증언_장소`: `CREATE INDEX "ix_증언_장소" ON public."증언" USING btree ("작품_번호", "장소_순서")`

## 조합

| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |
|---|---|---|---|---|
| 1 | 번호 | integer | 불가 | IDENTITY (GENERATED ALWAYS) |
| 2 | 작품_번호 | integer | 불가 |  |
| 3 | 순서 | integer | 불가 |  |
| 4 | 이름 | text | 불가 |  |
| 5 | 내용 | text | 가능 |  |
| 6 | 기능 | text | 가능 |  |
| 7 | 공개이름 | text | 가능 |  |

**제약조건**

| 종류 | 이름 | 정의 |
|---|---|---|
| PK | `pk_조합` | `PRIMARY KEY ("번호")` |
| UNIQUE | `uq_조합_작품_순서` | `UNIQUE ("작품_번호", "순서")` |
| FK | `fk_조합_작품` | `FOREIGN KEY ("작품_번호") REFERENCES "작품"("번호") ON DELETE CASCADE` |
| CHECK | `ck_조합_순서` | `CHECK (("순서" >= 1))` |

## 조합재료

| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |
|---|---|---|---|---|
| 1 | 번호 | integer | 불가 | IDENTITY (GENERATED ALWAYS) |
| 2 | 작품_번호 | integer | 불가 |  |
| 3 | 결과_조합_순서 | integer | 불가 |  |
| 4 | 단서_순서 | integer | 가능 |  |
| 5 | 증언_순서 | integer | 가능 |  |
| 6 | 조합_순서 | integer | 가능 |  |

**제약조건**

| 종류 | 이름 | 정의 |
|---|---|---|
| PK | `pk_조합재료` | `PRIMARY KEY ("번호")` |
| FK | `fk_조합재료_결과조합` | `FOREIGN KEY ("작품_번호", "결과_조합_순서") REFERENCES "조합"("작품_번호", "순서") ON DELETE CASCADE` |
| FK | `fk_조합재료_단서` | `FOREIGN KEY ("작품_번호", "단서_순서") REFERENCES "단서"("작품_번호", "순서") ON DELETE RESTRICT` |
| FK | `fk_조합재료_작품` | `FOREIGN KEY ("작품_번호") REFERENCES "작품"("번호") ON DELETE CASCADE` |
| FK | `fk_조합재료_조합` | `FOREIGN KEY ("작품_번호", "조합_순서") REFERENCES "조합"("작품_번호", "순서") ON DELETE RESTRICT` |
| FK | `fk_조합재료_증언` | `FOREIGN KEY ("작품_번호", "증언_순서") REFERENCES "증언"("작품_번호", "순서") ON DELETE RESTRICT` |
| CHECK | `ck_조합재료_재료하나` | `CHECK ((num_nonnulls("단서_순서", "증언_순서", "조합_순서") = 1))` |

**추가 인덱스** (PK/UNIQUE 제약이 만드는 인덱스는 제외)

- `ix_조합재료_결과조합`: `CREATE INDEX "ix_조합재료_결과조합" ON public."조합재료" USING btree ("작품_번호", "결과_조합_순서")`
- `ix_조합재료_단서`: `CREATE INDEX "ix_조합재료_단서" ON public."조합재료" USING btree ("작품_번호", "단서_순서")`
- `ix_조합재료_조합`: `CREATE INDEX "ix_조합재료_조합" ON public."조합재료" USING btree ("작품_번호", "조합_순서")`
- `ix_조합재료_증언`: `CREATE INDEX "ix_조합재료_증언" ON public."조합재료" USING btree ("작품_번호", "증언_순서")`

## 사건

| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |
|---|---|---|---|---|
| 1 | 번호 | integer | 불가 | IDENTITY (GENERATED ALWAYS) |
| 2 | 작품_번호 | integer | 불가 |  |
| 3 | 순서 | integer | 불가 |  |
| 4 | 설명 | text | 가능 |  |

**제약조건**

| 종류 | 이름 | 정의 |
|---|---|---|
| PK | `pk_사건` | `PRIMARY KEY ("번호")` |
| UNIQUE | `uq_사건_작품_순서` | `UNIQUE ("작품_번호", "순서")` |
| FK | `fk_사건_작품` | `FOREIGN KEY ("작품_번호") REFERENCES "작품"("번호") ON DELETE CASCADE` |
| CHECK | `ck_사건_순서` | `CHECK (("순서" >= 1))` |

## 사건설명

| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |
|---|---|---|---|---|
| 1 | 번호 | integer | 불가 | IDENTITY (GENERATED ALWAYS) |
| 2 | 작품_번호 | integer | 불가 |  |
| 3 | 사건_순서 | integer | 불가 |  |
| 4 | 인물_순서 | integer | 가능 |  |
| 5 | 상태 | text | 가능 |  |
| 6 | 설명 | text | 가능 |  |
| 7 | 추정발생시간 | timestamp without time zone | 가능 |  |
| 8 | 추정종료시간 | timestamp without time zone | 가능 |  |

**제약조건**

| 종류 | 이름 | 정의 |
|---|---|---|
| PK | `pk_사건설명` | `PRIMARY KEY ("번호")` |
| FK | `fk_사건설명_사건` | `FOREIGN KEY ("작품_번호", "사건_순서") REFERENCES "사건"("작품_번호", "순서") ON DELETE CASCADE` |
| FK | `fk_사건설명_인물` | `FOREIGN KEY ("작품_번호", "인물_순서") REFERENCES "인물"("작품_번호", "순서") ON DELETE RESTRICT` |
| FK | `fk_사건설명_작품` | `FOREIGN KEY ("작품_번호") REFERENCES "작품"("번호") ON DELETE CASCADE` |

**추가 인덱스** (PK/UNIQUE 제약이 만드는 인덱스는 제외)

- `ix_사건설명_사건`: `CREATE INDEX "ix_사건설명_사건" ON public."사건설명" USING btree ("작품_번호", "사건_순서")`
- `ix_사건설명_인물`: `CREATE INDEX "ix_사건설명_인물" ON public."사건설명" USING btree ("작품_번호", "인물_순서")`

## 타임라인

| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |
|---|---|---|---|---|
| 1 | 번호 | integer | 불가 | IDENTITY (GENERATED ALWAYS) |
| 2 | 작품_번호 | integer | 불가 |  |
| 3 | 순서 | integer | 불가 |  |
| 4 | 시작시간 | timestamp without time zone | 가능 |  |
| 5 | 종료시간 | timestamp without time zone | 가능 |  |
| 6 | 설명 | text | 불가 |  |

**제약조건**

| 종류 | 이름 | 정의 |
|---|---|---|
| PK | `pk_타임라인` | `PRIMARY KEY ("번호")` |
| UNIQUE | `uq_타임라인_작품_순서` | `UNIQUE ("작품_번호", "순서")` |
| FK | `fk_타임라인_작품` | `FOREIGN KEY ("작품_번호") REFERENCES "작품"("번호") ON DELETE CASCADE` |
| CHECK | `ck_타임라인_순서` | `CHECK (("순서" >= 1))` |

## 후일담

| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |
|---|---|---|---|---|
| 1 | 번호 | integer | 불가 | IDENTITY (GENERATED ALWAYS) |
| 2 | 작품_번호 | integer | 불가 |  |
| 3 | 순서 | integer | 불가 |  |
| 4 | 인물_순서 | integer | 가능 |  |
| 5 | 조건 | jsonb | 가능 |  |
| 6 | 내용 | text | 불가 |  |

**제약조건**

| 종류 | 이름 | 정의 |
|---|---|---|
| PK | `pk_후일담` | `PRIMARY KEY ("번호")` |
| UNIQUE | `uq_후일담_작품_순서` | `UNIQUE ("작품_번호", "순서")` |
| FK | `fk_후일담_인물` | `FOREIGN KEY ("작품_번호", "인물_순서") REFERENCES "인물"("작품_번호", "순서") ON DELETE RESTRICT` |
| FK | `fk_후일담_작품` | `FOREIGN KEY ("작품_번호") REFERENCES "작품"("번호") ON DELETE CASCADE` |
| CHECK | `ck_후일담_순서` | `CHECK (("순서" >= 1))` |

**추가 인덱스** (PK/UNIQUE 제약이 만드는 인덱스는 제외)

- `ix_후일담_인물`: `CREATE INDEX "ix_후일담_인물" ON public."후일담" USING btree ("작품_번호", "인물_순서")`

## 투표

| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |
|---|---|---|---|---|
| 1 | 번호 | integer | 불가 | IDENTITY (GENERATED ALWAYS) |
| 2 | 작품_번호 | integer | 불가 |  |
| 3 | 순서 | integer | 불가 |  |
| 4 | 진행순서_순서 | integer | 불가 |  |
| 5 | 이름 | text | 불가 |  |
| 6 | 내용 | text | 불가 |  |
| 7 | 규칙 | jsonb | 불가 |  |

**제약조건**

| 종류 | 이름 | 정의 |
|---|---|---|
| PK | `pk_투표` | `PRIMARY KEY ("번호")` |
| UNIQUE | `uq_투표_작품_순서` | `UNIQUE ("작품_번호", "순서")` |
| FK | `fk_투표_작품` | `FOREIGN KEY ("작품_번호") REFERENCES "작품"("번호") ON DELETE CASCADE` |
| FK | `fk_투표_진행순서` | `FOREIGN KEY ("작품_번호", "진행순서_순서") REFERENCES "진행순서"("작품_번호", "순서") ON DELETE RESTRICT` |
| CHECK | `ck_투표_순서` | `CHECK (("순서" >= 1))` |

**추가 인덱스** (PK/UNIQUE 제약이 만드는 인덱스는 제외)

- `ix_투표_진행순서`: `CREATE INDEX "ix_투표_진행순서" ON public."투표" USING btree ("작품_번호", "진행순서_순서")`

## 미디어

| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |
|---|---|---|---|---|
| 1 | 번호 | integer | 불가 | IDENTITY (GENERATED ALWAYS) |
| 2 | 작품_번호 | integer | 불가 |  |
| 3 | 순서 | integer | 불가 |  |
| 4 | 단서_순서 | integer | 가능 |  |
| 5 | 증언_순서 | integer | 가능 |  |
| 6 | 조합_순서 | integer | 가능 |  |
| 7 | 진행순서_순서 | integer | 가능 |  |
| 8 | 조건 | jsonb | 가능 |  |
| 9 | 유형 | text | 불가 |  |
| 10 | 경로 | text | 불가 |  |
| 11 | 인물_순서 | integer | 가능 |  |
| 12 | 공통스토리 | boolean | 불가 | false |
| 13 | 표지 | boolean | 불가 | false |

**제약조건**

| 종류 | 이름 | 정의 |
|---|---|---|
| PK | `pk_미디어` | `PRIMARY KEY ("번호")` |
| UNIQUE | `uq_미디어_작품_순서` | `UNIQUE ("작품_번호", "순서")` |
| FK | `fk_미디어_단서` | `FOREIGN KEY ("작품_번호", "단서_순서") REFERENCES "단서"("작품_번호", "순서") ON DELETE RESTRICT` |
| FK | `fk_미디어_인물` | `FOREIGN KEY ("작품_번호", "인물_순서") REFERENCES "인물"("작품_번호", "순서") ON DELETE RESTRICT` |
| FK | `fk_미디어_작품` | `FOREIGN KEY ("작품_번호") REFERENCES "작품"("번호") ON DELETE CASCADE` |
| FK | `fk_미디어_조합` | `FOREIGN KEY ("작품_번호", "조합_순서") REFERENCES "조합"("작품_번호", "순서") ON DELETE RESTRICT` |
| FK | `fk_미디어_증언` | `FOREIGN KEY ("작품_번호", "증언_순서") REFERENCES "증언"("작품_번호", "순서") ON DELETE RESTRICT` |
| FK | `fk_미디어_진행순서` | `FOREIGN KEY ("작품_번호", "진행순서_순서") REFERENCES "진행순서"("작품_번호", "순서") ON DELETE RESTRICT` |
| CHECK | `ck_미디어_대상` | `CHECK ((((num_nonnulls("단서_순서", "증언_순서", "조합_순서", "진행순서_순서", "인물_순서") + CASE WHEN "공통스토리" THEN 1 ELSE 0 END) + CASE WHEN "표지" THEN 1 ELSE 0 END) = 1))` |
| CHECK | `ck_미디어_순서` | `CHECK (("순서" >= 1))` |
| CHECK | `ck_미디어_유형` | `CHECK (("유형" = ANY (ARRAY['이미지'::text, '영상'::text])))` |

**추가 인덱스** (PK/UNIQUE 제약이 만드는 인덱스는 제외)

- `ix_미디어_단서`: `CREATE INDEX "ix_미디어_단서" ON public."미디어" USING btree ("작품_번호", "단서_순서")`
- `ix_미디어_인물`: `CREATE INDEX "ix_미디어_인물" ON public."미디어" USING btree ("작품_번호", "인물_순서")`
- `ix_미디어_조합`: `CREATE INDEX "ix_미디어_조합" ON public."미디어" USING btree ("작품_번호", "조합_순서")`
- `ix_미디어_증언`: `CREATE INDEX "ix_미디어_증언" ON public."미디어" USING btree ("작품_번호", "증언_순서")`
- `ix_미디어_진행순서`: `CREATE INDEX "ix_미디어_진행순서" ON public."미디어" USING btree ("작품_번호", "진행순서_순서")`

## 방

| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |
|---|---|---|---|---|
| 1 | 번호 | integer | 불가 | IDENTITY (GENERATED ALWAYS) |
| 2 | 계정_번호 | integer | 불가 |  |
| 3 | 입장코드 | text | 불가 |  |
| 4 | 상태 | text | 불가 | '대기'::text |
| 5 | 생성일시 | timestamp with time zone | 불가 | CURRENT_TIMESTAMP |
| 6 | 상태변경일시 | timestamp with time zone | 불가 | CURRENT_TIMESTAMP |
| 7 | 종료일시 | timestamp with time zone | 가능 |  |
| 8 | 작품_번호 | integer | 불가 |  |
| 9 | 버전_버전 | text | 불가 |  |

**제약조건**

| 종류 | 이름 | 정의 |
|---|---|---|
| PK | `pk_방` | `PRIMARY KEY ("번호")` |
| UNIQUE | `uq_방_번호_작품_버전` | `UNIQUE ("번호", "작품_번호", "버전_버전")` |
| FK | `fk_방_계정` | `FOREIGN KEY ("계정_번호") REFERENCES "계정"("번호") ON DELETE RESTRICT` |
| FK | `fk_방_버전` | `FOREIGN KEY ("작품_번호", "버전_버전") REFERENCES "버전"("작품_번호", "버전") ON DELETE RESTRICT` |
| FK | `fk_방_작품` | `FOREIGN KEY ("작품_번호") REFERENCES "작품"("번호") ON DELETE RESTRICT` |
| CHECK | `ck_방_상태` | `CHECK (("상태" = ANY (ARRAY['대기'::text, '진행'::text, '종료'::text])))` |

**추가 인덱스** (PK/UNIQUE 제약이 만드는 인덱스는 제외)

- `ix_방_계정`: `CREATE INDEX "ix_방_계정" ON public."방" USING btree ("계정_번호")`
- `ix_방_버전`: `CREATE INDEX "ix_방_버전" ON public."방" USING btree ("작품_번호", "버전_버전")`
- `uq_방_입장코드_사용중`: `CREATE UNIQUE INDEX "uq_방_입장코드_사용중" ON public."방" USING btree ("입장코드") WHERE ("상태" <> '종료'::text)`

**트리거**

- `tg_방_시각`: `CREATE TRIGGER "tg_방_시각" BEFORE INSERT OR UPDATE ON public."방" FOR EACH ROW EXECUTE FUNCTION "fn_방_시각"()`

## 진행

| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |
|---|---|---|---|---|
| 1 | 번호 | integer | 불가 | IDENTITY (GENERATED ALWAYS) |
| 2 | 방_번호 | integer | 불가 |  |
| 3 | 작품_번호 | integer | 불가 |  |
| 4 | 버전_버전 | text | 불가 |  |
| 5 | 진행순서_순서 | integer | 가능 |  |
| 6 | 시작일시 | timestamp with time zone | 불가 | CURRENT_TIMESTAMP |
| 7 | 종료일시 | timestamp with time zone | 가능 |  |
| 8 | 상태 | text | 불가 | '진행'::text |

**제약조건**

| 종류 | 이름 | 정의 |
|---|---|---|
| PK | `pk_진행` | `PRIMARY KEY ("번호")` |
| UNIQUE | `uq_진행_방` | `UNIQUE ("방_번호")` |
| FK | `fk_진행_방` | `FOREIGN KEY ("방_번호") REFERENCES "방"("번호") ON DELETE RESTRICT` |
| FK | `fk_진행_방_작품_버전` | `FOREIGN KEY ("방_번호", "작품_번호", "버전_버전") REFERENCES "방"("번호", "작품_번호", "버전_버전") ON DELETE RESTRICT` |
| FK | `fk_진행_버전` | `FOREIGN KEY ("작품_번호", "버전_버전") REFERENCES "버전"("작품_번호", "버전") ON DELETE RESTRICT` |
| FK | `fk_진행_작품` | `FOREIGN KEY ("작품_번호") REFERENCES "작품"("번호") ON DELETE RESTRICT` |
| CHECK | `ck_진행_상태` | `CHECK (("상태" = ANY (ARRAY['진행'::text, '종료'::text])))` |

**추가 인덱스** (PK/UNIQUE 제약이 만드는 인덱스는 제외)

- `ix_진행_방`: `CREATE INDEX "ix_진행_방" ON public."진행" USING btree ("방_번호")`
- `ix_진행_방_작품_버전`: `CREATE INDEX "ix_진행_방_작품_버전" ON public."진행" USING btree ("방_번호", "작품_번호", "버전_버전")`
- `ix_진행_버전`: `CREATE INDEX "ix_진행_버전" ON public."진행" USING btree ("작품_번호", "버전_버전")`

**트리거**

- `tg_진행_시각`: `CREATE TRIGGER "tg_진행_시각" BEFORE INSERT OR UPDATE ON public."진행" FOR EACH ROW EXECUTE FUNCTION "fn_진행_시각"()`

## 기믹실행

| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |
|---|---|---|---|---|
| 1 | 번호 | integer | 불가 | IDENTITY (GENERATED ALWAYS) |
| 2 | 작품_번호 | integer | 불가 |  |
| 3 | 진행_번호 | integer | 불가 |  |
| 4 | 기믹적용_순서 | integer | 불가 |  |
| 5 | 실행여부 | boolean | 불가 | false |
| 6 | 결과 | jsonb | 가능 |  |

**제약조건**

| 종류 | 이름 | 정의 |
|---|---|---|
| PK | `pk_기믹실행` | `PRIMARY KEY ("번호")` |
| UNIQUE | `uq_기믹실행_진행_적용` | `UNIQUE ("진행_번호", "기믹적용_순서")` |
| FK | `fk_기믹실행_작품` | `FOREIGN KEY ("작품_번호") REFERENCES "작품"("번호") ON DELETE RESTRICT` |
| FK | `fk_기믹실행_진행` | `FOREIGN KEY ("진행_번호") REFERENCES "진행"("번호") ON DELETE CASCADE` |

**추가 인덱스** (PK/UNIQUE 제약이 만드는 인덱스는 제외)

- `ix_기믹실행_작품`: `CREATE INDEX "ix_기믹실행_작품" ON public."기믹실행" USING btree ("작품_번호")`

## 엔딩

| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |
|---|---|---|---|---|
| 1 | 번호 | integer | 불가 | IDENTITY (GENERATED ALWAYS) |
| 2 | 작품_번호 | integer | 불가 |  |
| 3 | 진행_번호 | integer | 불가 |  |
| 4 | 순서 | integer | 불가 |  |
| 5 | 엔딩분기_순서 | integer | 가능 |  |
| 6 | 후일담_순서 | integer | 가능 |  |

**제약조건**

| 종류 | 이름 | 정의 |
|---|---|---|
| PK | `pk_엔딩` | `PRIMARY KEY ("번호")` |
| UNIQUE | `uq_엔딩_진행_순서` | `UNIQUE ("진행_번호", "순서")` |
| FK | `fk_엔딩_작품` | `FOREIGN KEY ("작품_번호") REFERENCES "작품"("번호") ON DELETE RESTRICT` |
| FK | `fk_엔딩_진행` | `FOREIGN KEY ("진행_번호") REFERENCES "진행"("번호") ON DELETE CASCADE` |
| CHECK | `ck_엔딩_순서` | `CHECK (("순서" >= 1))` |
| CHECK | `ck_엔딩_하나` | `CHECK ((num_nonnulls("엔딩분기_순서", "후일담_순서") = 1))` |

**추가 인덱스** (PK/UNIQUE 제약이 만드는 인덱스는 제외)

- `ix_엔딩_작품`: `CREATE INDEX "ix_엔딩_작품" ON public."엔딩" USING btree ("작품_번호")`

## 획득

| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |
|---|---|---|---|---|
| 1 | 번호 | integer | 불가 | IDENTITY (GENERATED ALWAYS) |
| 2 | 작품_번호 | integer | 불가 |  |
| 3 | 진행_번호 | integer | 불가 |  |
| 4 | 참여_번호 | integer | 불가 |  |
| 5 | 단서_순서 | integer | 가능 |  |
| 6 | 증언_순서 | integer | 가능 |  |
| 7 | 조합_순서 | integer | 가능 |  |
| 8 | 진행순서_순서 | integer | 불가 |  |
| 9 | 획득방법 | text | 불가 |  |
| 10 | 보유여부 | boolean | 불가 | true |

**제약조건**

| 종류 | 이름 | 정의 |
|---|---|---|
| PK | `pk_획득` | `PRIMARY KEY ("번호")` |
| FK | `fk_획득_작품` | `FOREIGN KEY ("작품_번호") REFERENCES "작품"("번호") ON DELETE RESTRICT` |
| FK | `fk_획득_진행` | `FOREIGN KEY ("진행_번호") REFERENCES "진행"("번호") ON DELETE CASCADE` |
| FK | `fk_획득_참여` | `FOREIGN KEY ("참여_번호") REFERENCES "참여"("번호") ON DELETE CASCADE` |
| CHECK | `ck_획득_하나` | `CHECK ((num_nonnulls("단서_순서", "증언_순서", "조합_순서") = 1))` |

**추가 인덱스** (PK/UNIQUE 제약이 만드는 인덱스는 제외)

- `ix_획득_작품`: `CREATE INDEX "ix_획득_작품" ON public."획득" USING btree ("작품_번호")`
- `ix_획득_진행`: `CREATE INDEX "ix_획득_진행" ON public."획득" USING btree ("진행_번호")`
- `ix_획득_참여`: `CREATE INDEX "ix_획득_참여" ON public."획득" USING btree ("참여_번호")`

## 테스터

| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |
|---|---|---|---|---|
| 1 | 번호 | integer | 불가 | IDENTITY (GENERATED ALWAYS) |
| 2 | 작품_번호 | integer | 불가 |  |
| 3 | 계정_번호 | integer | 불가 |  |
| 4 | 부여일시 | timestamp with time zone | 불가 | CURRENT_TIMESTAMP |

**제약조건**

| 종류 | 이름 | 정의 |
|---|---|---|
| PK | `pk_테스터` | `PRIMARY KEY ("번호")` |
| UNIQUE | `uq_테스터_작품_계정` | `UNIQUE ("작품_번호", "계정_번호")` |
| FK | `fk_테스터_계정` | `FOREIGN KEY ("계정_번호") REFERENCES "계정"("번호") ON DELETE CASCADE` |
| FK | `fk_테스터_작품` | `FOREIGN KEY ("작품_번호") REFERENCES "작품"("번호") ON DELETE CASCADE` |

**추가 인덱스** (PK/UNIQUE 제약이 만드는 인덱스는 제외)

- `ix_테스터_계정`: `CREATE INDEX "ix_테스터_계정" ON public."테스터" USING btree ("계정_번호")`

## 자료

| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |
|---|---|---|---|---|
| 1 | 번호 | integer | 불가 | IDENTITY (GENERATED ALWAYS) |
| 2 | 작품_번호 | integer | 불가 |  |
| 3 | 순서 | integer | 불가 |  |
| 4 | 제목 | text | 불가 |  |
| 5 | 내용 | text | 불가 |  |

**제약조건**

| 종류 | 이름 | 정의 |
|---|---|---|
| PK | `pk_자료` | `PRIMARY KEY ("번호")` |
| UNIQUE | `uq_자료_작품_순서` | `UNIQUE ("작품_번호", "순서")` |
| FK | `fk_자료_작품` | `FOREIGN KEY ("작품_번호") REFERENCES "작품"("번호") ON DELETE CASCADE` |
| CHECK | `ck_자료_순서` | `CHECK (("순서" >= 1))` |

## 참여

| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |
|---|---|---|---|---|
| 1 | 번호 | integer | 불가 | IDENTITY (GENERATED ALWAYS) |
| 2 | 작품_번호 | integer | 불가 |  |
| 3 | 진행_번호 | integer | 불가 |  |
| 4 | 계정_번호 | integer | 불가 |  |
| 5 | 인물_순서 | integer | 가능 |  |
| 6 | 평점 | numeric(2,1) | 가능 |  |
| 7 | 난이도 | numeric(2,1) | 가능 |  |
| 8 | 후기 | text | 가능 |  |
| 9 | 후기공개 | boolean | 불가 | true |
| 10 | 메모 | text | 가능 |  |

**제약조건**

| 종류 | 이름 | 정의 |
|---|---|---|
| PK | `pk_참여` | `PRIMARY KEY ("번호")` |
| UNIQUE | `uq_참여_진행_계정` | `UNIQUE ("진행_번호", "계정_번호")` |
| UNIQUE | `uq_참여_진행_인물` | `UNIQUE ("진행_번호", "인물_순서")` |
| FK | `fk_참여_계정` | `FOREIGN KEY ("계정_번호") REFERENCES "계정"("번호") ON DELETE RESTRICT` |
| FK | `fk_참여_작품` | `FOREIGN KEY ("작품_번호") REFERENCES "작품"("번호") ON DELETE RESTRICT` |
| FK | `fk_참여_진행` | `FOREIGN KEY ("진행_번호") REFERENCES "진행"("번호") ON DELETE CASCADE` |
| CHECK | `ck_참여_난이도` | `CHECK ((("난이도" IS NULL) OR ((("난이도" >= (0)::numeric) AND ("난이도" <= (5)::numeric)) AND (("난이도" * (2)::numeric) = trunc(("난이도" * (2)::numeric))))))` |
| CHECK | `ck_참여_평점` | `CHECK ((("평점" IS NULL) OR ((("평점" >= (0)::numeric) AND ("평점" <= (5)::numeric)) AND (("평점" * (2)::numeric) = trunc(("평점" * (2)::numeric))))))` |

**추가 인덱스** (PK/UNIQUE 제약이 만드는 인덱스는 제외)

- `ix_참여_계정`: `CREATE INDEX "ix_참여_계정" ON public."참여" USING btree ("계정_번호")`
- `ix_참여_작품`: `CREATE INDEX "ix_참여_작품" ON public."참여" USING btree ("작품_번호")`

## 엔딩분기

| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |
|---|---|---|---|---|
| 1 | 번호 | integer | 불가 | IDENTITY (GENERATED ALWAYS) |
| 2 | 작품_번호 | integer | 불가 |  |
| 3 | 순서 | integer | 불가 |  |
| 4 | 이름 | text | 불가 |  |
| 5 | 조건 | jsonb | 불가 |  |
| 6 | 내용 | text | 불가 |  |

**제약조건**

| 종류 | 이름 | 정의 |
|---|---|---|
| PK | `pk_엔딩분기` | `PRIMARY KEY ("번호")` |
| UNIQUE | `uq_엔딩분기_작품_순서` | `UNIQUE ("작품_번호", "순서")` |
| FK | `fk_엔딩분기_작품` | `FOREIGN KEY ("작품_번호") REFERENCES "작품"("번호") ON DELETE CASCADE` |
| CHECK | `ck_엔딩분기_순서` | `CHECK (("순서" >= 1))` |

## 진행순서

| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |
|---|---|---|---|---|
| 1 | 번호 | integer | 불가 | IDENTITY (GENERATED ALWAYS) |
| 2 | 작품_번호 | integer | 불가 |  |
| 3 | 순서 | integer | 불가 |  |
| 4 | 이름 | text | 가능 |  |
| 5 | 진행시간 | integer | 불가 | 30 |

**제약조건**

| 종류 | 이름 | 정의 |
|---|---|---|
| PK | `pk_진행순서` | `PRIMARY KEY ("번호")` |
| UNIQUE | `uq_진행순서_작품_순서` | `UNIQUE ("작품_번호", "순서")` |
| FK | `fk_진행순서_작품` | `FOREIGN KEY ("작품_번호") REFERENCES "작품"("번호") ON DELETE CASCADE` |
| CHECK | `ck_진행순서_순서` | `CHECK (("순서" >= 1))` |
| CHECK | `ck_진행순서_진행시간` | `CHECK (("진행시간" >= 0))` |

## 공개

| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |
|---|---|---|---|---|
| 1 | 번호 | integer | 불가 | IDENTITY (GENERATED ALWAYS) |
| 2 | 작품_번호 | integer | 불가 |  |
| 3 | 진행_번호 | integer | 불가 |  |
| 4 | 획득_번호 | integer | 불가 |  |
| 5 | 대상_참여_번호 | integer | 가능 |  |
| 6 | 공개일시 | timestamp with time zone | 불가 | CURRENT_TIMESTAMP |
| 7 | 취소일시 | timestamp with time zone | 가능 |  |

**제약조건**

| 종류 | 이름 | 정의 |
|---|---|---|
| PK | `pk_공개` | `PRIMARY KEY ("번호")` |
| FK | `fk_공개_작품` | `FOREIGN KEY ("작품_번호") REFERENCES "작품"("번호") ON DELETE RESTRICT` |
| FK | `fk_공개_진행` | `FOREIGN KEY ("진행_번호") REFERENCES "진행"("번호") ON DELETE CASCADE` |
| FK | `fk_공개_참여` | `FOREIGN KEY ("대상_참여_번호") REFERENCES "참여"("번호") ON DELETE CASCADE` |
| FK | `fk_공개_획득` | `FOREIGN KEY ("획득_번호") REFERENCES "획득"("번호") ON DELETE CASCADE` |

**추가 인덱스** (PK/UNIQUE 제약이 만드는 인덱스는 제외)

- `ix_공개_작품`: `CREATE INDEX "ix_공개_작품" ON public."공개" USING btree ("작품_번호")`
- `ix_공개_진행`: `CREATE INDEX "ix_공개_진행" ON public."공개" USING btree ("진행_번호")`
- `ix_공개_참여`: `CREATE INDEX "ix_공개_참여" ON public."공개" USING btree ("대상_참여_번호")`
- `ix_공개_획득`: `CREATE INDEX "ix_공개_획득" ON public."공개" USING btree ("획득_번호")`

## 투표결과

| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |
|---|---|---|---|---|
| 1 | 번호 | integer | 불가 | IDENTITY (GENERATED ALWAYS) |
| 2 | 작품_번호 | integer | 불가 |  |
| 3 | 투표이름 | text | 불가 |  |
| 4 | 참여_번호 | integer | 불가 |  |
| 5 | 선택 | text | 불가 |  |

**제약조건**

| 종류 | 이름 | 정의 |
|---|---|---|
| PK | `pk_투표결과` | `PRIMARY KEY ("번호")` |
| UNIQUE | `uq_투표결과_투표_참여` | `UNIQUE ("작품_번호", "투표이름", "참여_번호")` |
| FK | `fk_투표결과_작품` | `FOREIGN KEY ("작품_번호") REFERENCES "작품"("번호") ON DELETE RESTRICT` |
| FK | `fk_투표결과_참여` | `FOREIGN KEY ("참여_번호") REFERENCES "참여"("번호") ON DELETE CASCADE` |

**추가 인덱스** (PK/UNIQUE 제약이 만드는 인덱스는 제외)

- `ix_투표결과_참여`: `CREATE INDEX "ix_투표결과_참여" ON public."투표결과" USING btree ("참여_번호")`

## 대화

| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |
|---|---|---|---|---|
| 1 | 번호 | integer | 불가 | IDENTITY (GENERATED ALWAYS) |
| 2 | 진행_번호 | integer | 불가 |  |
| 3 | 계정_번호 | integer | 불가 |  |
| 4 | 장소 | text | 불가 |  |
| 5 | 내용 | text | 불가 |  |
| 6 | 보낸일시 | timestamp with time zone | 불가 | CURRENT_TIMESTAMP |

**제약조건**

| 종류 | 이름 | 정의 |
|---|---|---|
| PK | `pk_대화` | `PRIMARY KEY ("번호")` |
| FK | `fk_대화_계정` | `FOREIGN KEY ("계정_번호") REFERENCES "계정"("번호") ON DELETE RESTRICT` |
| FK | `fk_대화_진행` | `FOREIGN KEY ("진행_번호") REFERENCES "진행"("번호") ON DELETE CASCADE` |
| CHECK | `ck_대화_내용` | `CHECK (((char_length("내용") >= 1) AND (char_length("내용") <= 500)))` |

**추가 인덱스** (PK/UNIQUE 제약이 만드는 인덱스는 제외)

- `ix_대화_계정`: `CREATE INDEX "ix_대화_계정" ON public."대화" USING btree ("계정_번호")`
- `ix_대화_진행`: `CREATE INDEX "ix_대화_진행" ON public."대화" USING btree ("진행_번호", "번호")`

## 대화수신

| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |
|---|---|---|---|---|
| 1 | 번호 | integer | 불가 | IDENTITY (GENERATED ALWAYS) |
| 2 | 대화_번호 | integer | 불가 |  |
| 3 | 계정_번호 | integer | 불가 |  |

**제약조건**

| 종류 | 이름 | 정의 |
|---|---|---|
| PK | `pk_대화수신` | `PRIMARY KEY ("번호")` |
| UNIQUE | `uq_대화수신_대화_계정` | `UNIQUE ("대화_번호", "계정_번호")` |
| FK | `fk_대화수신_계정` | `FOREIGN KEY ("계정_번호") REFERENCES "계정"("번호") ON DELETE RESTRICT` |
| FK | `fk_대화수신_대화` | `FOREIGN KEY ("대화_번호") REFERENCES "대화"("번호") ON DELETE CASCADE` |

**추가 인덱스** (PK/UNIQUE 제약이 만드는 인덱스는 제외)

- `ix_대화수신_계정`: `CREATE INDEX "ix_대화수신_계정" ON public."대화수신" USING btree ("계정_번호", "대화_번호")`

