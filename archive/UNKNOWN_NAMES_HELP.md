# Как исправить неизвестные имена

## Быстрый поиск всех неизвестных:

\`\`\`bash
grep -n "mailto:UNKNOWN" Product_Review_2025/*/*.md
\`\`\`

## Список неизвестных из последнего запуска:

См. файл `unattributed_names.md`

## Как исправить:

### 1. Если знаете email:
Замените вручную в файле:
\`\`\`
[Максим](mailto:UNKNOWN) → [Maksym Silman](mailto:maksym@route4me.com)
\`\`\`

### 2. Добавьте в emails.csv:
\`\`\`csv
"maksym@route4me.com","Maksym Silman","Максим Сильман"
\`\`\`

### 3. Запустите скрипт снова:
\`\`\`bash
python3 standardize_product_reviews.py
\`\`\`

## Частые случаи:

- **Игорь** - 2 человека (igor@route4me.com, igorgolovtsov@route4me.com)
  - Нужен контекст или фамилия
- **Александр/Саша** - несколько человек
  - Используйте фамилию или контекст
- **Команда/Team** - не нужна ссылка, будет удалена автоматически
