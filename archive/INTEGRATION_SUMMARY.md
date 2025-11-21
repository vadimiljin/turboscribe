# Интеграция emails.csv в standardize_product_reviews.py

## Что сделано:

### 1. Загрузка базы данных emails.csv при инициализации
- `load_emails_database()` - читает `emails.csv` и создает 3 индекса:
  - `email_to_full_name`: email → "Artur Moskalenko"
  - `email_to_ru_name`: email → "Артур Москаленко"  
  - `email_to_ru_first`: email → "Артур" (только первое имя)

### 2. Извлечение имен по email из документа
- `extract_names_from_text()` - находит ВСЕ email в документе
- Для каждого email берет данные из `emails.csv`
- Создает mapping для всех вариантов (с падежами):
  - Артур → arturm@route4me.com
  - Артура → arturm@route4me.com  
  - Артуру → arturm@route4me.com
  - Артуром → arturm@route4me.com

### 3. Исправление формата имен
- `fix_name_format()` - пост-обработка текста:
  - **С email**: [Full English Name](mailto:email)
  - **Без email**: [Русское Имя в падеже](mailto:email)

### 4. Жесткие правила для LLM
- `get_known_names_list()` - генерирует промпт со ВСЕМИ людьми из документа
- **КРИТИЧЕСКИЕ ПРАВИЛА**:
  - ⛔ ЗАПРЕЩЕНО придумывать email
  - Используй ТОЛЬКО email из списка
  - Если имени нет → [Имя](mailto:Имя)
  - Группы (Команда, Бэкенд, Дизайнеры) → БЕЗ ссылок

### 5. Отслеживание неизвестных имен
- `save_unattributed_names()` - создает `unattributed_names.md`
- Формат: | Name | Document | Context |
- Автоматически собирает имена без email для ручной проверки

## Алгоритм работы:

```
1. Загрузить emails.csv → индексы
2. Прочитать документ
3. Найти ВСЕ email в документе
4. Для каждого email → взять данные из индексов
5. Создать mapping (имя + падежи → email)
6. Передать в LLM список ВСЕХ людей
7. LLM обрабатывает текст
8. Пост-обработка: исправить оставшиеся ошибки
9. Сохранить неизвестные имена в unattributed_names.md
```

## Правила форматирования:

### С email (в ссылке):
✓ `[Artur Moskalenko](mailto:arturm@route4me.com)`
✗ `[Артур](mailto:arturm@route4me.com)`
✗ `Artur Moskalenko (arturm@route4me.com)`

### Без email (в тексте):
✓ `[Артур](mailto:arturm@route4me.com) предложил`
✓ `Предложение [Артура](mailto:arturm@route4me.com)`
✗ `Артур Москаленко предложил` (не используй фамилию!)
✗ `Артур предложил` (нет ссылки!)

### Специальные случаи:
- `(Команда)` → БЕЗ ссылки
- `(Бэкенд)` → БЕЗ ссылки  
- `(Дизайнеры)` → БЕЗ ссылки
- `**Александр (дизайнер):**` → `**[Александр](mailto:...) (дизайнер):**`

## Файлы:

- `emails.csv` - база данных (Email, Full Name, RU/UA Transcription)
- `standardize_product_reviews.py` - основной скрипт
- `unattributed_names.md` - имена без найденного email (для ручной проверки)
- `employees.md` - централизованная база всех сотрудников

## Проверка порядка:

✅ **Порядок НЕ нарушается** при параллельной обработке:
- Темы обрабатываются параллельно (5 потоков)
- Записываются строго по порядку (1, 2, 3...)
- Используется `topic_results[topic_num]` для сохранения порядка

