# GitHub Pages 랜딩 배포 (P12)

## 랜딩 페이지 확인
```bash
ls /d/solar_book/landing/
```

## gh-pages 브랜치 배포
```bash
cd /d/solar_book && git subtree push --prefix landing origin gh-pages
```

## GitHub Actions 상태 확인
```bash
gh workflow list
gh run list --limit 5
```
