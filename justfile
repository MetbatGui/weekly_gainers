# 도커 이미지 빌드
build:
    docker compose build

# 최신 이미지로 컨테이너 재기동
up:
    docker compose up -d

# 빌드 후 재기동
deploy: build up
