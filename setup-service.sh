#!/bin/bash

set -e

CURRENT_USER=$(whoami)
PROJECT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
VENV_PYTHON="$PROJECT_DIR/venv/bin/python"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "✗ Ошибка: виртуальное окружение не найдено!"
    echo "Сначала выполни: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
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

echo ""
echo "✓ Готово! Бот настроен на автозапуск."
echo ""
echo "Полезные команды:"
echo "  sudo systemctl status reposter-bot  - проверить статус"
echo "  sudo systemctl restart reposter-bot - перезапустить"
echo "  sudo systemctl stop reposter-bot    - остановить"
echo "  tail -f $PROJECT_DIR/bot.log        - посмотреть логи"
echo ""
