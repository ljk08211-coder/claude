---
name: shorts-finder
description: 유튜브 쇼츠와 인스타 릴스에서 주제(테마)별로 조회수가 잘 나온 영상을 찾아 떡상 지수(조회수 ÷ 구독자/팔로워) 순으로 정리한다. 유튜브는 YouTube Data API, 인스타는 Apify(apify/instagram-scraper)로 수집한다. 사용자가 "터진 쇼츠 찾아줘", "잘 나온 릴스 찾아줘", "벤치마킹할 영상 뽑아줘", "주류/칵테일/바 창업 숏폼 분석", "키워드별 조회수 좋은 영상", "숏폼 트렌드 리포트" 등을 요청하면 이 스킬을 사용한다.
---

# 숏폼 벤치마킹: 주제별 터진 영상 찾기

키워드(유튜브)와 해시태그(인스타)를 테마로 묶어 수집하고, 테마별 상위 영상 리포트를 만든다.

## 1단계: 연결 확인

```bash
python3 <이 스킬 폴더>/scripts/shorts_finder.py check
```

- 유튜브 키: 환경 Network secret(`www.googleapis.com`에 `X-Goog-Api-Key` 헤더) 또는 환경 변수 `YOUTUBE_API_KEY`
- Apify 토큰: 환경 Network secret(`api.apify.com`에 `Authorization: Bearer ...`) 또는 환경 변수 `APIFY_TOKEN`
- 실패하면 어느 쪽이 안 되는지 알려주고, 키를 채팅에 붙여넣지 말고 환경 설정에 넣도록 안내한다.

## 2단계: 키워드 확인

`<이 스킬 폴더>/keywords.json`이 기본 설정이다. 사용자가 다른 주제를 원하면 이 파일을 복사해서 `themes`만 바꾼 설정으로 실행한다.

| 항목 | 뜻 |
|---|---|
| `days` | 유튜브 검색 기간(일) |
| `instagram_days` | 인스타 기간(일). 해시태그 페이지는 인기 글 위주라 최근 글이 적으므로 길게 둔다 |
| `youtube_per_keyword` / `instagram_per_hashtag` | 키워드·해시태그당 수집 개수 |
| `min_views` | 리포트에 넣을 최소 조회수(기본 1만). 소규모 채널의 착시를 막는다 |
| `relevance_words` | 제목·캡션에 하나라도 있어야 주제 관련으로 본다 |
| `themes` | 테마별 `youtube` 검색어, `instagram` 해시태그(# 없이) |

## 3단계: 실행 (비용이 드는 부분은 먼저 알린다)

```bash
python3 <이 스킬 폴더>/scripts/shorts_finder.py run --config <설정.json> --out shorts-finder
```

- 유튜브: 무료. 검색어 1개에 하루 할당량 10,000 중 100을 쓴다.
- 인스타: Apify 유료. 릴스 1개와 계정 1개 조회가 각각 약 $0.0027이다. 기본 설정(해시태그 9개)으로 1회에 약 $0.6~0.8이 든다. 해시태그를 크게 늘릴 때는 예상 비용을 먼저 말하고 동의를 받는다.
- 한쪽만 돌리려면 `--skip-youtube` 또는 `--skip-instagram`을 붙인다.
- 이미 모은 데이터로 리포트만 다시 만들 때는 비용이 들지 않는다.
  `python3 <이 스킬 폴더>/scripts/shorts_finder.py report --config <설정.json> --data shorts-finder/results_YYYYMMDD.json`

결과물은 `shorts-finder/`에 생긴다.

| 파일 | 내용 |
|---|---|
| `report_YYYYMMDD.md` | 플랫폼·테마별 상위 영상 표 |
| `results_YYYYMMDD.csv` | 전체 영상(엑셀용, 주제 무관·저조회 포함) |
| `results_YYYYMMDD.json` | 위와 같은 데이터. `report` 명령의 입력 |

## 4단계: 정리해서 전달

리포트를 그대로 붙이지 말고, 표를 읽고 다음을 정리해 준다.

1. 테마별로 **반복되는 포맷이나 후킹 패턴** (예: "트레이더스 이번 달 위스키 TOP" 같은 시리즈형)
2. **떡상 지수가 높은 소규모 채널.** 구독자 대비 조회수가 높아 따라 하기 좋은 사례다
3. 주제와 무관한데 섞인 영상(연예 뉴스, 협찬 광고 등)은 빼고 말한다. 인스타 해시태그 결과에 특히 많다
4. 더 깊게 볼 영상 3~5개를 추천하고, 유튜브 영상이면 `youtube-digest` 스킬로 자막과 장면을 분석할지 묻는다

## 알아둘 점

- 떡상 지수는 구독자가 숨겨진 채널이면 비어 있다(`-`).
- 인스타 해시태그 수집은 인스타가 보여주는 인기 글만 가져온다. 최근성이나 주제 정확도는 유튜브보다 낮다. 특정 경쟁 계정을 추적하려면 해시태그 대신 계정 목록으로 수집하는 방식을 제안한다.
