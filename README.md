# qoo10-order-alert

Qoo10 Japan 판매자용 도구 모음
1. **주문 알림** – 새 주문이 들어오면 텔레그램/디스코드로 알려줘요 (`qoo10_alert.txt`, `alert.yml`)
2. **📱 폰 상품 등록 앱** – 폰으로 사진 찍어서 바로 Qoo10에 상품 등록 (`docs/`, `qoo10_upload.py`, `upload.yml`)

---

## 📱 폰 상품 등록 앱

### 동작 방식
```
폰 앱(GitHub Pages) ──사진·상품정보 저장──▶ 이 저장소
        └──등록 요청──▶ GitHub Actions(qoo10_upload.py) ──▶ Qoo10 API
                                  └── 결과(results/)를 저장 → 앱에 표시
```
Qoo10 API 키는 이미 주문 알림용으로 넣어둔 **GitHub Secrets** 를 그대로 씁니다
(`QOO10_SAK` 또는 `QOO10_API_KEY` + `QOO10_USER_ID` + `QOO10_PASSWORD`).

### 처음 한 번만 설정
1. **GitHub Pages 켜기**: 저장소 → Settings → Pages → Source: *Deploy from a branch* → Branch `main` / 폴더 `/docs` → Save
   → 1~2분 뒤 `https://kbj8917.github.io/qoo10-order-alert/` 에서 앱이 열려요.
2. **GitHub 토큰 만들기**: GitHub → Settings → Developer settings → Personal access tokens → *Fine-grained tokens* → Generate
   - Repository access: *Only select repositories* → `qoo10-order-alert`
   - Permissions: **Contents: Read and write**, **Actions: Read and write**
3. 폰에서 앱 주소 열기 → ⚙︎ 설정에 토큰 붙여넣기 → 저장
4. 설정에서 **「카테고리·배송비 목록 Qoo10에서 불러오기」** 누르기 (1~2분)
5. 홈 화면에 추가 (iPhone: 공유 → 홈 화면에 추가 / 안드로이드: ⋮ → 홈 화면에 추가) → 앱처럼 사용

### 사용
사진 촬영/선택 → 상품명 · 카테고리 · 가격 · 재고 · 배송비 선택 → **Qoo10에 등록하기**
→ 30초~1분 뒤 결과(상품번호 또는 오류)가 표시돼요. 실패한 건 「최근 등록」에서 *다시 시도* 가능.

### 참고 / 주의
- 사진은 자동으로 압축(최대 1200px)돼 저장소 `uploads/` 에 올라가고, 그 주소를 Qoo10이 가져가요.
  **저장소가 공개(public)라서 사진·상품정보도 공개**됩니다 (판매할 상품 이미지라 보통 문제 없음). 토큰·API 키는 공개되지 않아요.
- 등록 직후엔 Qoo10 측 심사/반영에 시간이 걸릴 수 있어요.
- Qoo10 API 필드가 바뀌었거나 추가 항목이 필요하면 앱의 *추가 옵션 → 추가 API 파라미터(JSON)* 에 넣으면 그대로 전달돼요.
  예: `{"PromotionName":"本日発送","TaxRate":"10"}`
- 등록 오류 상세 로그: 저장소 → Actions → *qoo10-upload*
