# Use PowerShell on Windows
set shell := ["powershell", "-c"]

# 도커 이미지 빌드
build:
    docker compose build

# 최신 이미지로 컨테이너 재기동
up:
    docker compose up -d

# 빌드 후 재기동
deploy: build up

setup-release:
    git checkout master
    git remote add employers-weekly-gainers https://github.com/guruta71/weekly-gainers.git

# Release to employers-weekly-gainers
# Usage: just release
release:
    git checkout -B release master
    git push -u employers-weekly-gainers release:main
    git checkout master
