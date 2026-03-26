# GitHub Pages 랜딩 배포

`landing/` 폴더를 변경하고 push하면 GitHub Actions가 자동 배포합니다.

## 배포 방법

```bash
cd /d/solar_book
git add landing/
git commit -m "landing: <변경 내용>"
git push origin main
```

→ `.github/workflows/deploy-landing.yml` 자동 실행
→ `https://delion-dev.github.io/bookengine/` 갱신 (1~2분 소요)

## 배포 상태 확인

```bash
curl -s "https://api.github.com/repos/delion-dev/bookengine/actions/runs?per_page=3" \
  | python -c "import sys,json; [print(r['name'],'|',r['status'],'|',r.get('conclusion','—')) for r in json.load(sys.stdin).get('workflow_runs',[])]"
```

## 강제 배포 (파일 변경 없을 때)

```bash
cd /d/solar_book
git commit --allow-empty -m "ci: force landing deploy"
git push origin main
```

## 랜딩 사이트 URL

```
https://delion-dev.github.io/bookengine/
```
