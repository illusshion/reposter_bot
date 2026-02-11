#!/bin/bash

# Определяем директорию проекта автоматически
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
SERVICE_NAME="reposter-bot"

# Определяем команду по имени скрипта или первому аргументу
CMD_NAME=$(basename "$0")
if [[ "$CMD_NAME" =~ ^bot- ]]; then
    # Если вызван как bot-start, bot-stop и т.д.
    ACTION="${CMD_NAME#bot-}"
    # Для bot-logs аргумент будет в $1
    LOGS_ARG="$1"
else
    # Если вызван как bot-manager.sh с аргументом
    ACTION="$1"
    LOGS_ARG="$2"
fi

case "$ACTION" in
    start)
        echo "Запуск бота..."
        sudo systemctl start "$SERVICE_NAME"
        echo "✓ Бот запущен"
        ;;
    stop)
        echo "Остановка бота..."
        sudo systemctl stop "$SERVICE_NAME"
        echo "✓ Бот остановлен"
        ;;
    restart)
        echo "Перезапуск бота..."
        sudo systemctl restart "$SERVICE_NAME"
        echo "✓ Бот перезапущен"
        ;;
    status)
        sudo systemctl status "$SERVICE_NAME"
        ;;
    logs)
        if [ -n "$LOGS_ARG" ] && [[ "$LOGS_ARG" =~ ^[0-9]+$ ]]; then
            tail -n "$LOGS_ARG" "$PROJECT_DIR/bot.log"
        else
            tail -f "$PROJECT_DIR/bot.log"
        fi
        ;;
    enable)
        echo "Включение автозапуска..."
        sudo systemctl enable "$SERVICE_NAME"
        echo "✓ Автозапуск включен"
        ;;
    disable)
        echo "Отключение автозапуска..."
        sudo systemctl disable "$SERVICE_NAME"
        echo "✓ Автозапуск отключен"
        ;;
    *)
        # Если вызван напрямую без аргументов, показываем справку
        if [ "$CMD_NAME" == "bot-manager.sh" ] && [ -z "$ACTION" ]; then
            echo "Использование: $0 {start|stop|restart|status|logs|enable|disable}"
            echo ""
            echo "Команды:"
            echo "  start    - запустить бота"
            echo "  stop     - остановить бота"
            echo "  restart  - перезапустить бота"
            echo "  status   - показать статус"
            echo "  logs     - показать логи (tail -f)"
            echo "  logs N   - показать последние N строк логов"
            echo "  enable   - включить автозапуск"
            echo "  disable  - отключить автозапуск"
            exit 1
        fi
        # Если команда не распознана
        echo "✗ Неизвестная команда: $ACTION"
        echo "Используйте: bot-start, bot-stop, bot-restart, bot-status, bot-logs"
        exit 1
        ;;
esac
