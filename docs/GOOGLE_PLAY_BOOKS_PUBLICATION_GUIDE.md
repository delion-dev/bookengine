# Google Play Books Publication Guide

이 문서는 `S9 / AG-06` 출판 엔진이 따라야 하는 Google Play Books 기준을 코어 정책으로 고정한다.

## Official Sources

- Book file guidelines
  - https://support.google.com/books/partner/answer/11048747
- EPUB files
  - https://support.google.com/books/partner/answer/11048640
- PDF file configuration
  - https://support.google.com/books/partner/answer/11048698

## Engine Policy

### EPUB

- 출력 포맷은 `EPUB 3` 기준의 리플로어블 구조를 사용한다.
- EPUB 내부에는 반드시 front cover image를 포함한다.
- 네비게이션은 `toc` 기반으로만 구성한다.
- JavaScript, MathML, 멀티컬럼 레이아웃에 의존하지 않는다.
- 이미지 포맷은 `GIF`, `JPEG`, `PNG`, `SVG`만 사용한다.
- 임베디드 폰트는 `platform/fonts/NanumGothic-main`의 `NanumGothic.ttf`, `NanumGothicBold.ttf` 2종을 기본으로 한다.

### PDF

- 출력 방향은 `portrait`를 기본으로 한다.
- 본문용 폰트는 EPUB과 같은 `NanumGothic` 계열을 사용한다.
- PDF 렌더러는 시스템에 설치된 `NanumGothic` 패밀리를 우선 사용하고, EPUB은 `platform/fonts`의 원본 파일을 직접 임베딩한다.
- 제목 계층은 PDF 북마크 생성 친화 구조로 유지한다.

### Cover

- 출판 엔진은 별도 `frontcover.png`를 생성한다.
- 기본 커버 크기는 `1400x2000`이며 Google Play Books 권고치인 `3200px 이하`, `3.2MP 이하`를 만족한다.
- EPUB 내부 cover image와 별도 출력 커버는 동일 자산을 사용한다.

### Validation

- `publication_manifest.json`은 아래를 검증한다.
- EPUB 구조: `mimetype`, `container.xml`, `package.opf`, `nav.xhtml`, `cover.xhtml`, `cover image`, `embedded fonts`
- PDF 구조: PDF 시그니처, `NanumGothic` 폰트 문자열 탐지
- 운영 경고: placeholder image가 남아 있는 경우 warning으로 기록

## Local Canonical Assets

- canonical source font root: `platform/fonts/NanumGothic-main`
- canonical embedded font root: `books/<book>/publication/assets/fonts/google_books`
- canonical cover output: `books/<book>/publication/output/<book_id>_frontcover.png`
- canonical style output: `books/<book>/publication/output/google_books_book.css`
