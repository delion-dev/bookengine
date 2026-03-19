# UI/UX 디자인 시스템 검색

BookEngine 디자인 시스템 조회 및 컴포넌트 설계에 활용합니다.

## Design System 전체 조회
```bash
python tools/ui-ux-pro-max/scripts/search.py "<키워드>" --design-system -p "BookEngine" -f markdown
```

## 도메인별 검색
```bash
# 스타일
python tools/ui-ux-pro-max/scripts/search.py "glassmorphism dark" --domain style

# 색상 팔레트
python tools/ui-ux-pro-max/scripts/search.py "productivity SaaS dark" --domain color

# UX 가이드
python tools/ui-ux-pro-max/scripts/search.py "form accessibility" --domain ux

# 타이포그래피
python tools/ui-ux-pro-max/scripts/search.py "modern professional" --domain typography
```

## 디자인 시스템 저장
```bash
python tools/ui-ux-pro-max/scripts/search.py "<키워드>" --design-system --persist -p "BookEngine"
```
