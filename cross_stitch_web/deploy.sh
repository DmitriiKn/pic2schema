#!/bin/bash

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Настройки
PORT=${1:-8080}  # Можно передать порт как аргумент, по умолчанию 8080

echo -e "${GREEN}🚀 Начинаем деплой Cross Stitch Pattern Generator на порту ${PORT}${NC}"

# Проверка наличия Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Docker не установлен!${NC}"
    exit 1
fi

# Проверка наличия Docker Compose
if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}Docker Compose не установлен!${NC}"
    exit 1
fi

# Проверка версии Docker Compose
COMPOSE_VERSION=$(docker-compose --version | grep -oP '\d+\.\d+\.\d+' | head -1)
echo -e "${YELLOW}📌 Docker Compose версия: ${COMPOSE_VERSION}${NC}"

# Создание необходимых директорий
echo -e "${YELLOW}📁 Создаем директории...${NC}"
mkdir -p nginx ssl uploads static

# Проверяем, что статический файл существует
if [ ! -f "static/index.html" ]; then
    echo -e "${YELLOW}⚠️  Файл static/index.html не найден. Создаем заглушку...${NC}"
    cat > static/index.html << 'EOF'
<!DOCTYPE html>
<html>
<head>
    <title>Cross Stitch Pattern Generator</title>
</head>
<body>
    <h1>Приложение запускается...</h1>
    <p>Пожалуйста, подождите несколько секунд и обновите страницу.</p>
</body>
</html>
EOF
fi

# Остановка старых контейнеров
echo -e "${YELLOW}🛑 Останавливаем старые контейнеры...${NC}"
docker-compose down --remove-orphans

# Очистка старых volume (опционально)
# docker volume prune -f

# Сборка новых образов
echo -e "${YELLOW}🏗️  Собираем Docker образы...${NC}"
docker-compose build --no-cache

# Запуск контейнеров
echo -e "${YELLOW}▶️  Запускаем контейнеры...${NC}"
docker-compose up -d

# Ждем запуска
echo -e "${YELLOW}⏳ Ожидаем запуска контейнеров...${NC}"
sleep 10

# Проверка статуса
echo -e "${YELLOW}🔍 Проверяем статус...${NC}"
if docker-compose ps | grep -q "Up"; then
    echo -e "${GREEN}✅ Контейнеры успешно запущены!${NC}"
    
    # Проверяем доступность приложения
    echo -e "${YELLOW}🌐 Проверяем доступность приложения...${NC}"
    
    # Проверка через curl
    if command -v curl &> /dev/null; then
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:${PORT})
        if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "301" ] || [ "$HTTP_CODE" = "302" ]; then
            echo -e "${GREEN}✅ Приложение доступно по адресу: http://localhost:${PORT}${NC}"
        else
            echo -e "${RED}❌ Приложение вернуло код ${HTTP_CODE}${NC}"
            echo -e "${YELLOW}📋 Проверьте логи:${NC}"
            docker-compose logs --tail=20
        fi
    else
        echo -e "${GREEN}✅ Приложение запущено. Проверьте: http://localhost:${PORT}${NC}"
    fi
    
    # Показываем информацию
    echo -e "\n${YELLOW}📌 Информация:${NC}"
    echo "   - Локальный доступ: http://localhost:${PORT}"
    
    # Пытаемся получить IP
    if command -v ip &> /dev/null; then
        IP=$(ip route get 1 | awk '{print $NF;exit}' 2>/dev/null)
        echo "   - Из сети: http://${IP}:${PORT}"
    elif command -v hostname &> /dev/null; then
        echo "   - Из сети: http://$(hostname -I | awk '{print $1}'):${PORT}"
    fi
else
    echo -e "${RED}❌ Ошибка запуска контейнеров!${NC}"
    echo -e "${YELLOW}📋 Логи:${NC}"
    docker-compose logs
    exit 1
fi

# Показываем логи
echo -e "\n${YELLOW}📋 Последние логи (Ctrl+C для выхода):${NC}"
docker-compose logs --tail=50