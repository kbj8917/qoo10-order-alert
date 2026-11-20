#!/usr/bin/env python3
"""Qoo10 Japan 상품 등록 (폰 앱 → GitHub Actions에서 실행)

  python qoo10_upload.py --job jobs/<id>.json   # 상품 등록
  python qoo10_upload.py --sync                  # 카테고리/배송비 목록 → docs/data/

작업 파일(jobs/<id>.json)의 "type":
  register (기본)  새 상품 등록
  scan             판매중 상품 + 기간 내 판매수량 조회 → results/<id>.json
  relist           페이지 갈이: 기존 상품 정보 복사 → 수정 → 기존 판매중지 → 새로 등록

표준 라이브러리만 사용. 인증 정보는 qoo10_alert 와 동일한 환경변수/Secrets 사용:
  QOO10_SAK  또는  QOO10_API_KEY + QOO10_USER_ID + QOO10_PASSWORD
"""
import argparse
import json
import os
import sys
import traceback
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API_BASE = "https://api.qoo10.jp/GMKT.INC.Front.QAPIService/ebayjapan.qapi"
JST = timezone(timedelta(hours=9))


def env(name, default=""):
    return os.environ.get(name, default).strip()


def load_actions_secrets():
    raw = os.environ.get("S")
    if raw:
        for k, v in json.loads(raw).items():
            if isinstance(v, str):
                os.environ.setdefault(k, v)


def load_dotenv(path=".env"):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def qapi(method, key, version="1.0", **params):
    """POST 방식 호출 (상세설명처럼 긴 값도 전송 가능)."""
    body = {"returnType": "json", "key": key, "v": version}
    body.update({k: str(v) for k, v in params.items() if v not in (None, "")})
    req = urllib.request.Request(
        f"{API_BASE}/{method}",
        data=urllib.parse.urlencode(body).encode(),
        headers={
            "GiosisCertificationKey": key,
            "QAPIVersion": version,
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "qoo10-uploader/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        text = r.read().decode("utf-8-sig")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise RuntimeError(f"Qoo10 응답을 해석할 수 없습니다: {text[:300]}")
    code = str(data.get("ResultCode", data.get("resultCode", "0")))
    if code not in ("0", "-10001"):
        raise RuntimeError(f"Qoo10 API 오류 [{method}] code={code} msg={data.get('ResultMsg') or data.get('resultMsg')}")
    return data


def get_seller_key():
    sak = env("QOO10_SAK")
    if sak:
        return sak
    api_key, uid, pwd = env("QOO10_API_KEY"), env("QOO10_USER_ID"), env("QOO10_PASSWORD")
    if not (api_key and uid and pwd):
        raise RuntimeError("Secrets 설정 오류: QOO10_SAK 또는 (QOO10_API_KEY + QOO10_USER_ID + QOO10_PASSWORD)가 필요합니다.")
    data = qapi("CertificationAPI.CreateCertificationKey", api_key, user_id=uid, pwd=pwd)
    sak = data.get("ResultObject")
    if not sak or not isinstance(sak, str):
        raise RuntimeError(f"판매자 인증키 발급 실패: {data}")
    return sak


def field(o, *names, default=""):
    """응답 필드명 대소문자/표기 차이를 흡수."""
    if not isinstance(o, dict):
        return default
    low = {k.lower(): v for k, v in o.items()}
    for n in names:
        v = low.get(n.lower())
        if v not in (None, ""):
            return v
    return default


def as_list(obj):
    """ResultObject 가 list / {Items:[...]} / dict 단일 등 여러 형태로 오는 것을 리스트로."""
    if obj is None:
        return []
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, list) and k.lower() in ("items", "item", "itemlist", "goods", "list", "data"):
                return v
        return [obj]
    return []


# ------------------------------------------------------------------ 상품 등록
def build_description(job):
    """텍스트 설명 + 상세 이미지들을 HTML로 조합."""
    parts = []
    desc = (job.get("description") or "").strip()
    if desc:
        if "<" in desc and ">" in desc:
            parts.append(desc)  # 이미 HTML
        else:
            esc = desc.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            parts.append("<p>" + esc.replace("\n", "<br>") + "</p>")
    for url in job.get("detail_images") or []:
        parts.append(f'<p><img src="{url}" style="max-width:100%"></p>')
    return "\n".join(parts) or "<p>-</p>"


def register(job, sak):
    images = job.get("images") or []
    if not images:
        raise RuntimeError("대표 이미지가 없습니다.")
    params = {
        "SecondSubCat": job.get("category"),
        "BrandNo": job.get("brand_no"),
        "ItemTitle": job.get("title"),
        "PromotionName": job.get("promotion"),
        "SellerCode": job.get("seller_code"),
        "IndustrialCodeType": "J" if job.get("jan") else None,
        "IndustrialCode": job.get("jan"),
        "ProductionPlaceType": job.get("origin_type", "2"),  # 1:국내(일본) 2:해외 3:기타
        "ProductionPlace": job.get("origin", "Korea"),
        "Weight": job.get("weight"),
        "RetailPrice": job.get("retail_price") or None,
        "ItemPrice": job.get("price"),
        "ItemQty": job.get("qty"),
        "ExpireDate": job.get("expire_date", "2099-12-31"),
        "ShippingNo": job.get("shipping_no"),
        "AvailableDateType": job.get("available_type", "0"),
        "AvailableDateValue": job.get("available_value", "3"),
        "AdultYN": job.get("adult", "N"),
        "TaxRate": job.get("tax_rate", "S"),
        "Keyword": job.get("keyword"),
        "StandardImage": images[0],
        "ItemDescription": build_description(job),
    }
    params.update(job.get("extra") or {})  # 앱의 '추가 파라미터(JSON)'로 덮어쓰기 가능
    missing = [k for k in ("SecondSubCat", "ItemTitle", "SellerCode", "ItemPrice", "ItemQty", "ShippingNo") if not params.get(k)]
    if missing:
        raise RuntimeError("필수 항목 누락: " + ", ".join(missing))

    method = job.get("method", "ItemsBasic.SetNewGoods")
    data = qapi(method, sak, job.get("api_version", "1.1"), **params)
    obj = data.get("ResultObject") or {}
    if isinstance(obj, list):
        obj = obj[0] if obj else {}
    gd_no = str(obj.get("GdNo") or obj.get("ItemCode") or obj.get("itemCode") or "") if isinstance(obj, dict) else str(obj)
    result = {"item_code": gd_no, "raw": data, "warnings": []}

    # 추가 이미지 (대표 이미지 외)
    extra_imgs = images[1:]
    if extra_imgs and gd_no:
        mp = {"ItemCode": gd_no, "SellerCode": params["SellerCode"]}
        for i, u in enumerate(extra_imgs[:50], 1):
            mp[f"EnlargedImage{i}"] = u
        try:
            qapi("ItemsContents.EditGoodsMultiImage", sak, **mp)
        except Exception as e:
            result["warnings"].append(f"추가 이미지 등록 실패: {e}")
    return result


# ------------------------------------------------------------------ 스캔 (판매 부진 상품 찾기)
def list_items(sak, status="S2"):
    """판매중(S2) 상품 전체 목록."""
    items, page = [], 1
    while page <= 200:
        d = qapi("ItemsLookup.GetAllGoodsInfo", sak, ItemStatus=status, Page=page)
        obj = d.get("ResultObject")
        batch = as_list(obj)
        if not batch:
            break
        for it in batch:
            code = str(field(it, "ItemCode", "GdNo", "itemNo"))
            if not code:
                continue
            items.append({
                "code": code,
                "seller_code": field(it, "SellerCode", "SellerItemCode"),
                "title": field(it, "ItemTitle", "ItemName", "Title"),
                "price": field(it, "ItemPrice", "SellPrice", "Price"),
                "qty": field(it, "ItemQty", "Qty", "StockQty"),
                "image": field(it, "ImageUrl", "StandardImage", "ItemImage"),
                "reg_date": str(field(it, "RegDate", "RegistDate", "CreateDate", "StartDate"))[:10],
                "status": field(it, "ItemStatus", "Status"),
            })
        total_pages = int(field(obj, "TotalPages", "TotalPage", default=0) or 0) if isinstance(obj, dict) else 0
        if (total_pages and page >= total_pages) or (not total_pages and len(batch) < 100):
            break
        page += 1
    return items


def sales_by_item(sak, days):
    """최근 days일 주문을 7일 단위로 나눠 조회 → {상품코드: 판매수량}."""
    sold, seen = {}, set()
    end = datetime.now(JST)
    start = end - timedelta(days=days)
    cur = start
    while cur < end:
        nxt = min(cur + timedelta(days=7), end)
        for st in ("1", "2", "3", "4", "5"):
            d = qapi("ShippingBasic.GetShippingInfo_v2", sak, ShippingStat=st,
                     search_Sdate=cur.strftime("%Y%m%d"), search_Edate=nxt.strftime("%Y%m%d"), search_condition="1")
            for o in as_list(d.get("ResultObject")):
                key = (str(field(o, "orderNo", "OrderNo")), str(field(o, "packNo", "PackNo")))
                if key in seen:
                    continue
                seen.add(key)
                code = str(field(o, "itemCode", "ItemCode", "GdNo"))
                if code:
                    sold[code] = sold.get(code, 0) + int(float(field(o, "orderQty", "OrderQty", default=1) or 1))
        cur = nxt + timedelta(days=1)
    return sold


def scan(job, sak):
    days = int(job.get("days") or 30)
    items = list_items(sak)
    sold = sales_by_item(sak, days)
    for it in items:
        it["sold"] = sold.get(it["code"], 0)
    return {"days": days, "items": items, "item_count": len(items), "sold_items": len(sold)}


# ------------------------------------------------------------------ 페이지 갈이
def item_detail(sak, code, seller_code=""):
    d = qapi("ItemsLookup.GetItemDetailInfo", sak, ItemCode=code, SellerCode=seller_code or None)
    lst = as_list(d.get("ResultObject"))
    if not lst:
        raise RuntimeError(f"상품 상세 조회 실패: {code}")
    return lst[0]


def set_status(sak, code, seller_code, status):
    """status: 1=取引待機(판매중지) 2=取引可能(판매중) 3=取引廃止(거래폐지)"""
    qapi("ItemsBasic.EditGoodsStatus", sak, ItemCode=code, SellerCode=seller_code or None, Status=status)


def relist_one(sak, it, dry_run, old_action):
    code = str(it["code"])
    det = item_detail(sak, code, it.get("seller_code"))
    old_seller = it.get("seller_code") or field(det, "SellerCode")
    out = {"old_code": code, "warnings": []}

    # 옵션 상품은 옵션이 복사되지 않으므로 기본적으로 제외
    try:
        od = qapi("ItemsLookup.GetGoodsOptionInfo", sak, ItemCode=code)
        if as_list(od.get("ResultObject")) and not it.get("allow_options"):
            raise RuntimeError("옵션이 있는 상품이라 자동 갈이에서 제외했어요 (옵션은 복사되지 않음)")
    except RuntimeError as e:
        if "옵션이 있는" in str(e):
            raise
        out["warnings"].append(f"옵션 확인 불가: {e}")

    new_seller = it.get("new_seller_code") or f"{old_seller or code}-R{datetime.now(JST).strftime('%m%d')}"
    job = {
        "category": field(det, "SecondSubCat", "SecondSubCatCd", "CategoryCode", "SubCatCd", "CatCd"),
        "brand_no": field(det, "BrandNo"),
        "title": it.get("new_title") or field(det, "ItemTitle"),
        "promotion": field(det, "PromotionName"),
        "seller_code": new_seller,
        "jan": field(det, "IndustrialCode", "JanCode"),
        "origin_type": field(det, "ProductionPlaceType", default="2"),
        "origin": field(det, "ProductionPlace", default="Korea"),
        "weight": field(det, "Weight"),
        "retail_price": field(det, "RetailPrice") or None,
        "price": it.get("new_price") or field(det, "ItemPrice", "SellPrice"),
        "qty": field(det, "ItemQty", "Qty", default=it.get("qty") or 100),
        "expire_date": str(field(det, "ExpireDate", default="2099-12-31"))[:10],
        "shipping_no": field(det, "ShippingNo", "ShippingGroupNo"),
        "available_type": field(det, "AvailableDateType", default="0"),
        "available_value": field(det, "AvailableDateValue", default="3"),
        "adult": field(det, "AdultYN", default="N"),
        "keyword": field(det, "Keyword", "SearchKeyword"),
        "description": field(det, "ItemDescription", "ItemDetail", "Description", "ItemContents"),
        "images": [u for u in [it.get("new_image") or field(det, "ImageUrl", "StandardImage")] if u]
                  + list(it.get("extra_images") or []),
        "extra": it.get("extra") or {},
    }
    out["new_seller_code"] = new_seller
    out["title"] = job["title"]
    if dry_run:
        out["preview"] = {k: (v[:200] + "…" if isinstance(v, str) and len(v) > 200 else v) for k, v in job.items()}
        out["detail_raw_keys"] = sorted(det.keys())
        return out

    # 1) 기존 상품 판매중지 (중복 출품 방지)  2) 새로 등록  3) 실패 시 기존 상품 복구
    set_status(sak, code, old_seller, old_action)
    try:
        res = register(job, sak)
    except Exception as e:
        try:
            set_status(sak, code, old_seller, "2")
            note = "기존 상품은 다시 판매중으로 되돌렸어요"
        except Exception as e2:
            note = f"⚠️ 기존 상품 복구 실패! QSM에서 직접 판매중으로 바꿔주세요 ({e2})"
        raise RuntimeError(f"새 등록 실패: {e} → {note}")
    out["new_code"] = res.get("item_code")
    out["warnings"] += res.get("warnings", [])
    return out


def relist(job, sak):
    dry = bool(job.get("dry_run"))
    action = str(job.get("old_action") or "1")
    results = []
    for it in (job.get("items") or [])[:30]:
        try:
            r = relist_one(sak, it, dry, action)
            r["ok"] = True
        except Exception as e:
            r = {"old_code": it.get("code"), "title": it.get("new_title"), "ok": False, "error": str(e)}
        results.append(r)
    return {"dry_run": dry, "results": results,
            "success": sum(r["ok"] for r in results), "failed": sum(not r["ok"] for r in results)}


def run_job(path):
    job_id = os.path.splitext(os.path.basename(path))[0]
    out = {"id": job_id}
    try:
        with open(path, encoding="utf-8") as f:
            job = json.load(f)
        kind = job.get("type", "register")
        out["type"] = kind
        sak = get_seller_key()
        if kind == "scan":
            out.update(scan(job, sak))
        elif kind == "relist":
            out.update(relist(job, sak))
        else:
            out["title"] = job.get("title")
            out.update(register(job, sak))
        out["ok"] = True
    except Exception as e:
        out["ok"] = False
        out["error"] = str(e)
        traceback.print_exc()
    out["finished_at"] = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    os.makedirs("results", exist_ok=True)
    with open(f"results/{job_id}.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in out.items() if k not in ("raw", "items")}, ensure_ascii=False)[:3000])


# ------------------------------------------------------------------ 목록 동기화
def sync():
    sak = get_seller_key()
    os.makedirs("docs/data", exist_ok=True)
    status = {"synced_at": datetime.now(JST).strftime("%Y-%m-%d %H:%M"), "errors": []}

    try:
        d = qapi("ItemsLookup.GetSellerDeliveryGroupInfo", sak)
        ships = []
        for s in d.get("ResultObject") or []:
            low = {k.lower(): v for k, v in s.items()}
            ships.append({"no": str(low.get("shippingno", "")), "name": low.get("shippingname", ""),
                          "fee": low.get("shippingfee", ""), "free": low.get("freecondition", low.get("shippingfreecondition", ""))})
        with open("docs/data/shipping.json", "w", encoding="utf-8") as f:
            json.dump(ships, f, ensure_ascii=False)
    except Exception as e:
        status["errors"].append(f"배송비 목록: {e}")

    try:
        d = qapi("CommonInfoLookup.GetCatagoryListAll", sak, lang_cd="ja")
        cats = []
        for c in d.get("ResultObject") or []:
            low = {k.lower(): v for k, v in c.items()}
            code = str(low.get("cd_s") or low.get("s_code") or "")
            if code:
                cats.append({"c": code, "n": " > ".join(str(low.get(k, "")) for k in ("nm_l", "nm_m", "nm_s") if low.get(k))})
        with open("docs/data/categories.json", "w", encoding="utf-8") as f:
            json.dump(cats, f, ensure_ascii=False, separators=(",", ":"))
    except Exception as e:
        status["errors"].append(f"카테고리 목록: {e}")

    with open("docs/data/sync.json", "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False)
    print(json.dumps(status, ensure_ascii=False))


def main():
    load_dotenv()
    load_actions_secrets()
    ap = argparse.ArgumentParser()
    ap.add_argument("--job")
    ap.add_argument("--sync", action="store_true")
    a = ap.parse_args()
    if a.sync:
        sync()
    elif a.job:
        run_job(a.job)
    else:
        ap.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
