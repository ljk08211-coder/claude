---
name: auction-bid
description: 부동산 경매(아파트) 물건의 적정 입찰가를 추천한다. 사건번호와 법원 서류(감정평가서·매각물건명세서·현황조사서·등기부 PDF나 붙여넣은 텍스트)를 받아 실거래가로 시세를 추정하고, 권리분석(말소기준·대항력·인수금액·위험 키워드), 취득세·양도세·대출이자·수리비·명도비를 계산해 목표 세후 순이익을 맞추는 수익 상한가를 역산한 뒤, 낙찰확률을 곁들여 보수·추천·공격 3안과 HTML 리포트를 만든다. 사용자가 "2026타경12345 분석해줘", "이 경매 물건 얼마 써야 해", "입찰가 추천", "적정 입찰가", "경매 권리분석", "낙찰가 예상", "낙찰 결과 기록해줘" 등을 요청하면 이 스킬을 사용한다.
---

# 경매 적정 입찰가 추천

사건 하나를 넣으면 **시세 → 권리·비용 → 수익 상한가 → 낙찰확률 → 입찰가 3안**이 나온다.
기획 배경과 로직은 저장소의 `auction-bid/PLAN.md` 를 참고한다.

- 스크립트: `python3 <이 스킬 폴더>/scripts/auction.py`
- 사건 폴더: `auction-cases/<사건번호>/` (case.json · comps.json · report.html · result.json)
- 낙찰결과 누적: `auction-cases/_results.csv` (쌓일수록 낙찰확률이 정확해진다)
- 개인 설정: `auction-cases/config.toml` 을 만들면 스킬 기본 `config.toml` 위에 덮어쓴다. 바꾸고 싶은 항목만 쓰면 된다.

## 1단계: 확인

```bash
python3 <스킬>/scripts/auction.py check
```

API 키는 환경변수 `DATA_GO_KR_KEY` 또는 `auction-cases/config.toml` 에 둔다 (이 폴더는 git 에 올라가지 않는다).

```toml
[api]
data_go_kr_key = "발급받은 일반 인증키"
```

`DATA_GO_KR_KEY: 없음` 이면 실거래가 자동 수집이 안 된다. 사용자에게 알려주고 셋 중 하나로 간다.
- 공공데이터포털(data.go.kr)에서 **국토교통부_아파트 매매 실거래가 상세 자료**, **국토교통부_아파트 전월세 실거래가 자료** 활용신청 → 발급된 키를 `DATA_GO_KR_KEY` 환경변수에 설정 (무료, 승인 즉시~1시간)
- rt.molit.go.kr 에서 해당 시군구 아파트 매매 CSV 를 받아 `--csv` 로 넣기
- KB시세·호가를 받아 `overrides.market_value` 로 직접 입력

## 2단계: 사건 만들기

```bash
python3 <스킬>/scripts/auction.py init 2026타경12345
```

`auction-cases/2026타경12345/case.json` 이 생긴다. 사용자가 준 서류를 직접 읽고(PDF 는 Read 로) 아래 표대로 채운다.
**서류에 없는 값은 지어내지 않는다.** 모르면 비워두고 리포트 설명 때 "가정"이라고 말한다.

| 필드 | 어디서 | 메모 |
|---|---|---|
| `court`, `item_no` | 사건정보 | |
| `property.region` | 주소 | "부산 해운대구"처럼. 같은 구 이름이 여러 도시에 있으면 도시를 붙인다. `lawd_cd`(5자리)를 알면 직접 넣어도 된다 |
| `property.dong`, `apt_name`, `apt_seq` | 주소·감정평가서 → 3단계 후 `apts` 로 확정 | `dong` 은 법정동(예: 좌동, 우동). 실거래 수집 뒤 `apts` 로 국토부 표기 단지명과 `apt_seq`(단지 고유번호)를 확인해서 넣는다 |
| `property.exclusive_area` | 감정평가서 | **전용면적** ㎡ |
| `property.floor`, `top_floor`, `build_year` | 감정평가서·건축물대장 | 준공 10년 이내면 수리비 대신 도배·청소비(150만)만 잡힌다 |
| `property.official_price` | 감정평가서·부동산공시가격알리미 | 공동주택 공시가격. 취득세(공시가격 × 1%) 계산용. 없으면 시세×69% 로 추정 |
| `auction.appraisal`, `min_price`, `failed_count`, `sale_date` | 사건정보 | 원 단위 정수 |
| `auction.resale`, `share_sale`, `special_conditions` | 매각물건명세서 | 재매각이면 `resale` true. 일부 지분만 파는 경우만 `share_sale` true (공유자 "지분 전부"를 함께 팔면 건물 전체라 false). 특별매각조건·인수 조건 원문 |
| `auction.reduction_rate` | 법원 | 유찰 저감률. 모르면 null(기본 20%) |
| `occupancy.type` | 현황조사서 | `owner`(소유자·채무자) / `tenant` / `vacant` / `unknown` |
| `rights[]` | 등기부 갑구·을구 | `{"type":"근저당","date":"YYYY-MM-DD","amount":원,"holder":"○○은행"}`. 근저당·저당·압류·가압류·가처분·가등기·전세권·임차권·경매개시결정 모두 |
| `tenants[]` | 매각물건명세서 | `{"name","move_in","fixed_date","deposit","monthly_rent","claimed_dividend":true/false}` |
| `flags[]` | 명세서·현황조사서·감정평가서 | 유치권, 법정지상권, 대지권미등기, 토지별도등기, 위반건축물, 폐문부재, 관리비 체납 같은 문구를 원문 그대로. 위험 키워드는 `flags` 와 `special_conditions` 에서만 찾는다 (`notes` 는 설명용이라 검사 안 함) |

## 3단계: 실거래 수집

```bash
python3 <스킬>/scripts/auction.py comps auction-cases/2026타경12345/case.json [--csv 다운받은.csv]
```

- `API_ERROR` → 키 승인 대기 중이거나 오류. CSV 나 직접 입력으로 계속 간다.
- 한 구 12개월이면 매매 수천 건이라 1~2분 걸린다. HTTPS 가 막힌 네트워크면 자동으로 HTTP 로 다시 요청한다.

수집이 끝나면 단지를 확정한다. 같은 이름 단지가 여러 개면(예: 현대, 현대(1051-2)) 주소의 법정동·준공연도·전용면적으로 고른다.

```bash
python3 <스킬>/scripts/auction.py apts auction-cases/2026타경12345/case.json 센텀대림
```

출력된 단지명 그대로 `apt_name`, 그리고 `apt_seq`, `dong` 을 case.json 에 넣는다.
- `NO_DATA_SOURCE` → 1단계 안내로 돌아간다.

## 4단계: 현장조사 정보 (있으면)

사용자에게 물어보고 `site_survey` 를 채운다. 없어도 분석은 돌아가지만 보수적 가정(컨디션 C등급)이 들어간다.
- `condition_grade`: A(손볼 것 없음) / B(도배·장판 + 부분 수리) / C(욕실·주방 포함) / D(올수리·섀시). 수리 견적이 있으면 `repair_cost_override`
- `unpaid_mgmt_fee`: 관리사무소에서 확인한 체납 관리비 총액
- `kb_price`, `asking_prices`: KB 일반가, 중개사무소 호가들
- 월세 시세를 중개사에게 들었다면 `overrides.monthly_rent`, `overrides.rent_deposit`

## 5단계: 분석

```bash
python3 <스킬>/scripts/auction.py analyze auction-cases/2026타경12345/case.json
```

- `NO_MARKET_VALUE` → 비교 사례가 없다. 단지명·법정동 표기를 실거래 데이터(comps.json)와 맞춰보고, 그래도 없으면 KB·호가를 받아 다시 돌린다.
- 출력된 요약 마크다운을 그대로 보여주고 리포트 경로(`report.html`)를 알려준다. 사용자가 보기 편하게 SendUserFile 로 리포트를 보낼 수 있으면 보낸다.
- 설명할 때 꼭 짚을 것:
  1. **판정** (입찰 추천 / 검토 / 다음 회차 대기 / 패스)과 이유
  2. 추천가와 그 낙찰확률·세후 순이익, 그리고 **상한가는 넘기지 말 것**
  3. 보유기간별 차이 (무주택자는 2년 보유 비과세가 핵심. 조정대상지역은 2년 거주도 필요)
  4. 🔴·🟡 플래그, 그리고 "가정"으로 넣은 값들 (컨디션, 시세 신뢰도, 낙찰확률이 기본 분포인지)
- 이 결과는 판단 보조용이다. 🔴 플래그나 대항력 있는 임차인이 있으면 법무사 확인을 권한다.

목표 수익·보유기간·세율·대출 조건을 바꾸고 싶다고 하면 `auction-cases/config.toml` 에 해당 항목만 써서 다시 analyze 한다. 예:

```toml
[strategy]
target_net_profit = 15_000_000
```

## 6단계: 결과 기록 (낙찰확률 학습)

매각기일이 지나면 결과를 기록하게 한다.

```bash
# 내가 분석한 사건
python3 <스킬>/scripts/auction.py record auction-cases/2026타경12345/case.json --winning-bid 205000000 --bidders 7 [--my-bid 원]
# 다른 사람 사건(같은 지역 낙찰 사례) — 법원경매정보 매각결과나 유료 사이트에서 본 것
python3 <스킬>/scripts/auction.py record-comp --lawd "부산 해운대구" --market-value 300000000 --winning-bid 262000000 --sale-date 2026-09-30 [--bidders 9]
```

같은 시군구·같은 유형 사례가 최근 6개월 8건 이상 쌓이면 기본 분포 대신 실제 분포로 낙찰확률을 계산한다.
사용자가 지역 낙찰 결과 여러 건을 붙여넣으면 각각 record-comp 로 넣는다. 이때 시세는 그 단지 실거래로 확인한 값을 쓴다.

## 테스트

```bash
python3 -m unittest discover -s <스킬>/scripts/tests
```
