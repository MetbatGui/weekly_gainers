# Use PowerShell on Windows
set shell := ["powershell", "-c"]

# 도커 이미지 빌드 (CI가 이 3개 레시피를 build -> deploy -> release 순으로 독립 호출할 수
# 있도록 이름을 표준화함 - handoff_guide.md §2 참고)
docker-build:
    docker compose build

# 최신 이미지로 컨테이너 재기동 (재빌드는 하지 않음 - docker-build를 먼저 실행할 것)
docker-deploy:
    docker compose up -d

# 현재 브랜치가 main/master일 때만 origin push - ship은 "안정화된 main 배포"가 목적이라
# feature 브랜치에서 실수로 배포/릴리즈되는 걸 막는다.
push-main:
    $branch = git rev-parse --abbrev-ref HEAD; if ($branch -ne 'main' -and $branch -ne 'master') { Write-Error "Refusing to push: current branch is '$branch', not main/master"; exit 1 }; git push origin $branch

# push-main -> docker-build -> docker-deploy -> release를 순서대로 한 번에 실행
ship: push-main docker-build docker-deploy release

setup-release:
    git checkout master
    git remote add employers-weekly-gainers https://github.com/guruta71/weekly-gainers.git

# Release to employers-weekly-gainers
# Usage: just release
release:
    git checkout -B release master
    git push -u employers-weekly-gainers release:main
    git checkout master
