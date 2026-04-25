#!/usr/bin/env python
"""Тестовый скрипт для проверки конфигурации."""

from app.config import Settings

try:
    settings = Settings()
    print("Settings loaded successfully!")
    print(f"MAX_CONTEXT_MESSAGES: {settings.max_context_messages}")
except Exception as e:
    print(f"Error loading settings: {e}")
    print("Trying to fix the issue...")
    
    # Попробуем исправить проблему, добавив обработку пустых значений
    import os
    os.environ["MAX_CONTEXT_MESSAGES"] = "40"
    
    try:
        settings = Settings()
        print("Settings loaded successfully after fix!")
        print(f"MAX_CONTEXT_MESSAGES: {settings.max_context_messages}")
    except Exception as e:
        print(f"Error loading settings after fix: {e}")