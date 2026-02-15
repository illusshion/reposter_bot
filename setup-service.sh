#!/bin/bash

set -e

CURRENT_USER=$(whoami)
PROJECT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
VENV_DIR="$PROJECT_DIR/venv"
VENV_PYTHON="$VENV_DIR/bin/python"

echo "Настройка бота..."
echo "   Пользователь: $CURRENT_USER"
echo "   Директория: $PROJECT_DIR"
echo ""

# Проверка Python
if ! command -v python3 &> /dev/null; then
    echo "✗ Ошибка: Python3 не установлен!"
    exit 1
fi

# Создание виртуального окружения если его нет
if [ ! -f "$VENV_PYTHON" ]; then
    echo "Создание виртуального окружения..."
    python3 -m venv "$VENV_DIR"
    echo "✓ Виртуальное окружение создано"
fi

# Установка зависимостей
if [ -f "$PROJECT_DIR/requirements.txt" ]; then
    echo "Установка зависимостей..."
    "$VENV_DIR/bin/pip" install --upgrade pip -q
    "$VENV_DIR/bin/pip" install -r "$PROJECT_DIR/requirements.txt" -q
    echo "✓ Зависимости установлены"
else
    echo "⚠ Предупреждение: файл requirements.txt не найден"
fi

# Проверка .env файла
if [ ! -f "$PROJECT_DIR/.env" ]; then
    if [ -f "$PROJECT_DIR/.env.example" ]; then
        echo ""
        echo "⚠ Файл .env не найден!"
        echo "Создаю .env из примера..."
        cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
        echo "✓ Файл .env создан"
        echo ""
        echo "⚠ ВАЖНО: Отредактируйте файл .env и заполните необходимые параметры:"
        echo "   nano $PROJECT_DIR/.env"
        echo ""
        read -p "Нажмите Enter после заполнения .env файла..."
    else
        echo "✗ Ошибка: файл .env не найден и нет примера .env.example"
        exit 1
    fi
fi

if [ ! -f "$PROJECT_DIR/main.py" ]; then
    echo "✗ Ошибка: файл main.py не найден!"
    exit 1
fi

echo "Настройка автозапуска бота..."
echo "   Пользователь: $CURRENT_USER"
echo "   Директория: $PROJECT_DIR"
echo ""

SERVICE_FILE="/etc/systemd/system/reposter-bot.service"

sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Reposter Bot
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PROJECT_DIR/venv/bin"
ExecStart=$VENV_PYTHON $PROJECT_DIR/main.py
Restart=always
RestartSec=10
StandardOutput=append:$PROJECT_DIR/bot.log
StandardError=append:$PROJECT_DIR/bot.log

[Install]
WantedBy=multi-user.target
EOF

echo "✓ Файл сервиса создан: $SERVICE_FILE"
echo ""

echo "Перезагрузка systemd..."
sudo systemctl daemon-reload

echo "Включение автозапуска..."
sudo systemctl enable reposter-bot

echo "Запуск бота..."
sudo systemctl start reposter-bot

# Установка команд управления ботом
echo "Установка команд управления..."
BOT_MANAGER="$PROJECT_DIR/bot-manager.sh"
BOT_SETUP="$PROJECT_DIR/bot-setup.sh"

if [ -f "$BOT_MANAGER" ]; then
    chmod +x "$BOT_MANAGER"
    
    # Создаем симлинки для простых команд
    sudo ln -sf "$BOT_MANAGER" /usr/local/bin/bot-start
    sudo ln -sf "$BOT_MANAGER" /usr/local/bin/bot-stop
    sudo ln -sf "$BOT_MANAGER" /usr/local/bin/bot-restart
    sudo ln -sf "$BOT_MANAGER" /usr/local/bin/bot-status
    sudo ln -sf "$BOT_MANAGER" /usr/local/bin/bot-logs
    
    echo "✓ Команды управления установлены"
else
    echo "⚠ Предупреждение: bot-manager.sh не найден"
fi

# Установка команды bot-setup для запуска из любой директории
if [ -f "$BOT_SETUP" ]; then
    chmod +x "$BOT_SETUP"
    sudo ln -sf "$BOT_SETUP" /usr/local/bin/bot-setup
    echo "✓ Команда bot-setup установлена"
fi

echo ""
echo "✓ Готово! Бот настроен на автозапуск."
echo ""
echo "Полезные команды:"
echo "  bot-start    - запустить бота"
echo "  bot-stop     - остановить бота"
echo "  bot-restart  - перезапустить бота"
echo "  bot-status   - проверить статус"
echo "  bot-logs     - посмотреть логи"
echo "  bot-logs 100 - показать последние 100 строк логов"
echo ""
