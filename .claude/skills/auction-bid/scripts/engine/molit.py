"""국토교통부 아파트 실거래가(매매·전월세) — 공공데이터포털 API 와 CSV 파일 읽기.

API 키: 공공데이터포털(data.go.kr)에서 '국토교통부_아파트 매매 실거래가 상세 자료',
'국토교통부_아파트 전월세 실거래가 자료' 활용신청 → 환경변수 DATA_GO_KR_KEY 에 넣는다.
API 가 막히면 rt.molit.go.kr 에서 받은 CSV 를 load_csv 로 읽는다.
"""
import csv
import datetime as dt
import io
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

TRADE_URLS = [
    "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev",
    "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade",
]
RENT_URLS = ["https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent"]


_HTTP_ONLY = False


class ApiError(RuntimeError):
    pass


def _won(text):
    """'  82,500' (만원) → 825000000 (원)."""
    text = re.sub(r"[^\d]", "", str(text or ""))
    return int(text) * 10_000 if text else 0


def _num(text, cast=float, default=None):
    try:
        return cast(str(text).strip())
    except (TypeError, ValueError):
        return default


def exact_name(name):
    """괄호까지 살린 단지명 (현대 ≠ 현대(1051-2))."""
    return re.sub(r"\s|아파트", "", name or "").lower()


def norm_name(name):
    name = re.sub(r"\(.*?\)", "", name or "")
    return re.sub(r"\s|아파트", "", name).lower()


def _get(full_url):
    with urllib.request.urlopen(full_url, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _request(url, params, key):
    # 공공데이터포털은 인코딩 키/디코딩 키를 둘 다 준다. '%' 가 있으면 이미 인코딩된 키.
    enc_key = key if "%" in key else urllib.parse.quote(key, safe="")
    query = f"serviceKey={enc_key}&" + urllib.parse.urlencode(params)
    global _HTTP_ONLY
    http_url = "http://" + url.split("://", 1)[1]
    if _HTTP_ONLY:
        body = _get(f"{http_url}?{query}")
    else:
        try:
            body = _get(f"{url}?{query}")
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            # 일부 네트워크에서 apis.data.go.kr HTTPS 연결이 끊긴다. 이후로는 HTTP 로만 요청.
            _HTTP_ONLY = True
            body = _get(f"{http_url}?{query}")
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        raise ApiError(f"응답이 XML 이 아님: {body[:200]}")
    code = (root.findtext(".//resultCode") or "").strip()
    if code not in ("00", "000"):
        msg = root.findtext(".//resultMsg") or root.findtext(".//returnAuthMsg") or body[:200]
        raise ApiError(f"API 오류 {code}: {msg.strip()}")
    items = [{c.tag: (c.text or "").strip() for c in it} for it in root.iter("item")]
    total = _num(root.findtext(".//totalCount"), int, len(items))
    return items, total


def _fetch_month(urls, lawd, ym, key):
    last = None
    for url in urls:
        try:
            out, page = [], 1
            while True:
                items, total = _request(url, {"LAWD_CD": lawd, "DEAL_YMD": ym, "pageNo": page, "numOfRows": 1000}, key)
                out += items
                if len(out) >= total or not items:
                    return out
                page += 1
        except ApiError as e:
            last = e
    raise last


def months_back(n, today=None):
    today = today or dt.date.today()
    y, m = today.year, today.month
    out = []
    for _ in range(n):
        out.append(f"{y}{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out


def parse_trade(it):
    if it.get("cdealType", "").strip() in ("O", "Y"):  # 해제된 거래
        return None
    y, m, d = (_num(it.get(k), int) for k in ("dealYear", "dealMonth", "dealDay"))
    price = _won(it.get("dealAmount"))
    area = _num(it.get("excluUseAr"))
    if not (y and m and price and area):
        return None
    return {
        "date": f"{y}-{m:02d}-{(d or 1):02d}",
        "apt_name": it.get("aptNm", ""),
        "apt_seq": it.get("aptSeq", ""),
        "dong": it.get("umdNm", ""),
        "jibun": it.get("jibun", ""),
        "area": area,
        "floor": _num(it.get("floor"), int),
        "build_year": _num(it.get("buildYear"), int),
        "price": price,
        "dealing": it.get("dealingGbn", ""),
    }


def parse_rent(it):
    y, m, d = (_num(it.get(k), int) for k in ("dealYear", "dealMonth", "dealDay"))
    area = _num(it.get("excluUseAr"))
    if not (y and m and area):
        return None
    return {
        "date": f"{y}-{m:02d}-{(d or 1):02d}",
        "apt_name": it.get("aptNm", ""),
        "apt_seq": it.get("aptSeq", ""),
        "dong": it.get("umdNm", ""),
        "area": area,
        "floor": _num(it.get("floor"), int),
        "build_year": _num(it.get("buildYear"), int),
        "deposit": _won(it.get("deposit")),
        "monthly_rent": _won(it.get("monthlyRent")),
    }


def fetch(lawd, months, key, kind="trade", log=print):
    urls, parser = (TRADE_URLS, parse_trade) if kind == "trade" else (RENT_URLS, parse_rent)
    rows = []
    for ym in months_back(months):
        items = _fetch_month(urls, lawd, ym, key)
        parsed = [r for r in map(parser, items) if r]
        log(f"  {kind} {ym}: {len(parsed)}건")
        rows += parsed
    return rows


def load_csv(path):
    """rt.molit.go.kr 에서 내려받은 아파트 매매 CSV(앞쪽 안내문 포함)를 읽는다."""
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "cp949"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if "단지명" in line)
    rows = []
    for r in csv.DictReader(io.StringIO("\n".join(lines[start:]))):
        ym = re.sub(r"\D", "", r.get("계약년월", ""))
        if len(ym) != 6 or (r.get("해제사유발생일") or "-").strip() not in ("", "-"):
            continue
        area = _num(r.get("전용면적(㎡)"))
        price = _won(r.get("거래금액(만원)"))
        if not (area and price):
            continue
        sgg = (r.get("시군구") or "").split()
        rows.append({
            "date": f"{ym[:4]}-{ym[4:]}-{int(_num(r.get('계약일'), int, 1)):02d}",
            "apt_name": r.get("단지명", ""),
            "dong": sgg[-1] if sgg else "",
            "jibun": r.get("번지", ""),
            "area": area,
            "floor": _num(r.get("층"), int),
            "build_year": _num(r.get("건축년도"), int),
            "price": price,
            "dealing": r.get("거래유형", ""),
        })
    return rows
