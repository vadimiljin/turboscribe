# Product Review Standardization Scripts

Автоматическая стандартизация файлов Product Review с использованием GPT-4o-mini.

## Файлы

- **`standardize_product_reviews.py`** - Основной скрипт для обработки всех файлов
- **`test_standardize_single.py`** - Тестовый скрипт для обработки одного файла

## Требования

```bash
pip install openai python-dotenv
```

## Настройка

Создайте файл `.env` в корне проекта:

```bash
OPENAI_API_KEY='your-openai-api-key-here'
```

## Использование

### Тест одного файла

```bash
cd /home/vadim/Projects/route4me.com/turboscribe
python3 test_standardize_single.py
```

По умолчанию обрабатывает файл: `Product_Review_2025/4. Product Review 29 May/4.Product_Review_29_May.md`

### Обработка всех файлов

```bash
cd /home/vadim/Projects/route4me.com/turboscribe
python3 standardize_product_reviews.py
```

Скрипт:
- Сканирует все папки в `Product_Review_2025/`
- Находит все `.md` файлы (кроме `*_CLEAN.md`)
- Пропускает файлы, у которых уже есть `_CLEAN` версия
- Обрабатывает каждый файл с помощью GPT-4o-mini
- Сохраняет результат в `*_CLEAN.md`
- Логирует прогресс в `standardization_log.jsonl`

## Особенности

### Стратегии обработки

1. **Full mode** (файлы < 50KB):
   - Обрабатывает файл целиком за один запрос
   - Быстрее и дешевле

2. **Chunked mode** (файлы ≥ 50KB):
   - Chunk 1: Заголовок и Agenda
   - Chunk 2: Все темы обсуждения
   - Более надежно для больших файлов

### Стоимость

**GPT-4o-mini:**
- Input: $0.150 / 1M tokens
- Output: $0.600 / 1M tokens

Примерная стоимость:
- Маленький файл (~20KB): $0.01-0.02
- Средний файл (~50KB): $0.02-0.04
- Большой файл (~100KB): $0.04-0.08

**Для ~40 файлов:** ожидаемая стоимость $0.40-1.50

### Правила стандартизации

Скрипт применяет все правила из `STANDARDIZATION_RULES.md`:
- Форматирование заголовка с Recording и Passcode
- Структурирование Agenda и Questions
- Стандартная структура для каждой темы обсуждения
- Сохранение всех таймстемпов, ссылок, имен
- Преобразование inline numbered lists
- Исправление имени CEO (Dan/Дэн)
- Форматирование labels в ключевых моментах

## Результаты теста

Тестовый файл: `4.Product_Review_29_May.md`
- **Исходный размер:** 97.7 KB (560 строк)
- **Результат:** 828 строк
- **Статус:** ✅ Успешно обработан в chunked mode
- **Стратегия:** 2 chunks (Header + Topics)

Проверка показала:
- ✅ Правильное форматирование заголовка
- ✅ Структурированный Agenda с владельцами
- ✅ Все темы обсуждения переформатированы
- ✅ Таймстемпы сохранены
- ✅ Разделители `------` на месте

## Логирование

Все операции логируются в `Product_Review_2025/standardization_log.jsonl`:

```json
{
  "timestamp": "2025-11-14T20:58:44.971735",
  "file": "...",
  "folder": "4. Product Review 29 May",
  "status": "success_chunked",
  "details": "Processed in 2 chunks"
}
```

## Опции настройки

В `main()` функции можно изменить:

```python
# Пропускать файлы с существующей _CLEAN версией
skip_existing=True  

# Ограничить количество файлов (для теста)
max_files=5  # или None для всех файлов
```

## Troubleshooting

### API ключ не найден
```
❌ OPENAI_API_KEY не найден в .env!
```
**Решение:** Создайте файл `.env` с вашим OpenAI API ключом

### Ошибка импорта openai
```
⚠️  OpenAI не установлен
```
**Решение:** `pip install openai python-dotenv`

### Rate limiting
Если получаете rate limit ошибки, увеличьте паузу между запросами в коде:
```python
time.sleep(2)  # увеличьте до 5-10
```

## Дальнейшие шаги

1. ✅ Протестировано на одном файле
2. Запустите на всех файлах: `python3 standardize_product_reviews.py`
3. Проверьте несколько результатов вручную
4. Убедитесь, что все содержимое сохранено
5. Проверьте лог для ошибок

## Лицензия

Внутренний инструмент Route4Me.

