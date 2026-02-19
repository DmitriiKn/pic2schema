#!/bin/bash

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}🚀 Начинаем деплой Cross Stitch Pattern Generator${NC}"

if ! command -v docker &> /dev/null; then
    echo -e "${RED}Docker не установлен!${NC}"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}Docker Compose не установлен!${NC}"
    exit 1
fi

echo -e "${YELLOW}📁 Создаем директории...${NC}"
mkdir -p nginx ssl uploads static

echo -e "${YELLOW}🛑 Останавливаем старые контейнеры...${NC}"
docker-compose down

echo -e "${YELLOW}🏗️  Собираем Docker образы...${NC}"
docker-compose build --no-cache

echo -e "${YELLOW}▶️  Запускаем контейнеры...${NC}"
docker-compose up -d

echo -e "${YELLOW}🔍 Проверяем статус...${NC}"
sleep 5
if docker-compose ps | grep -q "Up"; then
    echo -e "${GREEN}✅ Деплой успешно завершен!${NC}"
    echo -e "${GREEN}🌐 Приложение доступно по адресу: http://localhost${NC}"
else
    echo -e "${RED}❌ Ошибка деплоя! Проверьте логи:${NC}"
    docker-compose logs
    exit 1
fi

echo -e "${YELLOW}📋 Последние логи:${NC}"
docker-compose logs --tail=50