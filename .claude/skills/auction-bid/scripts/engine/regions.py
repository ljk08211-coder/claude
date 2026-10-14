"""시군구 이름 ↔ 법정동 시군구코드(LAWD_CD 5자리).

부산·서울은 전부, 경기는 주요 시만 넣었다. 목록에 없으면 5자리 코드를 직접 쓰면 된다.
(경기 일부 시는 행정구 개편이 잦으니 결과가 비면 코드를 확인할 것)
"""

BUSAN = {
    "중구": "26110", "서구": "26140", "동구": "26170", "영도구": "26200", "부산진구": "26230",
    "동래구": "26260", "남구": "26290", "북구": "26320", "해운대구": "26350", "사하구": "26380",
    "금정구": "26410", "강서구": "26440", "연제구": "26470", "수영구": "26500", "사상구": "26530",
    "기장군": "26710",
}

SEOUL = {
    "종로구": "11110", "중구": "11140", "용산구": "11170", "성동구": "11200", "광진구": "11215",
    "동대문구": "11230", "중랑구": "11260", "성북구": "11290", "강북구": "11305", "도봉구": "11320",
    "노원구": "11350", "은평구": "11380", "서대문구": "11410", "마포구": "11440", "양천구": "11470",
    "강서구": "11500", "구로구": "11530", "금천구": "11545", "영등포구": "11560", "동작구": "11590",
    "관악구": "11620", "서초구": "11650", "강남구": "11680", "송파구": "11710", "강동구": "11740",
}

GYEONGGI = {
    "수원시 장안구": "41111", "수원시 권선구": "41113", "수원시 팔달구": "41115", "수원시 영통구": "41117",
    "성남시 수정구": "41131", "성남시 중원구": "41133", "성남시 분당구": "41135", "의정부시": "41150",
    "안양시 만안구": "41171", "안양시 동안구": "41173", "광명시": "41210", "평택시": "41220",
    "안산시 상록구": "41271", "안산시 단원구": "41273", "고양시 덕양구": "41281",
    "고양시 일산동구": "41285", "고양시 일산서구": "41287", "과천시": "41290", "구리시": "41310",
    "남양주시": "41360", "오산시": "41370", "시흥시": "41390", "군포시": "41410", "의왕시": "41430",
    "하남시": "41450", "용인시 처인구": "41461", "용인시 기흥구": "41463", "용인시 수지구": "41465",
    "파주시": "41480", "이천시": "41500", "안성시": "41550", "김포시": "41570", "광주시": "41610",
    "양주시": "41630", "포천시": "41650",
}

CITIES = {
    "부산": BUSAN, "부산시": BUSAN, "부산광역시": BUSAN,
    "서울": SEOUL, "서울시": SEOUL, "서울특별시": SEOUL,
    "경기": GYEONGGI, "경기도": GYEONGGI,
}

CITY_NAME = {"26": "부산광역시", "11": "서울특별시", "41": "경기도"}


def name_of(code):
    for table in (BUSAN, SEOUL, GYEONGGI):
        for name, c in table.items():
            if c == code:
                return f"{CITY_NAME.get(code[:2], '')} {name}".strip()
    return code


def resolve(text):
    """'해운대구', '부산 해운대구', '서울 강서구', '26350' → '26350'.

    여러 도시에 같은 이름이 있으면(중구, 강서구 등) ValueError 로 후보를 알려준다.
    """
    text = (text or "").strip()
    if text.isdigit() and len(text) == 5:
        return text
    parts = text.split()
    if parts and parts[0] in CITIES:
        table = CITIES[parts[0]]
        rest = " ".join(parts[1:])
        if rest in table:
            return table[rest]
        hits = [c for n, c in table.items() if n.replace(" ", "") == rest.replace(" ", "") or n.endswith(rest)]
        if len(hits) == 1:
            return hits[0]
        raise ValueError(f"'{text}' 를 찾지 못했다. 5자리 시군구코드를 직접 넣어줘.")
    hits = []
    for table in (BUSAN, SEOUL, GYEONGGI):
        for n, c in table.items():
            if n == text or n.replace(" ", "") == text.replace(" ", "") or n.endswith(" " + text):
                hits.append(c)
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ValueError(f"'{text}' 를 찾지 못했다. '부산 해운대구'처럼 쓰거나 5자리 코드를 넣어줘.")
    raise ValueError(f"'{text}' 가 여러 곳에 있다: {', '.join(name_of(c) for c in hits)}. 도시 이름을 붙여줘.")


def is_regulated(code, cfg):
    reg = cfg["regions"]
    return code in reg.get("regulated_codes", []) or any(code.startswith(p) for p in reg.get("regulated_prefixes", []))
