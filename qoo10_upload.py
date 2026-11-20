#!/usr/bin/env python3
"""Qoo10 Japan 상품 등록 (폰 앱 → GitHub Actions에서 실행)

  python qoo10_upload.py --job jobs/<id>.json   # 상품 등록
  python qoo10_upload.py --sync                  # 카테고리/배송비 목록 → docs/data/

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


def run_job(path):
    job_id = os.path.splitext(os.path.basename(path))[0]
    out = {"id": job_id, "finished_at": datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")}
    try:
        with open(path, encoding="utf-8") as f:
            job = json.load(f)
        out["title"] = job.get("title")
        out.update(register(job, get_seller_key()))
        out["ok"] = True
    except Exception as e:
        out["ok"] = False
        out["error"] = str(e)
        traceback.print_exc()
    os.makedirs("results", exist_ok=True)
    with open(f"results/{job_id}.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in out.items() if k != "raw"}, ensure_ascii=False))


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
