# Qoo10 판매 도구 — Claude 작업 규칙

## 사용자가 상품 링크를 보내면 (매입가를 같이 줄 수도 있음)
1. `qoo10-listing-maker` 스킬 절차대로 썸네일·상세페이지 이미지를 만든다
   (아티팩트 '큐텐 상세페이지 메이커' 사용, 질문하지 않고 끝까지 진행).
2. `tools/qoo10_margin.xlsx` 의 '상품' 시트에 행을 추가한다.
   - 첫 번째 빈 행(F열 매입가가 빈 행)에 B 등록일(오늘), C 링크, D 상품명, E 옵션·용량, F 매입가(원), P 진행 상태="썸네일·상세 완료".
   - 예시 행(5행, 메모에 "예시 행")은 첫 실제 상품을 넣을 때 그 행을 덮어쓴다.
   - 수식 열(A,G~O)은 건드리지 않는다. 저장 후 xlsx 스킬의 recalc.py 로 재계산·오류 0 확인.
   - 매입가를 모르면 F는 비우고 답변 마지막에 "매입가 알려주면 마진 계산해 둘게요" 한 줄.
3. 완성 이미지는 `listings/<YYMMDD>-<상품 짧은이름>/` 에 저장
   (thumb.png, detail.png, detail_01.png…, copy.json).
4. 답변에는 권장 판매가·순이익(엔/원)·마진율을 한 줄로, 그리고 이미지·엑셀 파일을 SendUserFile로 보낸다.
5. 사용자가 원하면 커밋·푸시. 푸시된 이미지 주소(raw.githubusercontent.com)는 폰 앱 신규 등록에 그대로 쓸 수 있다.

## 구조
- `qoo10_alert.txt` + `.github/workflows/alert.yml`: 신규 주문 알림
- `docs/` (폰 앱), `qoo10_upload.py`, `.github/workflows/upload.yml`: 신규 등록·페이지 갈이
- `tools/qoo10_margin.xlsx`: 마진 계산표 (설정 시트에 환율·수수료·배송비)
