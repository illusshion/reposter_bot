#!/bin/bash

# Определяем директорию проекта автоматически
# Используем readlink для получения реального пути даже при вызове через симлинк
if [ -L "$0" ]; then
    # Если вызван через симлинк, получаем реальный путь
    REAL_SCRIPT=$(readlink -f "$0")
    SCRIPT_DIR="$(cd "$(dirname "$REAL_SCRIPT")" && pwd)"
else
    # Если вызван напрямую
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

PROJECT_DIR="$SCRIPT_DIR"

if [ ! -f "$PROJECT_DIR/setup-service.sh" ]; then
    echo "✗ Ошибка: файл setup-service.sh не найден в $PROJECT_DIR"
    exit 1
fi

exec "$PROJECT_DIR/setup-service.sh"
