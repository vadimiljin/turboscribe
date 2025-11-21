#!/usr/bin/env python3
"""
Автоматическая стандартизация файлов Product Review с использованием LLM.

Использует GPT-4o-mini для применения правил стандартизации к всем файлам в Product_Review_2025.
"""

import os
import json
import time
import re
import traceback
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import random

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("[WARN]  OpenAI не установлен. Выполните: pip install openai")
    exit(1)

try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False
    print("[WARN]  python-dotenv не установлен. Выполните: pip install python-dotenv")


class ProductReviewStandardizer:
    # Словарь уменьшительных имен (автоматически генерируется из emails.csv)
    # КРИТИЧНО: Привязаны к конкретным людям на основе RU/UA Transcription из emails.csv
    DIMINUTIVE_NAMES = {
        # Русские имена
        'Александр': ['Саша', 'Саня', 'Шура', 'Алекс'],
        'Олександр': ['Саша', 'Саня', 'Александр', 'Алекс'],  # Украинский вариант
        'Володимир': ['Володя'],  # Для Volodymyr Ishchenko (БЕЗ Вова!)
        'Владимир': ['Володя'],  # Для Vladimir Fedorov (БЕЗ Вова!)
        'Вова': [],  # Вова - это ПОЛНОЕ имя Vladimir Zhakhavets! Не уменьшительное
        'Евгений': ['Женя'],
        'Максим': ['Макс'],
        'Ольга': ['Оля'],
        'Дмитрий': ['Дима', 'Митя'],
        'Артем': ['Тема', 'Артёмка'],
        'Антон': ['Тоха', 'Антоша'],
        'Виктор': ['Витя'],
        'Роман': ['Рома'],
        'Юрий': ['Юра'],
        'Олег': ['Олежек'],
        'Сергей': ['Серёжа'],
        'Игорь': ['Игорёк'],
        'Алексей': ['Лёша', 'Алёша'],
        'Семён': ['Сёма'],
        'Гурген': ['Гур'],
        'Артур': ['Тур'],
        'Вадим': ['Вадик'],
        'Даврон': ['Давр'],
        # Английские варианты
        'Alexander': ['Alex', 'Sasha'],
        'Oleksandr': ['Alex', 'Sasha'],
        'Vladimir': [],  # БЕЗ Vova - это другой человек!
        'Volodymyr': [],  # БЕЗ Vova - это другой человек!
        'Eugene': ['Gene'],
        'Maksym': ['Max'],
        'Dmitry': ['Dima'],
        'Victor': ['Vic'],
        'Yuriy': ['Yura'],
    }
    
    # Специальные случаи транслитерации
    TRANSLITERATION_ALIASES = {
        'Ден': 'Дэн',
        'Дан': 'Дэн',
        'Den': 'Dan',
        'Семен': 'Семён',
    }
    
    def __init__(self, api_key: str, base_dir: str, rules_file: str):
        self.client = OpenAI(api_key=api_key)
        self.base_dir = Path(base_dir)
        self.rules_file = Path(rules_file)
        self.log_file = self.base_dir / "standardization_log.jsonl"
        
        # Читаем правила стандартизации
        with open(self.rules_file, 'r', encoding='utf-8') as f:
            self.rules = f.read()
        
        # Словарь для отслеживания имен и их email
        self.name_to_email = {}
        self.mentioned_names_no_email = set()
        
        # Лог неизвестных имен для отладки
        # Структура: [(name, document_path, line_number, context)]
        self.unattributed_names = []
        
        print(f"[OK] Правила загружены: {len(self.rules)} символов", flush=True)
        
        # Загружаем базу email из emails.csv
        self.load_emails_database()
        
        # Генерируем все варианты имен (падежи + уменьшительные)
        self.generate_name_variants()
    
    def generate_name_variants(self):
        """
        Генерирует ВСЕ возможные варианты имен из emails.csv:
        - Все падежи (именительный, родительный, дательный, винительный, творительный)
        - Уменьшительные формы (Саша, Оля, Макс)
        - Английские варианты
        
        Создает mapping: variant -> email для разрешения неоднозначности.
        """
        if not hasattr(self, 'email_to_ru_name'):
            return
        
        # Структура: {name_variant: [emails]} для поиска конфликтов
        self.name_variant_to_emails = {}
        
        for email, ru_full_name in self.email_to_ru_name.items():
            full_name_en = self.email_to_full_name.get(email, '')
            
            # Разбираем русское полное имя
            parts_ru = ru_full_name.split()
            first_name_ru = parts_ru[0] if parts_ru else ''
            last_name_ru = parts_ru[1] if len(parts_ru) > 1 else ''
            
            # Разбираем английское полное имя
            parts_en = full_name_en.split()
            first_name_en = parts_en[0] if parts_en else ''
            last_name_en = parts_en[1] if len(parts_en) > 1 else ''
            
            all_variants = set()
            
            # 1. ПОЛНЫЕ ИМЕНА
            all_variants.add(ru_full_name)
            all_variants.add(full_name_en)
            
            # 2. ПЕРВОЕ ИМЯ (именительный падеж)
            all_variants.add(first_name_ru)
            all_variants.add(first_name_en)
            
            # 3. ПАДЕЖИ РУССКОГО ИМЕНИ
            if first_name_ru:
                all_variants.update(self._generate_case_variants(first_name_ru))
            
            if last_name_ru:
                all_variants.update(self._generate_case_variants(last_name_ru))
            
            # 4. УМЕНЬШИТЕЛЬНЫЕ ФОРМЫ
            if first_name_ru in self.DIMINUTIVE_NAMES:
                all_variants.update(self.DIMINUTIVE_NAMES[first_name_ru])
                # Добавляем падежи для уменьшительных
                for dim in self.DIMINUTIVE_NAMES[first_name_ru]:
                    all_variants.update(self._generate_case_variants(dim))
            
            if first_name_en in self.DIMINUTIVE_NAMES:
                all_variants.update(self.DIMINUTIVE_NAMES[first_name_en])
            
            # 5. ТРАНСЛИТЕРАЦИЯ И АЛИАСЫ
            for variant in list(all_variants):
                if variant in self.TRANSLITERATION_ALIASES:
                    all_variants.add(self.TRANSLITERATION_ALIASES[variant])
            
            # Сохраняем все варианты
            for variant in all_variants:
                if not variant:
                    continue
                if variant not in self.name_variant_to_emails:
                    self.name_variant_to_emails[variant] = []
                self.name_variant_to_emails[variant].append(email)
        
        # Статистика
        total_variants = len(self.name_variant_to_emails)
        ambiguous = {v: e for v, e in self.name_variant_to_emails.items() if len(e) > 1}
        
        print(f"[OK] Сгенерировано {total_variants} вариантов имен", flush=True)
        print(f"[INFO] Неоднозначных вариантов: {len(ambiguous)}", flush=True)
        
        if ambiguous:
            print(f"[INFO] Примеры конфликтов:", flush=True)
            for name, emails in list(ambiguous.items())[:3]:
                names = [self.email_to_full_name.get(e, e) for e in emails]
                print(f"   - '{name}': {', '.join(names)}", flush=True)
    
    def _generate_case_variants(self, name: str) -> set:
        """
        Генерирует все падежи для имени (русского).
        
        Правила склонения:
        - Мужские имена на согласную: Артур -> Артура, Артуру, Артуром, Артуре
        - Мужские имена на -й: Евгений -> Евгения, Евгению, Евгением, Евгении
        - Мужские имена на -ь: Игорь -> Игоря, Игорю, Игорем, Игоре
        - Женские имена на -а: Ольга -> Ольги, Ольге, Ольгу, Ольгой, Ольге
        """
        variants = {name}  # Именительный падеж
        
        if not name or not any(c.isalpha() and ord(c) > 127 for c in name):
            # Не русское имя
            return variants
        
        # Мужские имена на согласную (р, м, н, к, т и т.д.)
        if name[-1] in 'рмнктлбвгджзпсфхцчшщ':
            variants.add(name + 'а')    # Родительный: Артура
            variants.add(name + 'у')    # Дательный: Артуру
            variants.add(name + 'ом')   # Творительный: Артуром
            variants.add(name + 'е')    # Предложный: Артуре
        
        # Мужские имена на -й
        elif name.endswith('й'):
            base = name[:-1]
            variants.add(base + 'я')    # Родительный: Евгения
            variants.add(base + 'ю')    # Дательный: Евгению
            variants.add(base + 'ем')   # Творительный: Евгением
            variants.add(base + 'и')    # Предложный: Евгении
        
        # Мужские имена на -ь
        elif name.endswith('ь'):
            base = name[:-1]
            variants.add(base + 'я')    # Родительный: Игоря
            variants.add(base + 'ю')    # Дательный: Игорю
            variants.add(base + 'ем')   # Творительный: Игорем
            variants.add(base + 'е')    # Предложный: Игоре
        
        # Женские имена на -а
        elif name.endswith('а'):
            base = name[:-1]
            variants.add(base + 'и')    # Родительный: Ольги
            variants.add(base + 'е')    # Дательный: Ольге
            variants.add(base + 'у')    # Винительный: Ольгу
            variants.add(base + 'ой')   # Творительный: Ольгой
            variants.add(base + 'е')    # Предложный: Ольге
        
        # Фамилии на -ов, -ев, -ин
        elif name.endswith('ов') or name.endswith('ев') or name.endswith('ин'):
            variants.add(name + 'а')    # Родительный: Федорова
            variants.add(name + 'у')    # Дательный: Федорову
            variants.add(name + 'ым')   # Творительный: Федоровым
            variants.add(name + 'е')    # Предложный: Федорове
        
        # Фамилии на -ский
        elif name.endswith('ский'):
            base = name[:-2]  # Убираем "ий"
            variants.add(base + 'ого')  # Родительный: Скрыньковского
            variants.add(base + 'ому')  # Дательный: Скрыньковскому
            variants.add(base + 'им')   # Творительный: Скрыньковским
            variants.add(base + 'ом')   # Предложный: Скрыньковском
        
        return variants
    
    def load_emails_database(self):
        """
        Загружает базу email из emails.csv.
        
        Email = уникальный идентификатор человека.
        Для каждого email:
        - Full Name (английское) - используется РЯДОМ с email
        - RU/UA Transcription (только первое имя) - используется В ТЕКСТЕ в нужном падеже
        """
        import csv
        
        emails_file = self.base_dir.parent / 'emails.csv'
        
        # Индексы для быстрого поиска
        self.email_to_full_name = {}     # email -> "Artur Moskalenko"
        self.email_to_ru_name = {}       # email -> "Артур Москаленко" (полное)
        self.email_to_ru_first = {}      # email -> "Артур" (только первое имя)
        
        if not emails_file.exists():
            print("[WARN] emails.csv не найден, будет использоваться динамическое извлечение", flush=True)
            return
        
        with open(emails_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                email = row['Email'].strip()
                full_name = row['Full Name'].strip()
                ru_transcription = row['RU/UA Transcription from ENGLISH'].strip()
                
                self.email_to_full_name[email] = full_name
                
                if ru_transcription:
                    self.email_to_ru_name[email] = ru_transcription
                    # Берем только ПЕРВОЕ имя (без фамилии) для использования в тексте
                    ru_first = ru_transcription.split()[0]
                    self.email_to_ru_first[email] = ru_first
        
        print(f"[OK] Загружено {len(self.email_to_full_name)} email из emails.csv", flush=True)
        if self.email_to_full_name:
            sample = list(self.email_to_full_name.items())[:3]
            print(f"[INFO] Примеры: {', '.join([f'{name} ({email})' for email, name in sample])}", flush=True)
    
    
    def resolve_name_disambiguation(self, document_content: str, agenda_section: str) -> Dict[str, str]:
        """
        Разрешает неоднозначность имен с помощью LLM API.
        
        Использует ТОЛЬКО emails.csv + автоматически сгенерированные варианты имен.
        Когда в документе есть несколько людей с одинаковым именем (например, два Владимира),
        использует контекст всего документа для точной атрибуции.
        
        Returns:
            Dict[ambiguous_name, resolved_email]: mapping неоднозначных имен к email
        """
        if not hasattr(self, 'name_variant_to_emails'):
            print("   [SKIP] Варианты имен не сгенерированы, пропускаем disambiguation", flush=True)
            return {}
        
        # ШАГ 1: Находим AMBIGUOUS имена (где > 1 кандидата)
        ambiguous_names = {name: emails for name, emails in self.name_variant_to_emails.items() 
                          if len(emails) > 1}
        
        if not ambiguous_names:
            print("   [OK] Конфликтов имен не обнаружено", flush=True)
            return {}
        
        print(f"   [INFO] Найдено {len(ambiguous_names)} неоднозначных вариантов имен", flush=True)
        
        # ШАГ 2: Для каждого неоднозначного имени ищем упоминания в документе
        resolutions = {}
        
        for ambiguous_name, candidate_emails in ambiguous_names.items():
            # Пропускаем слишком короткие имена (< 3 символа)
            if len(ambiguous_name) < 3:
                continue
            
            # Ищем упоминания этого имени в документе
            pattern = rf'\b{re.escape(ambiguous_name)}\b'
            mentions = []
            
            for match in re.finditer(pattern, document_content, re.IGNORECASE):
                start = max(0, match.start() - 200)
                end = min(len(document_content), match.end() + 200)
                context = document_content[start:end]
                
                # Находим номер строки
                line_num = document_content[:match.start()].count('\n') + 1
                
                mentions.append({
                    'text': match.group(0),
                    'context': context,
                    'line': line_num
                })
            
            if not mentions:
                continue
            
            # Только если найдено достаточно упоминаний
            if len(mentions) < 2:
                continue
            
            print(f"\n   [DISAMB] Разрешение для '{ambiguous_name}' ({len(candidate_emails)} кандидатов, {len(mentions)} упоминаний)...", flush=True)
            
            # ШАГ 3: Собираем информацию о кандидатах
            candidates_info = []
            for email in candidate_emails:
                full_name = self.email_to_full_name.get(email, '')
                ru_name = self.email_to_ru_name.get(email, '')
                
                # Ищем зону ответственности в Agenda
                responsibilities = []
                for line in agenda_section.split('\n'):
                    if email in line or full_name in line:
                        # Извлекаем тему из строки типа "- Order Snapshot [[Name]]"
                        topic_match = re.match(r'^-\s+(.+?)\s+\[', line)
                        if topic_match:
                            responsibilities.append(topic_match.group(1).strip())
                
                candidates_info.append({
                    'email': email,
                    'full_name': full_name,
                    'ru_name': ru_name,
                    'responsibilities': responsibilities
                })
            
            # ШАГ 4: Вызываем LLM для разрешения
            try:
                resolved_email = self._call_llm_for_disambiguation(
                    ambiguous_name,
                    mentions[:5],  # Ограничиваем количество примеров
                    candidates_info,
                    agenda_section,
                    document_content
                )
                
                if resolved_email:
                    resolutions[ambiguous_name] = resolved_email
                    emp_name = self.email_to_full_name.get(resolved_email, resolved_email)
                    print(f"   [OK] '{ambiguous_name}' → {emp_name} ({resolved_email})", flush=True)
                else:
                    print(f"   [WARN] Не удалось разрешить '{ambiguous_name}'", flush=True)
                    
            except Exception as e:
                print(f"   [ERROR] Ошибка при разрешении '{ambiguous_name}': {e}", flush=True)
        
        return resolutions
    
    def _call_llm_for_disambiguation(
        self,
        ambiguous_name: str,
        mentions: List[Dict],
        candidates: List[Dict],
        agenda: str,
        full_document: str
    ) -> Optional[str]:
        """
        Вызывает LLM API для разрешения неоднозначности конкретного имени.
        
        Returns:
            email выбранного кандидата или None
        """
        # Подготовка информации о кандидатах
        candidates_text = ""
        for i, cand in enumerate(candidates, 1):
            candidates_text += f"\n{i}. {cand['full_name']} ({cand['email']})\n"
            if cand['ru_name']:
                candidates_text += f"   Русское имя: {cand['ru_name']}\n"
            if cand['responsibilities']:
                candidates_text += f"   Зоны ответственности в Agenda: {', '.join(cand['responsibilities'])}\n"
            else:
                candidates_text += f"   Зоны ответственности: не указаны в Agenda\n"
        
        # Подготовка примеров упоминаний
        mentions_text = ""
        for i, mention in enumerate(mentions, 1):
            mentions_text += f"\n{i}. Строка {mention['line']}: ...{mention['context']}...\n"
        
        prompt = f"""Задача: Определить, какой КОНКРЕТНЫЙ человек упоминается под именем "{ambiguous_name}" в документе Product Review.

ПРОБЛЕМА: В документе несколько людей с именем/вариантом "{ambiguous_name}".

КАНДИДАТЫ:
{candidates_text}

ПРИМЕРЫ УПОМИНАНИЙ "{ambiguous_name}" В ДОКУМЕНТЕ:
{mentions_text}

AGENDA (зоны ответственности):
{agenda[:2000]}

ИНСТРУКЦИИ ПО АНАЛИЗУ:

1. Проанализируй контекст каждого упоминания "{ambiguous_name}"
2. Определи ключевые слова рядом с именем (например: "снэпшот", "schedule", "deploy")
3. Сопоставь ключевые слова с зонами ответственности кандидатов
4. Вычисли evidence_score для каждого кандидата:
   - +30 если контекст совпадает с зоной ответственности в Agenda
   - +20 если ключевые слова указывают на работу кандидата
   - +10 если имя упоминается в той же секции, что и задачи кандидата
   - -20 если контекст противоречит зоне ответственности

ПРАВИЛА РАЗРЕШЕНИЯ:

- "между снэпшотами" → тот, кто отвечает за снэпшоты
- "Schedule Section" → тот, кто отвечает за Schedule
- имя в заголовке секции ("### N. Задачи Владимира") → высокий приоритет
- "хотел бы выделить день" → личное высказывание, нужен контекст работы

ФОРМАТ ОТВЕТА (строго JSON):

{{
  "resolved_email": "email@route4me.com",
  "confidence": 0.85,
  "reasoning": [
    "Причина 1: контекст указывает на ...",
    "Причина 2: зона ответственности совпадает с ...",
    "Причина 3: ключевые слова '...' характерны для работы этого человека"
  ]
}}

Если уверенность < 50%, верни:
{{
  "resolved_email": null,
  "confidence": 0.30,
  "reasoning": ["Недостаточно контекста для однозначного определения"]
}}

Верни ТОЛЬКО JSON, без комментариев."""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Ты эксперт по разрешению неоднозначности имен в корпоративных документах. Анализируй контекст и зоны ответственности для точной атрибуции."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=1000,
                response_format={"type": "json_object"}
            )
            
            result_text = response.choices[0].message.content
            result = json.loads(result_text)
            
            resolved_email = result.get('resolved_email')
            confidence = result.get('confidence', 0)
            reasoning = result.get('reasoning', [])
            
            print(f"   [LLM] Уверенность: {confidence:.0%}", flush=True)
            for reason in reasoning[:3]:
                print(f"      - {reason}", flush=True)
            
            if resolved_email and confidence >= 0.5:
                return resolved_email
            else:
                return None
                
        except Exception as e:
            print(f"   [ERROR] Ошибка LLM API: {e}", flush=True)
            return None
    
    def find_files_to_process(self) -> List[Dict]:
        """Находит все файлы .md, которые нужно стандартизировать."""
        files_to_process = []
        
        for folder in sorted(self.base_dir.iterdir()):
            if not folder.is_dir():
                continue
            
            # Ищем .md файлы в папке
            md_files = list(folder.glob("*.md"))
            
            for md_file in md_files:
                # Пропускаем уже обработанные файлы (*_CLEAN.md)
                if "_CLEAN" in md_file.name:
                    continue
                
                # Проверяем, есть ли уже CLEAN версия
                clean_name = md_file.stem + "_CLEAN.md"
                clean_file = md_file.parent / clean_name
                
                file_info = {
                    'source': md_file,
                    'target': clean_file,
                    'folder': folder.name,
                    'size': md_file.stat().st_size,
                    'exists': clean_file.exists()
                }
                
                files_to_process.append(file_info)
        
        return files_to_process
    
    def log_progress(self, file_info: Dict, status: str, details: str = ""):
        """Логирование прогресса в JSONL."""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'file': str(file_info['source']),
            'folder': file_info['folder'],
            'status': status,
            'details': details
        }
        
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
    
    def estimate_tokens(self, text: str) -> int:
        """Примерная оценка количества токенов."""
        return len(text) // 3  # Грубая оценка: 1 токен ≈ 3 символа
    
    def clean_markdown_blocks(self, content: str) -> str:
        """
        Удаляет markdown code blocks (```markdown и ```), если LLM их добавил.
        """
        import re
        
        # Удаляем ```markdown в начале
        content = re.sub(r'^```markdown\s*\n', '', content, flags=re.MULTILINE)
        
        # Удаляем ``` в конце
        content = re.sub(r'\n```\s*$', '', content, flags=re.MULTILINE)
        
        # Удаляем любые оставшиеся ```markdown или ```
        content = content.replace('```markdown', '').replace('```', '')
        
        return content.strip()
    
    def fix_name_format(self, content: str) -> str:
        """
        Обрабатывает имена в тексте по правилам:
        
        1. РЯДОМ с email ВСЕГДА полное английское имя из базы:
           [Artur Moskalenko](mailto:arturm@route4me.com)
        
        2. В ТЕКСТЕ (БЕЗ email) используем русское первое имя В ПАДЕЖЕ:
           "Артур предложил..." (именительный)
           "Предложение Артура..." (родительный)
           "Артуром было сказано..." (творительный)
        
        Падеж сохраняется из оригинального текста!
        """
        import re
        
        if not self.name_to_email:
            return content
        
        # ШАГ 0: УДАЛЯЕМ ВСЕ НЕСУЩЕСТВУЮЩИЕ EMAIL (которые придумал LLM)
        # Паттерн: [любой текст](mailto:email)
        pattern_with_email = r'\[([^\]]+)\]\(mailto:([a-zA-Z0-9._%+-а-яёА-ЯЁ]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\)'
        
        def remove_fake_emails(match):
            current_name = match.group(1).strip()
            email = match.group(2).strip()
            
            # Проверяем: email есть в базе?
            if hasattr(self, 'email_to_full_name') and email in self.email_to_full_name:
                # Email реальный - оставляем
                return match.group(0)
            else:
                # Email выдуманный или не в базе - удаляем ссылку, оставляем текст
                print(f"   [FIX] Удален несуществующий email: {email} (оставлен текст: {current_name})", flush=True)
                return current_name
        
        content = re.sub(pattern_with_email, remove_fake_emails, content)
        
        # ШАГ 1: Исправляем конструкции С EMAIL
        # Паттерн: [любой текст](mailto:email)
        pattern_with_email = r'\[([^\]]+)\]\(mailto:([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\)'
        
        def fix_email_link(match):
            current_name = match.group(1).strip()
            email = match.group(2).strip()
            
            # Получаем правильное ПОЛНОЕ английское имя из базы
            if hasattr(self, 'email_to_full_name') and email in self.email_to_full_name:
                correct_full_name = self.email_to_full_name[email]
                return f'[{correct_full_name}](mailto:{email})'
            else:
                # Email не в базе - оставляем как есть
                print(f"   [WARN] Email '{email}' в ссылке не найден в базе", flush=True)
                return match.group(0)
        
        content = re.sub(pattern_with_email, fix_email_link, content)
        
        # ШАГ 2: Исправляем старый формат "Name (email)" -> "[Full Name](mailto:email)"
        pattern_old_format = r'(?<!\[)([A-ZА-ЯЁ][a-zA-Zа-яёА-ЯЁ]+(?:\s+[A-ZА-ЯЁ][a-zA-Zа-яёА-ЯЁ]+)*)\s*\(([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\)'
        
        def fix_old_format(match):
            name = match.group(1).strip()
            email = match.group(2).strip()
            
            # Получаем правильное полное имя из базы
            if hasattr(self, 'email_to_full_name') and email in self.email_to_full_name:
                correct_full_name = self.email_to_full_name[email]
                return f'[{correct_full_name}](mailto:{email})'
            else:
                # Если email не в базе, используем текущее имя
                return f'[{name}](mailto:{email})'
        
        content = re.sub(pattern_old_format, fix_old_format, content)
        
        # ШАГ 3: Обрабатываем имена БЕЗ email в тексте
        # Заменяем все упоминания на [Русское Имя](mailto:email)
        # Сортируем по длине (сначала длинные, чтобы не заменить часть слова)
        sorted_names = sorted(self.name_to_email.keys(), key=len, reverse=True)
        
        for name in sorted_names:
            email = self.name_to_email[name]
            
            # Определяем, какое имя использовать в ссылке
            display_name = name
            
            # Если это полное английское имя - используем его
            if hasattr(self, 'email_to_full_name') and name == self.email_to_full_name.get(email):
                display_name = name  # Используем полное английское имя
            # Если это полное русское имя - используем полное английское из базы
            elif ' ' in name and hasattr(self, 'email_to_ru_name') and name == self.email_to_ru_name.get(email):
                if hasattr(self, 'email_to_full_name'):
                    display_name = self.email_to_full_name.get(email, name)  # Полное английское
                else:
                    display_name = name
            # Если это только первое имя - используем его (русское или английское)
            else:
                display_name = name
            
            # Паттерн: имя НЕ внутри ссылки
            escaped_name = re.escape(name)
            # (?<!\[) - не после [
            # (?<![a-zA-Zа-яёА-ЯЁ]) - не после букв
            # (?!\]\(mailto:) - не перед ](mailto:
            # (?![a-zA-Zа-яёА-ЯЁ]) - не перед буквами
            pattern = r'(?<!\[)(?<![a-zA-Zа-яёА-ЯЁ])(' + escaped_name + r')(?!\]\(mailto:)(?![a-zA-Zа-яёА-ЯЁ])'
            
            def replace_name(match):
                matched_text = match.group(1)
                pos = match.start()
                
                # Проверяем контекст - не внутри ли уже ссылки
                before = content[max(0, pos-50):pos]
                after = content[match.end():min(len(content), match.end()+10)]
                
                # Если уже в ссылке - пропускаем
                if before.count('[') > before.count(']'):
                    return matched_text
                if after.startswith('](mailto:'):
                    return matched_text
                
                # Заменяем на ссылку с email, используя правильное имя для отображения
                return f'[{display_name}](mailto:{email})'
            
            content = re.sub(pattern, replace_name, content)
        
        return content
    
    def fix_decisions_section(self, content: str) -> str:
        """
        Исправляет формат имен в секции "Решения и План Действий".
        
        Преобразует:
        - ([Имя]) или ([Имя Фамилия]) → ([Имя Фамилия](mailto:email))
        - ([Команда]), ([Дизайнеры]) → (Команда), (Дизайнеры) - убираем скобки
        - ([Имя, Имя2]) → ([Имя](mailto:email), [Имя2](mailto:email2))
        """
        import re
        
        # Паттерн для поиска конструкций типа ([Текст])
        pattern = r'\(\[([^\]]+)\]\)'
        
        def replace_decision_name(match):
            text_in_brackets = match.group(1).strip()
            
            # Проверяем: это группа слов (Команда, Дизайнеры, Бэкенд)?
            non_person_keywords = [
                'Команда', 'Дизайнеры', 'Бэкенд', 'Фронтенд', 'QA', 'Team',
                'Designers', 'Backend', 'Frontend', 'Developers'
            ]
            
            # Если это комбинация (Команда/Дизайнеры)
            if '/' in text_in_brackets:
                parts = text_in_brackets.split('/')
                if all(any(kw in part for kw in non_person_keywords) for part in parts):
                    # Убираем квадратные скобки, оставляем только круглые
                    return f'({text_in_brackets})'
            
            # Если это просто ключевое слово
            if any(keyword in text_in_brackets for keyword in non_person_keywords):
                # Убираем квадратные скобки
                return f'({text_in_brackets})'
            
            # Если есть запятые - несколько человек
            if ',' in text_in_brackets:
                names = [n.strip() for n in text_in_brackets.split(',')]
                result_names = []
                
                for name in names:
                    # Проверяем: это ключевое слово?
                    if any(keyword in name for keyword in non_person_keywords):
                        # Это не человек - убираем квадратные скобки
                        result_names.append(name)
                    else:
                        # Ищем email для этого имени
                        email = self._find_email_for_name(name)
                        if email:
                            result_names.append(f'[{self.email_to_full_name.get(email, name)}](mailto:{email})')
                        else:
                            result_names.append(f'[{name}](mailto:UNKNOWN)')
                
                return f'({", ".join(result_names)})'
            
            # Одно имя
            email = self._find_email_for_name(text_in_brackets)
            if email:
                full_name = self.email_to_full_name.get(email, text_in_brackets)
                return f'([{full_name}](mailto:{email}))'
            else:
                # Имя не найдено
                return f'([{text_in_brackets}](mailto:UNKNOWN))'
        
        content = re.sub(pattern, replace_decision_name, content)
        
        return content
    
    def remove_team_links(self, content: str) -> str:
        """
        Удаляет ссылки для групповых слов (Команда, Дизайнеры и т.д.).
        [Команда](mailto:UNKNOWN) → Команда
        **[Команда]**: → **Команда**:
        """
        import re
        
        non_person_keywords = [
            'Команда', 'Дизайнеры', 'Бэкенд', 'Фронтенд', 'QA', 'Team',
            'Designers', 'Backend', 'Frontend', 'Developers', 'Команда/Дизайнеры'
        ]
        
        # Паттерн: [Ключевое слово](mailto:любой_email)
        for keyword in non_person_keywords:
            # Точное совпадение
            pattern = r'\[' + re.escape(keyword) + r'\]\(mailto:[^\)]+\)'
            content = re.sub(pattern, keyword, content)
            
            # С частичным совпадением (например, "Команда/Дизайнеры")
            pattern_partial = r'\[([^\]]*' + re.escape(keyword) + r'[^\]]*)\]\(mailto:[^\)]+\)'
            content = re.sub(pattern_partial, r'\1', content)
        
        return content
    
    def _find_email_for_name(self, name: str) -> Optional[str]:
        """
        Находит email для имени, учитывая различные варианты написания.
        """
        # Прямое совпадение
        if name in self.name_to_email:
            return self.name_to_email[name]
        
        # Поиск по вариантам из name_variant_to_emails
        if hasattr(self, 'name_variant_to_emails') and name in self.name_variant_to_emails:
            emails = self.name_variant_to_emails[name]
            if len(emails) == 1:
                return emails[0]
        
        # Поиск по частичному совпадению с полным именем
        for stored_name, email in self.name_to_email.items():
            if ' ' in stored_name:  # Полное имя
                parts = stored_name.split()
                if name in parts or name == stored_name:
                    return email
        
        return None
    
    def fix_placeholder_emails(self, content: str, source_file: str = "document") -> str:
        """
        Заменяет placeholder email (@example.com) на реальные из name_to_email.
        
        Также исправляет КРИТИЧЕСКУЮ ОШИБКУ LLM:
        [Максим](mailto:Андрей) → [Максим](mailto:UNKNOWN)
        
        Удаляет ссылки для групп людей (Team, Команда, и т.д.)
        
        Args:
            content: содержимое документа
            source_file: имя файла для логирования unattributed names
        """
        import re
        
        # ШАГ 0: ИСПРАВЛЕНИЕ КРИТИЧЕСКОЙ ОШИБКИ LLM
        # LLM использует ОДИН placeholder для ВСЕХ неизвестных имен!
        # [Максим](mailto:Андрей), [Саша](mailto:Андрей) - это ОШИБКА!
        
        pattern_link = r'\[([^\]]+)\]\(mailto:([^)]+)\)'
        
        def fix_wrong_placeholder(match):
            name_in_brackets = match.group(1).strip()
            email = match.group(2).strip()
            
            # Проверяем: email = известный реальный email?
            if hasattr(self, 'email_to_full_name') and email in self.email_to_full_name:
                # Это реальный email - оставляем
                return match.group(0)
            
            # Email не в базе - это placeholder
            # Проверяем: email совпадает с именем в скобках?
            # [Максим](mailto:Максим) - правильно
            # [Максим](mailto:Андрей) - ОШИБКА!
            
            # Нормализуем для сравнения (убираем падежи)
            name_normalized = name_in_brackets.split()[0]  # Берем первое слово
            email_normalized = email.split('@')[0] if '@' in email else email
            email_normalized = email_normalized.split()[0]  # Первое слово
            
            if name_normalized.lower() != email_normalized.lower():
                # ОШИБКА LLM! Email не совпадает с именем
                print(f"   [FIX] Исправлена ошибка LLM: [{name_in_brackets}](mailto:{email}) → [{name_in_brackets}](mailto:UNKNOWN)", flush=True)
                return f'[{name_in_brackets}](mailto:UNKNOWN)'
            
            # Placeholder корректный, но заменим на UNKNOWN для легкого поиска
            return f'[{name_in_brackets}](mailto:UNKNOWN)'
        
        content = re.sub(pattern_link, fix_wrong_placeholder, content)
        
        # ШАГ 1: Заменяем UNKNOWN на реальные email из базы (если можем найти)
        pattern_unknown = r'\[([^\]]+)\]\(mailto:UNKNOWN\)'
        
        def replace_unknown(match):
            name = match.group(1).strip()
            line_start = content[:match.start()].count('\n') + 1
            
            # Пробуем найти в name_to_email (имена из документа)
            if name in self.name_to_email:
                email = self.name_to_email[name]
                print(f"   [OK] Найден email для '{name}': {email}", flush=True)
                return f'[{name}](mailto:{email})'
            
            # Пробуем первое слово (для падежей)
            first_word = name.split()[0]
            if first_word in self.name_to_email:
                email = self.name_to_email[first_word]
                print(f"   [OK] Найден email для '{name}' (через '{first_word}'): {email}", flush=True)
                return f'[{name}](mailto:{email})'
            
            # НОВОЕ: Ищем напрямую в emails.csv по русскому первому имени ИЛИ фамилии
            if hasattr(self, 'email_to_ru_first'):
                # Проверяем алиасы для первого слова
                canonical_name = self.TRANSLITERATION_ALIASES.get(first_word, first_word)
                
                # ШАГ 1: Поиск по ПЕРВОМУ ИМЕНИ
                matching_emails = []
                for email, ru_first in self.email_to_ru_first.items():
                    if ru_first == canonical_name:
                        matching_emails.append(email)
                
                # ШАГ 2: Если не нашли по первому имени - ищем по ФАМИЛИИ
                if not matching_emails:
                    # Убираем падежи у фамилий: Ковтунову → Ковтунов
                    # Типичные окончания дательного падежа: -у, -ю
                    # Типичные окончания именительного: -ов, -ев, -ин, -ский, -цкий
                    
                    search_words = name.split()  # Все слова из имени
                    
                    for word in search_words:
                        # Убираем падежное окончание
                        normalized_word = word
                        if word.endswith('ому') or word.endswith('ему'):
                            normalized_word = word[:-3] + 'ий'  # Делевскому → Делевский
                        elif word.endswith('ову') or word.endswith('еву') or word.endswith('ину'):
                            normalized_word = word[:-1]  # Ковтунову → Ковтунов
                        elif word.endswith('ого') or word.endswith('его'):
                            normalized_word = word[:-3] + 'ий'  # Делевского → Делевский
                        elif word.endswith('ова') or word.endswith('ева') or word.endswith('ина'):
                            normalized_word = word[:-1]  # Ковтунова → Ковтунов
                        
                        # Ищем по всем вариантам в RU/UA Transcription
                        for email, ru_transcription in self.email_to_ru_name.items():
                            if normalized_word in ru_transcription or word in ru_transcription:
                                matching_emails.append(email)
                                break
                        
                        if matching_emails:
                            break
                
                if len(matching_emails) == 1:
                    email = matching_emails[0]
                    full_name = self.email_to_full_name[email]
                    print(f"   [OK] Найден email для '{name}' в базе emails.csv: {email}", flush=True)
                    return f'[{full_name}](mailto:{email})'
                elif len(matching_emails) > 1:
                    print(f"   [WARN] '{name}' → {len(matching_emails)} совпадений в базе, оставлен UNKNOWN", flush=True)
            
            # Не нашли - оставляем UNKNOWN и логируем с номером строки
            context_start = max(0, match.start() - 50)
            context_end = min(len(content), match.end() + 50)
            context = content[context_start:context_end].replace('\n', ' ')
            self.unattributed_names.append((name, source_file, line_start, context))
            return match.group(0)  # Оставляем UNKNOWN
        
        content = re.sub(pattern_unknown, replace_unknown, content)
        
        # ШАГ 2: Удаляем ссылки для групп
        # Список слов, которые НЕ являются именами людей
        non_person_words = {
            # Группы
            'team', 'команда', 'команду', 'команды', 'команде',
            'web devs', 'mob team', 'developers', 'девелоперы',
            'дизайнеры', 'designers', 'тестировщики', 'testers',
            'бэкенд', 'backend', 'фронтенд', 'frontend',
            'мобильщики', 'mobile team', 'qa', 'саппорт', 'support',
            # Роли/должности общие
            'ответственный', 'responsible', 'owner', 'lead',
            # Технические термины
            'api', 'ui', 'ux', 'url', 'http', 'https',
            'agenda', 'recording', 'passcode', 'questions',
        }
        
        if not self.name_to_email:
            return content
        
        # Паттерн: [Текст](mailto:something@example.com)
        pattern = r'\[([^\]]+)\]\(mailto:([^)]+@example\.com)\)'
        
        def replace_placeholder(match):
            name = match.group(1)
            
            # Проверяем, не является ли это группой или техническим термином
            name_lower = name.lower().strip()
            if name_lower in non_person_words:
                # Убираем ссылку, оставляем просто текст
                return name
            
            # Проверяем по частям слова (если "Web devs" и т.д.)
            for non_person in non_person_words:
                if non_person in name_lower:
                    return name
            
            # Ищем реальный email для этого имени
            # Проверяем прямое совпадение
            if name in self.name_to_email:
                real_email = self.name_to_email[name]
                return f'[{name}](mailto:{real_email})'
            
            # Проверяем по первому слову (имени)
            first_word = name.split()[0]
            if first_word in self.name_to_email:
                real_email = self.name_to_email[first_word]
                return f'[{name}](mailto:{real_email})'
            
            # Проверяем по полному совпадению в значениях name_to_email
            for full_name, email in self.name_to_email.items():
                if ' ' in full_name:  # Только полные имена
                    if name.lower() in full_name.lower() or full_name.lower() in name.lower():
                        return f'[{name}](mailto:{email})'
            
            # Если не нашли - оставляем как placeholder для People секции
            # НО только если это похоже на имя человека (начинается с большой буквы)
            if name and name[0].isupper() and len(name.split()) <= 3:
                return f'[{name}](mailto:{name})'
            else:
                # Убираем ссылку для остального
                return name
        
        content = re.sub(pattern, replace_placeholder, content)
        
        return content
    
    def process_single_topic_with_retry(self, topic: str, topic_num: int, total_topics: int, known_names: str, source_file: str = "document", max_retries: int = 3) -> Optional[str]:
        """
        Обрабатывает одну тему/чанк с retry механизмом при rate limit errors.
        Поддерживает разные типы чанков: секции, списки, параграфы.
        """
        import re
        from openai import RateLimitError
        
        # Восстанавливаем ### в начале (если было разбиение и это секция)
        if not topic.startswith('#') and not topic.startswith('|'):
            # Проверяем, начинается ли с номера (1. 2. и т.д.) - это может быть секция
            if re.match(r'^\d+\.\s+', topic):
                topic = '### ' + topic
            elif not topic.strip().startswith('|'):  # Не таблица
                # Это может быть параграф или список - оставляем как есть
                pass
        
        # Извлекаем название темы для вывода
        topic_title = topic.split('\n')[0][:80]
        
        print(f"\n   [TOPIC] Тема {topic_num}/{total_topics}: {topic_title}", flush=True)
        print(f"   [SIZE] Размер: {len(topic)} символов", flush=True)
        
        # Определяем тип чанка для выбора промпта
        is_table = topic.strip().startswith('|')
        is_section = topic.strip().startswith('###') or re.match(r'^\d+\.\s+', topic.strip())
        is_list_item = re.match(r'^\d+\.\s+', topic.strip()) and not topic.strip().startswith('###')
        
        if is_table:
            # Это уже обработано в process_table_row_chunk
            prompt_topic = f"""Задача: Стандартизировать строку таблицы.

**КРИТИЧЕСКИ ВАЖНО:**
- Сохрани ВСЕ данные из строки
- Сохрани ВСЕ колонки
- Сохрани ВСЕ URLs

{known_names}

**Строка таблицы:**
{topic}

Верни ТОЛЬКО стандартизированную строку таблицы."""
        elif is_section or is_list_item:
            # Секция или пункт списка
            prompt_topic = f"""Задача: Стандартизировать ОДНУ тему/секцию обсуждения из файла Product Review.

**КРИТИЧЕСКИ ВАЖНО:**
- Сохрани ВСЕ слова из темы
- Обработай ВСЮ информацию в теме
- НЕ создавай заголовок документа (он уже обработан)
- НЕ теряй НИ ОДНОГО слова, URL, таймстемпа, детали

{known_names}

**Правила стандартизации:**
{self.rules[2000:8000] if len(self.rules) > 8000 else self.rules}

**Тема для обработки:**
{topic}

**Инструкции:**
1. Примени стандартную структуру для темы:
   - ### [N]. [Название темы] (сохрани номер и название ИЗ ОРИГИНАЛА)
   - **Ответственный:** [Полное Имя Фамилия](mailto:email)
   - **Время обсуждения:** (если есть - СОХРАНИ ТОЧНО КАК В ОРИГИНАЛЕ)
   - #### Контекст / Цель
   - #### Ключевые моменты обсуждения и предложения команды
   - #### Ключевые тезисы, директивы и мнения Дэна
   - #### Решения и План Действий / Следующие шаги
   - #### Итоговое резюме по теме
   - ------

2. **КРИТИЧНО - ФОРМАТ ИМЕН:**
   - РЯДОМ с email: [Полное Имя Фамилия](mailto:email)
   - В тексте: [Русское Имя](mailto:email) (сохраняй падеж!)

3. **КРИТИЧНО:** НЕ ТЕРЯЙ НИ ОДНОГО СЛОВА - каждое слово из оригинала должно быть в результате!
4. **КРИТИЧНО:** Сохрани ВСЕ URLs и ссылки ПОЛНОСТЬЮ! https://... должны остаться без изменений!
5. Сохрани ВСЕ детали: таймстемпы, технические термины, JIRA тикеты, комментарии, метаданные
6. Сохрани ВСЕ строки из Action Plan, Summary, все пункты списков
7. В секции "Решения и План Действий" КАЖДОЕ имя должно быть [Имя Фамилия](mailto:email)
8. Слова "Команда", "Дизайнеры", "Бэкенд" - НЕ оборачивай в ссылки, пиши просто (Команда)
9. НЕ добавляй ```markdown или ``` code blocks

Верни ТОЛЬКО стандартизированную тему, чистый markdown без code blocks."""
        else:
            # Параграф или другой контент
            prompt_topic = f"""Задача: Стандартизировать контент из файла Product Review.

**КРИТИЧЕСКИ ВАЖНО:**
- Сохрани ВСЕ слова
- Сохрани ВСЕ URLs, ссылки, детали
- НЕ теряй НИ ОДНОГО символа

{known_names}

**Контент для обработки:**
{topic}

**Инструкции:**
1. Примени стандартизацию имен: [Имя Фамилия](mailto:email)
2. Сохрани ВСЕ URLs полностью
3. Сохрани ВСЕ тексты, детали, метаданные
4. НЕ добавляй ```markdown или ``` code blocks

Верни ТОЛЬКО стандартизированный контент, чистый markdown без code blocks."""

        for attempt in range(max_retries):
            try:
                print(f"   [API] Отправка запроса к GPT-4o-mini (попытка {attempt + 1}/{max_retries})...", flush=True)
                
                response = self.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "Ты эксперт по стандартизации документации встреч."},
                        {"role": "user", "content": prompt_topic}
                    ],
                    temperature=0.0,
                    max_tokens=4000
                )
                
                print(f"   [OK] Получен ответ от API", flush=True)
                
                topic_content = response.choices[0].message.content
                
                # Очистка от markdown code blocks
                topic_content = self.clean_markdown_blocks(topic_content)
                
                # Исправление формата имен
                topic_content = self.fix_name_format(topic_content)
                
                # НОВОЕ: Исправляем секцию "Решения и План Действий"
                topic_content = self.fix_decisions_section(topic_content)
                
                # НОВОЕ: Удаляем ссылки для "Команда", "Дизайнеры" и т.д.
                topic_content = self.remove_team_links(topic_content)
                
                # НОВОЕ: Заменяем placeholder @example.com на реальные email
                topic_content = self.fix_placeholder_emails(topic_content, source_file)
                
                return topic_content
                
            except RateLimitError as e:
                if attempt < max_retries - 1:
                    # Exponential backoff с jitter
                    delay = (2 ** attempt) + random.uniform(0, 1)
                    print(f"   [WARN] Rate limit достигнут, ожидание {delay:.1f}с перед повтором...", flush=True)
                    time.sleep(delay)
                else:
                    print(f"   [ERROR] Rate limit после {max_retries} попыток: {e}", flush=True)
                    return None
            except Exception as e:
                print(f"   [ERROR] Ошибка при обработке темы {topic_num}: {e}", flush=True)
                return None
        
        return None
    
    def extract_names_from_text(self, text: str):
        """
        Извлекает ВСЕ email из документа и получает данные о людях из emails.csv.
        
        Алгоритм:
        1. Находим все email в тексте
        2. Для каждого email берем данные из базы (emails.csv)
        3. НОВОЕ: Ищем имена БЕЗ email в тексте и матчим с emails.csv по уникальности
        4. Создаем mapping для всех вариантов имен (с падежами)
        """
        import re
        
        # Очищаем старые данные
        self.name_to_email = {}
        self.mentioned_names_no_email = set()
        
        # ШАГ 1: Ищем ВСЕ email в документе
        email_pattern = r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
        found_emails = set(re.findall(email_pattern, text))
        
        # Фильтруем @example.com (placeholder)
        found_emails = {e for e in found_emails if '@example.com' not in e.lower()}
        
        print(f"   [INFO] Найдено уникальных email в документе: {len(found_emails)}", flush=True)
        
        # ШАГ 2: Для каждого найденного email получаем данные из базы
        for email in found_emails:
            if not hasattr(self, 'email_to_full_name') or email not in self.email_to_full_name:
                print(f"   [WARN] Email '{email}' НЕ НАЙДЕН в базе emails.csv!", flush=True)
                continue
            
            full_name = self.email_to_full_name[email]
            ru_name = self.email_to_ru_name.get(email, '')
            ru_first = self.email_to_ru_first.get(email, '')
            
            self._add_name_mappings(full_name, ru_name, ru_first, email)
        
        # ШАГ 3: НОВОЕ! Ищем имена БЕЗ email в тексте и матчим с emails.csv
        if hasattr(self, 'email_to_full_name'):
            # Паттерны для поиска имен в тексте:
            # 1. Полные имена (First Last) - английские и русские
            # 2. Только первые имена
            # 3. В различных контекстах (Автор:, Ответ:, Owner:, и т.д.)
            
            mentioned_names = set()
            
            # ПАТТЕРН 1: Полные имена (First Last) - английские
            # "Dan Khasis", "Artur Moskalenko", "Igor Skrynkovskyy"
            full_name_pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b'
            full_names = re.findall(full_name_pattern, text)
            for name in full_names:
                # Проверяем, что это похоже на имя (2-3 слова, не технический термин)
                words = name.split()
                if 2 <= len(words) <= 3:
                    # Пропускаем технические термины
                    if name.lower() not in ['route optimization', 'route editor', 'route planner', 'route metrics']:
                        mentioned_names.add(name)
            
            # ПАТТЕРН 2: Полные имена (First Last) - русские
            # "Артур Москаленко", "Игорь Скрыньковский"
            full_name_ru_pattern = r'\b([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)+)\b'
            full_names_ru = re.findall(full_name_ru_pattern, text)
            for name in full_names_ru:
                words = name.split()
                if 2 <= len(words) <= 3:
                    mentioned_names.add(name)
            
            # ПАТТЕРН 3: Имена в контексте (Автор:, Ответ:, Owner:, и т.д.)
            context_patterns = [
                r'Автор:\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',  # Автор: Dan Khasis
                r'Ответ\s*\(([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\):',  # Ответ (Artur Moskalenko):
                r'Owner:\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',  # Owner: Dan Khasis
                r'\*\*([А-ЯЁа-яё]+):\*\*',  # **Имя:** (двоеточие внутри)
                r'\*\*([A-Za-z]+):\*\*',  # **Name:** (двоеточие внутри)
                r'\*\*([А-ЯЁ][а-яё]+)\*\*:',  # **Имя**: (двоеточие снаружи)
                r'\*\*([A-Z][a-z]+)\*\*:',  # **Name**: (двоеточие снаружи)
                r'Ответственный:\s*([А-ЯЁ][а-яё]+)',  # Ответственный: Имя
                r'Ответственный:\s*([A-Z][a-z]+)',  # Ответственный: Name
                r'\(([А-ЯЁ][а-яё]+)/',  # (Имя/
                r'\(([A-Z][a-z]+)/',  # (Name/
                r'-\s+([А-ЯЁ][а-яё]+)\s+\(',  # - Имя (
                r'с\s+\[([А-ЯЁа-яё]+)\]\(mailto:',  # с [Дэном](mailto:
                r'с\s+([А-ЯЁ][а-яё]+)\s',  # с Дэном
            ]
            
            for pattern in context_patterns:
                matches = re.findall(pattern, text)
                mentioned_names.update(matches)
            
            print(f"   [INFO] Найдено имен БЕЗ email в тексте: {len(mentioned_names)}", flush=True)
            
            # Для каждого имени пытаемся найти email в базе
            for name in mentioned_names:
                if name in self.name_to_email:
                    continue  # Уже есть из ШАГ 2
                
                matching_emails = []
                
                # ШАГ 1: Прямое совпадение с полным английским именем
                for email, full_name in self.email_to_full_name.items():
                    if name == full_name or name.lower() == full_name.lower():
                        matching_emails.append(email)
                
                # ШАГ 2: Прямое совпадение с полным русским именем
                if not matching_emails and hasattr(self, 'email_to_ru_name'):
                    for email, ru_name in self.email_to_ru_name.items():
                        if name == ru_name or name.lower() == ru_name.lower():
                            matching_emails.append(email)
                
                # ШАГ 3: Используем систему вариантов имен (для падежей и уменьшительных)
                if not matching_emails and hasattr(self, 'name_variant_to_emails'):
                    matching_emails = self.name_variant_to_emails.get(name, [])
                
                # ШАГ 4: Частичное совпадение (если имя содержит фамилию)
                if not matching_emails:
                    name_words = name.split()
                    if len(name_words) >= 2:
                        # Ищем по фамилии (последнее слово)
                        last_name = name_words[-1]
                        for email, full_name in self.email_to_full_name.items():
                            if last_name.lower() in full_name.lower() or full_name.lower().endswith(last_name.lower()):
                                # Проверяем, что первое имя тоже совпадает
                                first_name = name_words[0]
                                if full_name.lower().startswith(first_name.lower()):
                                    matching_emails.append(email)
                
                # Если РОВНО ОДНО совпадение - используем!
                if len(matching_emails) == 1:
                    email = matching_emails[0]
                    full_name = self.email_to_full_name[email]
                    ru_name = self.email_to_ru_name.get(email, '')
                    ru_first = self.email_to_ru_first.get(email, '')
                    
                    print(f"   [OK] '{name}' → уникальное совпадение → {email} ({full_name})", flush=True)
                    self._add_name_mappings(full_name, ru_name, ru_first, email)
                    
                    # ВАЖНО: Добавляем и оригинальное написание (как оно встречается в тексте)
                    self.name_to_email[name] = email
                    
                elif len(matching_emails) > 1:
                    emails_list = ', '.join([self.email_to_full_name.get(e, e) for e in matching_emails])
                    print(f"   [WARN] '{name}' → {len(matching_emails)} совпадений ({emails_list}), пропущено", flush=True)
                else:
                    # Не нашли - сохраняем для unattributed_names
                    self.mentioned_names_no_email.add(name)
        
        print(f"   [OK] Подготовлено {len(set(self.name_to_email.values()))} человек", flush=True)
        print(f"   [INFO] Всего вариантов имен (с падежами): {len(self.name_to_email)}", flush=True)
        
        if self.name_to_email:
            sample_emails = list(set(self.name_to_email.values()))[:3]
            for email in sample_emails:
                if email in self.email_to_full_name:
                    full = self.email_to_full_name[email]
                    ru = self.email_to_ru_first.get(email, '')
                    print(f"   [INFO] {email}: {full} ({ru})", flush=True)
    
    def _add_name_mappings(self, full_name: str, ru_name: str, ru_first: str, email: str):
        """
        Вспомогательная функция: добавляет все варианты имени (с падежами) в mapping.
        """
        # Сохраняем все варианты для этого email
        # 1. Полное английское имя -> email (для ссылок)
        self.name_to_email[full_name] = email
        
        # 2. Полное русское имя -> email (если есть)
        if ru_name:
            self.name_to_email[ru_name] = email
        
        # 3. Первое русское имя -> email (для использования в тексте)
        if ru_first:
            self.name_to_email[ru_first] = email
            
            # Добавляем склонения русского имени
            # Родительный падеж (кого? чего?)
            if ru_first.endswith('р'):  # Артур -> Артура
                self.name_to_email[ru_first + 'а'] = email
            elif ru_first.endswith('й'):  # Евгений -> Евгения
                self.name_to_email[ru_first[:-1] + 'я'] = email
            elif ru_first.endswith('м'):  # Максим -> Максима
                self.name_to_email[ru_first + 'а'] = email
            elif ru_first.endswith('н'):  # Семён -> Семёна
                self.name_to_email[ru_first + 'а'] = email
            elif ru_first.endswith('ь'):  # Игорь -> Игоря
                self.name_to_email[ru_first[:-1] + 'я'] = email
            
            # Творительный падеж (кем? чем?)
            if ru_first.endswith('р'):  # Артур -> Артуром
                self.name_to_email[ru_first + 'ом'] = email
            elif ru_first.endswith('й'):  # Евгений -> Евгением
                self.name_to_email[ru_first[:-1] + 'ем'] = email
            elif ru_first.endswith('м'):  # Максим -> Максимом
                self.name_to_email[ru_first + 'ом'] = email
            elif ru_first.endswith('н'):  # Семён -> Семёном
                self.name_to_email[ru_first + 'ом'] = email
            elif ru_first.endswith('ь'):  # Игорь -> Игорем
                self.name_to_email[ru_first[:-1] + 'ем'] = email
            
            # Дательный падеж (кому? чему?)
            if ru_first.endswith('р'):  # Артур -> Артуру
                self.name_to_email[ru_first + 'у'] = email
            elif ru_first.endswith('й'):  # Евгений -> Евгению
                self.name_to_email[ru_first[:-1] + 'ю'] = email
            elif ru_first.endswith('м'):  # Максим -> Максиму
                self.name_to_email[ru_first + 'у'] = email
            elif ru_first.endswith('н'):  # Семён -> Семёну
                self.name_to_email[ru_first + 'у'] = email
            elif ru_first.endswith('ь'):  # Игорь -> Игорю
                self.name_to_email[ru_first[:-1] + 'ю'] = email
    
    def generate_mentioned_section(self) -> str:
        """
        Генерирует раздел "## People" со ВСЕМИ упомянутыми людьми.
        Использует ТОЛЬКО русские имена (если есть), без дубликатов по email.
        Включает людей с известным email И с UNKNOWN.
        Исключает групповые слова (Команда, Дизайнеры).
        """
        # Словарь: email -> русское_имя
        people_dict = {}
        
        # Ключевые слова, которые НЕ являются именами людей
        non_person_keywords = [
            'Команда', 'Дизайнеры', 'Бэкенд', 'Фронтенд', 'QA', 'Team',
            'Designers', 'Backend', 'Frontend', 'Developers', 'Команда/Дизайнеры'
        ]
        
        # 1. Добавляем всех известных людей из name_to_email
        for email in set(self.name_to_email.values()):
            # Берем русское полное имя из базы
            ru_name = self.email_to_ru_name.get(email, None)
            
            # Если нет русского имени - берем английское
            if not ru_name:
                ru_name = self.email_to_full_name.get(email, None)
            
            if ru_name:
                people_dict[email] = ru_name
        
        # 2. Добавляем людей без email из mentioned_names_no_email
        for name in self.mentioned_names_no_email:
            # Пропускаем групповые слова
            if any(keyword in name for keyword in non_person_keywords):
                continue
            # Используем имя как ключ, чтобы не было дубликатов
            people_dict[f"UNKNOWN_{name}"] = name
        
        # 3. Добавляем людей из unattributed_names (с UNKNOWN)
        if hasattr(self, 'unattributed_names'):
            for item in self.unattributed_names:
                if len(item) >= 1:
                    name = item[0]  # Первый элемент - имя
                    # Пропускаем групповые слова
                    if any(keyword in name for keyword in non_person_keywords):
                        continue
                    # Используем имя как ключ
                    people_dict[f"UNKNOWN_{name}"] = name
        
        if not people_dict:
            return ""
        
        section = "\n\n## People\n\n"
        
        # Создаем список (email, имя) и сортируем по имени
        people_list = [(email, name) for email, name in people_dict.items()]
        people_list.sort(key=lambda x: x[1])
        
        # Форматируем как unordered list
        for email, name in people_list:
            # Если email начинается с UNKNOWN_ - это placeholder
            if email.startswith('UNKNOWN_'):
                section += f"- [{name}](mailto:UNKNOWN)\n"
            else:
                section += f"- [{name}](mailto:{email})\n"
        
        return section
    
    def save_unattributed_names(self, file_info: Dict):
        """
        Сохраняет список имен без найденных email в unattributed_names.md
        
        Формат: Name | Document | Line | Context
        """
        if not self.unattributed_names:
            return
        
        unattributed_file = self.base_dir.parent / 'unattributed_names.md'
        
        # Читаем существующий файл если есть
        existing_entries = set()
        if unattributed_file.exists():
            with open(unattributed_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('|') and not line.startswith('| Name'):
                        existing_entries.add(line.strip())
        
        # Добавляем новые записи
        new_entries = []
        for item in self.unattributed_names:
            if len(item) == 4:
                name, doc_path, line_num, context = item
            else:
                # Старый формат для обратной совместимости
                name, doc_path, context = item
                line_num = '?'
            
            # Укорачиваем путь (только имя файла)
            doc_name = Path(doc_path).name if isinstance(doc_path, (str, Path)) else doc_path
            
            entry = f"| {name} | {doc_name} | {line_num} | {context[:80]} |"
            if entry not in existing_entries:
                new_entries.append((name, doc_name, line_num, context))
        
        if not new_entries:
            return
        
        # Записываем файл
        mode = 'a' if unattributed_file.exists() else 'w'
        with open(unattributed_file, mode, encoding='utf-8') as f:
            if mode == 'w':
                f.write("# Unattributed Names\n\n")
                f.write("Имена, для которых не найден email в документе.\n\n")
                f.write("| Name | Document | Line | Context |\n")
                f.write("|------|----------|------|----------|\n")
            
            for name, doc_name, line_num, context in new_entries:
                # Обрезаем контекст до 80 символов
                context_short = context[:80].replace('\n', ' ').replace('|', '\\|')
                f.write(f"| {name} | {doc_name} | {line_num} | {context_short} |\n")
        
        print(f"   [INFO] Добавлено {len(new_entries)} неизвестных имен в unattributed_names.md", flush=True)
    
    def save_employees_database(self):
        """
        Сохраняет/обновляет централизованную базу сотрудников в employees.md
        """
        employees_file = self.base_dir.parent / 'employees.md'
        
        # Читаем существующий файл если есть
        existing_employees = {}
        if employees_file.exists():
            with open(employees_file, 'r', encoding='utf-8') as f:
                content = f.read()
                # Парсим существующие записи
                import re
                pattern = r'\[([^\]]+)\]\(mailto:([^)]+)\)'
                for match in re.finditer(pattern, content):
                    name = match.group(1)
                    email = match.group(2)
                    existing_employees[email] = name
        
        # Добавляем новых сотрудников
        updated = False
        for name, email in self.name_to_email.items():
            if ' ' not in name:  # Только полные имена
                continue
            
            if email not in existing_employees:
                existing_employees[email] = name
                updated = True
            elif len(name) > len(existing_employees[email]):
                # Обновляем на более полное имя
                existing_employees[email] = name
                updated = True
        
        # Добавляем людей без email
        for name in self.mentioned_names_no_email:
            placeholder_email = name.replace(' ', '_')
            if placeholder_email not in existing_employees:
                existing_employees[placeholder_email] = f"{name} # research email"
                updated = True
        
        if updated:
            # Сортируем по имени
            sorted_employees = sorted(existing_employees.items(), key=lambda x: x[1])
            
            # Записываем файл
            with open(employees_file, 'w', encoding='utf-8') as f:
                f.write("# Employees Database\n\n")
                f.write("Централизованная база всех сотрудников, упомянутых в Product Review документах.\n\n")
                f.write("## People\n\n")
                
                for email, name in sorted_employees:
                    if '# research email' in name:
                        # Это placeholder
                        clean_name = name.replace(' # research email', '')
                        f.write(f"- [{clean_name}](mailto:{clean_name}) # research email\n")
                    else:
                        f.write(f"- [{name}](mailto:{email})\n")
            
            print(f"   [INFO] Обновлен файл employees.md ({len(sorted_employees)} сотрудников)", flush=True)
        else:
            print(f"   [INFO] employees.md не изменился", flush=True)
    
    def get_known_names_list(self) -> str:
        """
        Возвращает форматированный список ВСЕХ людей из документа для передачи в промпт LLM.
        
        ВАЖНО: Показываем ВСЕХ, а не только первых 10, чтобы LLM знал полный список.
        """
        if not hasattr(self, 'email_to_full_name') or not self.email_to_full_name:
            return "Нет известных имен."
        
        names_list = "СПИСОК ВСЕХ ЛЮДЕЙ ИЗ ЭТОГО ДОКУМЕНТА (email = уникальный ID):\n"
        names_list += "=" * 70 + "\n\n"
        
        # Показываем ВСЕХ людей, чьи email есть в документе
        # (self.name_to_email уже содержит только тех, кто упомянут)
        emails_in_doc = set(self.name_to_email.values())
        
        for email in sorted(emails_in_doc):
            if email not in self.email_to_full_name:
                continue
                
            full_name = self.email_to_full_name[email]
            ru_name = self.email_to_ru_name.get(email, '')
            ru_first = self.email_to_ru_first.get(email, '')
            
            names_list += f"Email: {email}\n"
            names_list += f"  Рядом с email: [{full_name}](mailto:{email})\n"
            if ru_first:
                names_list += f"  В тексте: [{ru_first}](mailto:{email}) (+ падежи: {ru_first}а, {ru_first}у, {ru_first}ом)\n"
            names_list += "\n"
        
        names_list += "\n" + "=" * 70 + "\n"
        names_list += "КРИТИЧЕСКИЕ ПРАВИЛА - НАРУШЕНИЕ = СЕРЬЁЗНАЯ ОШИБКА!\n"
        names_list += "=" * 70 + "\n\n"
        
        names_list += "1. ⛔ ЗАПРЕЩЕНО ПРИДУМЫВАТЬ EMAIL!\n"
        names_list += "   - Используй ТОЛЬКО email из списка выше\n"
        names_list += "   - НИКОГДА не создавай новые email (типа evgeniy@route4me.com)\n"
        names_list += "   - Email в документе = email из списка выше\n"
        names_list += "   - Если имени нет в списке → используй [Имя](mailto:Имя)\n"
        names_list += "\n"
        
        names_list += "2. Email = УНИКАЛЬНЫЙ ID человека\n"
        names_list += "   - Один человек = один email навсегда\n"
        names_list += "   - Email встретился в документе → используй ЕГО из списка\n"
        names_list += "\n"
        
        names_list += "3. РЯДОМ с email (в ссылке) → полное английское имя:\n"
        names_list += "   ✓ ПРАВИЛЬНО: [Artur Moskalenko](mailto:arturm@route4me.com)\n"
        names_list += "   ✗ ОШИБКА: [Артур](mailto:arturm@route4me.com)\n"
        names_list += "   ✗ ОШИБКА: Artur Moskalenko (arturm@route4me.com)\n"
        names_list += "   ✗ ОШИБКА: [Artur Moskalenko](mailto:artur@route4me.com)  ← придуманный email!\n"
        names_list += "\n"
        
        names_list += "4. В ТЕКСТЕ (без email рядом) → только первое русское имя:\n"
        names_list += "   ✓ ПРАВИЛЬНО: '[Артур](mailto:arturm@route4me.com) предложил'\n"
        names_list += "   ✓ ПРАВИЛЬНО: 'Предложение [Артура](mailto:arturm@route4me.com)'\n"
        names_list += "   ✗ ОШИБКА: 'Артур Москаленко предложил'  ← не используй фамилию!\n"
        names_list += "   ✗ ОШИБКА: 'Артур предложил'  ← нет ссылки!\n"
        names_list += "\n"
        
        names_list += "5. СОХРАНЯЙ ПАДЕЖ из оригинала:\n"
        names_list += "   - 'Артур сказал' → '[Артур](mailto:...) сказал'\n"
        names_list += "   - 'Предложение Артура' → 'Предложение [Артура](mailto:...)'\n"
        names_list += "   - 'Артуром сделано' → '[Артуром](mailto:...) сделано'\n"
        names_list += "\n"
        
        names_list += "6. Специальные случаи:\n"
        names_list += "   - (Команда) → НЕ создавай ссылку, оставь просто '(Команда)'\n"
        names_list += "   - (Дизайнеры) → оставь '(Дизайнеры)' без ссылки\n"
        names_list += "   - (Бэкенд) → оставь '(Бэкенд)' без ссылки\n"
        names_list += "   - **Александр (дизайнер):** → '**[Александр](mailto:...) (дизайнер):**'\n"
        names_list += "   - ⛔ Если имени НЕТ в списке → [ИМЯ_КАК_В_ТЕКСТЕ](mailto:ИМЯ_КАК_В_ТЕКСТЕ)\n"
        names_list += "   - КРИТИЧНО: Email в placeholder = само имя! НЕ используй другие имена!\n"
        names_list += "     ✓ ПРАВИЛЬНО: [Максим](mailto:Максим), [Андрей](mailto:Андрей)\n"
        names_list += "     ✗ ОШИБКА: [Максим](mailto:Андрей) ← ВСЕ разные имена!\n"
        names_list += "\n"
        
        names_list += "7. ⛔ ПРОВЕРКА ПЕРЕД СОЗДАНИЕМ ССЫЛКИ:\n"
        names_list += "   a) Этот email ЕСТЬ в списке выше? → ДА → используй\n"
        names_list += "   b) Этот email ЕСТЬ в списке выше? → НЕТ → используй [Имя](mailto:Имя)\n"
        names_list += "   c) НИКОГДА не угадывай/не придумывай email!\n"
        
        return names_list
    
    def extract_text_content(self, content: str) -> str:
        """
        Извлекает текстовое содержимое из markdown для проверки сохранности.
        Удаляет форматирование, но оставляет слова.
        """
        import re
        
        # Удаляем markdown ссылки, оставляем только текст
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', content)
        
        # Удаляем заголовки #
        text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
        
        # Удаляем bold/italic
        text = re.sub(r'\*\*([^\*]+)\*\*', r'\1', text)
        text = re.sub(r'\*([^\*]+)\*', r'\1', text)
        
        # Удаляем разделители
        text = re.sub(r'^-+$', '', text, flags=re.MULTILINE)
        
        # Удаляем пустые строки
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        # Возвращаем нормализованный текст
        return ' '.join(lines).lower()
    
    def verify_content_preservation(self, original: str, standardized: str) -> Dict:
        """
        Проверяет, что весь контент из оригинала присутствует в стандартизированной версии.
        
        Использует несколько методов проверки:
        1. Длина текста (должна быть ≥ 80% от оригинала)
        2. Количество всех слов (не уникальных)
        3. Сохранность таймстемпов
        4. Сохранность URL и JIRA тикетов
        
        Returns:
            {
                'preserved': bool,
                'details': str,
                'checks': Dict
            }
        """
        import re
        
        print("\n[CHECK] Проверка сохранности контента...")
        
        checks = {}
        issues = []
        
        # CHECK 1: Длина текста
        orig_len = len(original)
        std_len = len(standardized)
        len_ratio = std_len / orig_len if orig_len > 0 else 0
        checks['length'] = {
            'original': orig_len,
            'standardized': std_len,
            'ratio': len_ratio,
            'passed': len_ratio >= 0.8
        }
        print(f"   [1] Длина: {orig_len} → {std_len} символов ({len_ratio:.1%})")
        if not checks['length']['passed']:
            issues.append(f"Потеряно {100-len_ratio*100:.1f}% текста по длине")
        
        # CHECK 2: Количество ВСЕХ слов (с повторениями)
        orig_words = re.findall(r'\b[а-яА-ЯёЁa-zA-Z]+\b', original)
        std_words = re.findall(r'\b[а-яА-ЯёЁa-zA-Z]+\b', standardized)
        
        # Убираем стандартные слова-заголовки, которые меняются при стандартизации
        standardization_words = {
            'action', 'plan', 'summary', 'context', 'discussion', 'decision', 'decisions',
            'next', 'steps', 'responsible', 'topic', 'goal', 'objective', 'owner',
            'контекст', 'цель', 'обсуждение', 'обсуждения', 'решение', 'решения',
            'действий', 'план', 'шаги', 'следующие', 'ответственный', 'тема',
            'ключевые', 'моменты', 'предложения', 'команды', 'тезисы', 'директивы',
            'мнения', 'итоговое', 'резюме', 'саммари'
        }
        
        # Фильтруем эти слова из подсчета
        orig_words_filtered = [w for w in orig_words if w.lower() not in standardization_words]
        std_words_filtered = [w for w in std_words if w.lower() not in standardization_words]
        
        words_ratio = len(std_words_filtered) / len(orig_words_filtered) if orig_words_filtered else 0
        checks['words'] = {
            'original': len(orig_words),
            'original_filtered': len(orig_words_filtered),
            'standardized': len(std_words),
            'standardized_filtered': len(std_words_filtered),
            'ratio': words_ratio,
            'passed': words_ratio >= 0.80  # Снижаем порог до 80%
        }
        print(f"   [2] Слова: {len(orig_words_filtered)} → {len(std_words_filtered)} значимых слов ({words_ratio:.1%})")
        if not checks['words']['passed']:
            issues.append(f"Потеряно {100-words_ratio*100:.1f}% значимых слов")
        
        # CHECK 3: Таймстемпы (КРИТИЧНО)
        orig_timestamps = set(re.findall(r'\b\d{1,2}:\d{2}(?::\d{2})?\b', original))
        std_timestamps = set(re.findall(r'\b\d{1,2}:\d{2}(?::\d{2})?\b', standardized))
        missing_timestamps = orig_timestamps - std_timestamps
        checks['timestamps'] = {
            'original': len(orig_timestamps),
            'standardized': len(std_timestamps),
            'missing': len(missing_timestamps),
            'passed': len(missing_timestamps) == 0
        }
        print(f"   [3] Таймстемпы: {len(orig_timestamps)} → {len(std_timestamps)} (пропущено: {len(missing_timestamps)})")
        if missing_timestamps:
            issues.append(f"Пропущены таймстемпы: {', '.join(list(missing_timestamps)[:5])}")
        
        # CHECK 4: URLs
        orig_urls = set(re.findall(r'https?://[^\s\)]+', original))
        std_urls = set(re.findall(r'https?://[^\s\)]+', standardized))
        missing_urls = orig_urls - std_urls
        checks['urls'] = {
            'original': len(orig_urls),
            'standardized': len(std_urls),
            'missing': len(missing_urls),
            'passed': len(missing_urls) == 0
        }
        print(f"   [4] URLs: {len(orig_urls)} → {len(std_urls)} (пропущено: {len(missing_urls)})")
        if missing_urls:
            issues.append(f"Пропущены {len(missing_urls)} URLs")
        
        # CHECK 5: JIRA тикеты
        orig_jira = set(re.findall(r'\b[A-Z]+-\d+\b', original))
        std_jira = set(re.findall(r'\b[A-Z]+-\d+\b', standardized))
        missing_jira = orig_jira - std_jira
        checks['jira'] = {
            'original': len(orig_jira),
            'standardized': len(std_jira),
            'missing': len(missing_jira),
            'passed': len(missing_jira) == 0
        }
        if orig_jira:
            print(f"   [5] JIRA тикеты: {len(orig_jira)} → {len(std_jira)} (пропущено: {len(missing_jira)})")
            if missing_jira:
                issues.append(f"Пропущены тикеты: {', '.join(missing_jira)}")
        
        # ОБЩИЙ РЕЗУЛЬТАТ
        all_passed = all(check['passed'] for check in checks.values())
        
        result = {
            'preserved': all_passed,
            'checks': checks,
            'issues': issues
        }
        
        if all_passed:
            print(f"   [OK] Все проверки пройдены!")
        else:
            print(f"   [WARNING] Обнаружены проблемы:")
            for issue in issues:
                print(f"      - {issue}")
        
        return result
    
    def standardize_file_full(self, file_info: Dict) -> bool:
        """
        Стандартизация файла целиком (если файл небольшой).
        ОТКЛЮЧЕН: Теперь всегда используем chunked mode.
        Возвращает True при успехе.
        """
        try:
            # Читаем исходный файл
            with open(file_info['source'], 'r', encoding='utf-8') as f:
                original_content = f.read()
            
            print(f"   [INFO] Full mode отключен, перенаправляем в chunked mode", flush=True)
            
            # Проверяем, является ли документ таблицей
            is_table_document = bool(re.search(r'\|[^\n]+\|\s*\n\s*\|[-\s:]+\|\s*\n\s*\|', original_content, re.MULTILINE))
            
            if is_table_document:
                # ТАБЛИЦЫ ОСТАВЛЯЕМ В ОРИГИНАЛЬНОМ ВИДЕ
                print(f"   [INFO] Документ - таблица, копируем без изменений", flush=True)
                
                # Просто копируем файл как есть
                with open(file_info['target'], 'w', encoding='utf-8') as f:
                    f.write(original_content)
                
                print(f"   [OK] Таблица скопирована без изменений: {file_info['target'].name}")
                self.log_progress(file_info, 'success_table_copy', 'Table copied as-is')
                return True
            else:
                # Обычные документы - перенаправляем в chunked mode
                print(f"   [INFO] Перенаправление в chunked mode...", flush=True)
                return self.standardize_file_chunked(file_info)
            
        except Exception as e:
            print(f"   [ERROR] Ошибка: {e}")
            self.log_progress(file_info, 'error', str(e))
            return False
    
    def extract_urls_with_context(self, text: str) -> List[Dict]:
        """
        Извлекает все URLs с окружающим контекстом (30 символов до и после).
        Возвращает список словарей: {'url': 'https://...', 'context_before': '...', 'context_after': '...'}
        """
        import re
        # Находим все URLs (включая markdown формат)
        # Паттерн для markdown: [текст](url) и просто url
        pattern = r'https?://[^\s\)\]]+(?:[^\s\)\]])*'
        
        urls_data = []
        for match in re.finditer(pattern, text):
            url = match.group(0)
            start = match.start()
            end = match.end()
            
            # Извлекаем контекст (30 символов до и после)
            context_before = text[max(0, start-30):start]
            context_after = text[end:min(len(text), end+30)]
            
            urls_data.append({
                'url': url,
                'context_before': context_before,
                'context_after': context_after,
                'position': start
            })
        
        return urls_data
    
    def restore_urls(self, processed_text: str, original_urls: List[Dict]) -> str:
        """
        Восстанавливает URLs в обработанном тексте, используя контекст для поиска места вставки.
        """
        import re
        
        if not original_urls:
            return processed_text
        
        result = processed_text
        
        for url_data in original_urls:
            url = url_data['url']
            context_before = url_data['context_before']
            context_after = url_data['context_after']
            
            # Проверяем, есть ли уже этот URL в тексте
            if url in result:
                continue
            
            # Ищем место по контексту
            # Убираем из контекста возможные URL для более точного поиска
            clean_context_before = re.sub(r'https?://[^\s\)\]]+', '', context_before)
            clean_context_after = re.sub(r'https?://[^\s\)\]]+', '', context_after)
            
            # Пробуем найти место для вставки
            # Вариант 1: ищем точное совпадение контекста
            search_pattern = re.escape(clean_context_before.strip()[-20:] if len(clean_context_before.strip()) > 20 else clean_context_before.strip())
            
            if search_pattern:
                matches = list(re.finditer(search_pattern, result))
                if matches:
                    # Берем первое совпадение и вставляем URL после него
                    insert_pos = matches[0].end()
                    # Проверяем, есть ли уже URL рядом
                    next_chars = result[insert_pos:insert_pos+50]
                    if not re.search(r'https?://', next_chars):
                        result = result[:insert_pos] + ' ' + url + result[insert_pos:]
        
        return result

    def detect_document_structure(self, content: str) -> Dict:
        """
        Умное определение структуры документа.
        
        Returns:
            {
                'type': 'table' | 'sections' | 'mixed' | 'list',
                'chunks': List[Dict] - список чанков с метаданными
            }
        """
        import re
        
        structure = {
            'type': 'unknown',
            'chunks': []
        }
        
        # Проверяем наличие таблиц (markdown таблицы)
        table_pattern = r'\|[^\n]+\|\n\|[-\s:]+\|\n'
        tables = list(re.finditer(table_pattern, content, re.MULTILINE))
        
        # Проверяем наличие секций с ### (все варианты)
        section_patterns = [
            r'\n###\s+\d+\.',  # ### 1.
            r'\n###\s+\d+\.\s',  # ### 1. с пробелом после
            r'\n###\s+[А-ЯЁA-Z]',  # ### Название (без номера)
        ]
        sections = []
        for pattern in section_patterns:
            matches = list(re.finditer(pattern, content))
            sections.extend(matches)
        # Убираем дубликаты
        seen = set()
        unique_sections = []
        for match in sections:
            if match.start() not in seen:
                seen.add(match.start())
                unique_sections.append(match)
        sections = unique_sections
        
        # Проверяем наличие нумерованных списков (1. 2. 3.)
        numbered_list_pattern = r'^\d+\.\s+[^\n]+'
        numbered_items = list(re.finditer(numbered_list_pattern, content, re.MULTILINE))
        
        print(f"   [STRUCT] Анализ структуры документа...", flush=True)
        print(f"   [STRUCT] Таблицы: {len(tables)}, Секции ###: {len(sections)}, Нумерованные списки: {len(numbered_items)}", flush=True)
        
        # Определяем тип документа
        # ПРИОРИТЕТ: Если есть и таблицы, и секции - выбираем по количеству
        # Но если секций намного больше - это документ с секциями, а не таблица
        # ВАЖНО: Если таблица начинается сразу после ### - это все равно таблица!
        # Проверяем, есть ли таблица в первых 1000 символах после ###
        has_table_after_header = False
        if sections:
            first_section_pos = sections[0].start()
            content_after_first_section = content[first_section_pos:first_section_pos+1000]
            has_table_after_header = bool(re.search(r'\|[^\n]+\|\s*\n\s*\|[-\s:]+\|', content_after_first_section, re.MULTILINE))
        
        if (len(tables) > 0 or has_table_after_header) and (len(tables) * 3 > len(sections) or len(sections) == 0 or has_table_after_header):
            # Документ с таблицами (как Tech_Leads_Chat)
            structure['type'] = 'table'
            print(f"   [STRUCT] Тип: ТАБЛИЦА (каждая строка = один чанк)", flush=True)
            
            # Разбиваем таблицы на строки
            # Находим ВСЕ таблицы в документе
            table_blocks = []
            
            # Если таблица начинается после ### - находим ее по-другому
            if has_table_after_header:
                # Ищем ВСЕ таблицы после ### заголовков
                for section_match in sections:
                    section_start = section_match.start()
                    # Ищем таблицу после этой секции
                    content_after = content[section_start:section_start+5000]  # Увеличиваем окно поиска
                    table_in_section = re.search(r'\|[^\n]+\|\s*\n\s*\|[-\s:]+\|', content_after, re.MULTILINE)
                    if table_in_section:
                        # Находим все строки таблицы
                        table_start_in_content = section_start + table_in_section.start()
                        # Ищем конец таблицы - следующая секция ### или конец файла
                        remaining = content[table_start_in_content:]
                        # Ищем следующую секцию ### (но не ту же самую)
                        next_section = re.search(r'\n###\s+[^\n]+\n', remaining)
                        if next_section:
                            # Проверяем, что это не та же секция
                            next_section_pos = table_start_in_content + next_section.start()
                            if next_section_pos > section_start + 100:  # Это другая секция
                                table_end_in_content = next_section_pos
                            else:
                                table_end_in_content = len(content)
                        else:
                            table_end_in_content = len(content)
                        
                        table_content = content[table_start_in_content:table_end_in_content]
                        # Проверяем, что это действительно таблица (есть строки данных)
                        if '|' in table_content and table_content.count('|') > 10:
                            table_blocks.append((table_start_in_content, table_end_in_content, table_content))
            
            # Обрабатываем обычные таблицы (найденные паттерном)
            for table_match in tables:
                table_start = table_match.start()
                # Ищем конец таблицы (пустая строка или начало новой секции)
                table_end = table_match.end()
                # Продолжаем искать строки таблицы до пустой строки или новой секции
                remaining_content = content[table_end:]
                next_table_match = re.search(r'\n\n|\n###|\n##', remaining_content)
                if next_table_match:
                    table_end = table_end + next_table_match.start()
                
                table_content = content[table_start:table_end]
                table_blocks.append((table_start, table_end, table_content))
            
            # Обрабатываем каждую таблицу
            for table_start, table_end, table_content in table_blocks:
                lines = table_content.split('\n')
                # Находим заголовок и разделитель
                header_line = None
                separator_line = None
                data_start_idx = 0
                
                for i, line in enumerate(lines):
                    if line.strip().startswith('|') and header_line is None:
                        header_line = line
                    elif line.strip().startswith('|') and ('---' in line or ':' in line):
                        separator_line = line
                        data_start_idx = i + 1
                        break
                
                if header_line and separator_line:
                    # Обрабатываем каждую строку данных
                    for i, line in enumerate(lines[data_start_idx:], start=data_start_idx):
                        if line.strip() and line.strip().startswith('|'):
                            chunk = {
                                'type': 'table_row',
                                'content': f"{header_line}\n{separator_line}\n{line}",
                                'row_number': len(structure['chunks']) + 1,
                                'original_line': line.strip(),
                                'table_context': table_content[:200]  # Контекст для лучшей обработки
                            }
                            structure['chunks'].append(chunk)
        
        elif len(sections) > 0:
            # Документ с секциями ###
            structure['type'] = 'sections'
            print(f"   [STRUCT] Тип: СЕКЦИИ (каждая секция ### = один чанк)", flush=True)
            
            # Разбиваем по секциям ### - ищем ВСЕ варианты:
            # - ### 1. Название
            # - ### Название (без номера)
            # - Ищем также в начале строки (без \n перед ###)
            section_patterns = [
                r'\n(###\s+\d+\.\s+[^\n]+)',  # ### 1. Название (с \n перед)
                r'^(###\s+\d+\.\s+[^\n]+)',  # ### 1. Название (в начале строки)
                r'\n(###\s+\d+\.\s*[^\n]+)',  # ### 1. Название (с возможным пробелом после точки)
                r'^(###\s+\d+\.\s*[^\n]+)',  # ### 1. Название (в начале, с пробелом)
                r'\n(###\s+[А-ЯЁA-Z][^\n]+)',  # ### Название (без номера, начинается с заглавной)
                r'^(###\s+[А-ЯЁA-Z][^\n]+)',  # ### Название (в начале, без номера)
            ]
            
            all_section_matches = []
            for pattern in section_patterns:
                matches = list(re.finditer(pattern, content))
                all_section_matches.extend(matches)
            
            # Сортируем по позиции в документе
            all_section_matches.sort(key=lambda m: m.start())
            
            # Убираем дубликаты (если один и тот же раздел найден разными паттернами)
            unique_matches = []
            seen_positions = set()
            for match in all_section_matches:
                pos = match.start()
                if pos not in seen_positions:
                    seen_positions.add(pos)
                    unique_matches.append(match)
            
            print(f"   [STRUCT] Найдено уникальных секций: {len(unique_matches)}", flush=True)
            
            for i, match in enumerate(unique_matches):
                section_start = match.start()
                # Конец секции = начало следующей или конец файла
                section_end = unique_matches[i + 1].start() if i + 1 < len(unique_matches) else len(content)
                
                section_content = content[section_start:section_end].strip()
                
                # Извлекаем заголовок секции
                title_match = re.match(r'###\s*(\d+\.\s*)?(.+)', match.group(1))
                title = title_match.group(2).strip() if title_match else match.group(1).strip()
                
                chunk = {
                    'type': 'section',
                    'content': section_content,
                    'section_number': i + 1,
                    'title': title
                }
                structure['chunks'].append(chunk)
        
        elif len(numbered_items) > 0:
            # Документ с нумерованным списком
            structure['type'] = 'list'
            print(f"   [STRUCT] Тип: НУМЕРОВАННЫЙ СПИСОК (каждый пункт = один чанк)", flush=True)
            
            # Разбиваем по пунктам
            for i, match in enumerate(numbered_items):
                item_start = match.start()
                # Конец пункта = начало следующего или конец файла
                next_match = numbered_items[i + 1] if i + 1 < len(numbered_items) else None
                item_end = next_match.start() if next_match else len(content)
                
                item_content = content[item_start:item_end].strip()
                
                chunk = {
                    'type': 'list_item',
                    'content': item_content,
                    'item_number': i + 1
                }
                structure['chunks'].append(chunk)
        
        else:
            # Смешанный или неизвестный формат - обрабатываем целиком или по параграфам
            structure['type'] = 'mixed'
            print(f"   [STRUCT] Тип: СМЕШАННЫЙ (обработка по параграфам)", flush=True)
            
            # Разбиваем по двойным переносам строк (параграфы)
            paragraphs = content.split('\n\n')
            for i, para in enumerate(paragraphs):
                if para.strip() and len(para.strip()) > 50:  # Только значимые параграфы
                    chunk = {
                        'type': 'paragraph',
                        'content': para.strip(),
                        'paragraph_number': i + 1
                    }
                    structure['chunks'].append(chunk)
        
        print(f"   [STRUCT] Найдено чанков для обработки: {len(structure['chunks'])}", flush=True)
        
        # Детальное логирование первых 5 чанков для отладки
        if structure['chunks']:
            print(f"   [STRUCT] Примеры найденных чанков:", flush=True)
            for i, chunk in enumerate(structure['chunks'][:5], 1):
                chunk_preview = chunk.get('content', chunk.get('original_line', ''))[:60]
                print(f"      {i}. Тип: {chunk.get('type', 'unknown')}, Превью: {chunk_preview}...", flush=True)
            if len(structure['chunks']) > 5:
                print(f"      ... и еще {len(structure['chunks']) - 5} чанков", flush=True)
        
        return structure
    
    def process_table_row_chunk(self, chunk: Dict, chunk_num: int, total_chunks: int, known_names: str, source_file: str = "document") -> Optional[str]:
        """
        Обрабатывает одну строку таблицы как отдельный чанк.
        """
        row_content = chunk['content']
        row_num = chunk.get('row_number', chunk_num)
        
        print(f"\n   [ROW] Строка таблицы {row_num}/{total_chunks}", flush=True)
        print(f"   [SIZE] Размер: {len(row_content)} символов", flush=True)
        
        prompt = f"""Задача: Стандартизировать ОДНУ строку таблицы из документа Product Review.

**КРИТИЧЕСКИ ВАЖНО:**
- Сохрани ВСЕ данные из строки таблицы
- Сохрани ВСЕ колонки
- Сохрани ВСЕ URLs, ссылки, тексты ТОЧНО как в оригинале
- НЕ теряй НИ ОДНОГО символа
- НЕ ЗАМЕНЯЙ реальные URLs на example.com или placeholder!

{known_names}

**Правила стандартизации:**
{self.rules[2000:8000] if len(self.rules) > 8000 else self.rules}

**Строка таблицы для обработки:**
{row_content}

**Инструкции:**
1. Сохрани формат таблицы (markdown) - заголовок, разделитель, строка данных
2. Примени стандартизацию имен: [Имя Фамилия](mailto:email) ТОЛЬКО для имен людей
3. **КРИТИЧНО:** Сохрани ВСЕ URLs полностью и ТОЧНО - https://route4me.atlassian.net/..., https://route4me.com/... и т.д.
   - НЕ ЗАМЕНЯЙ реальные ссылки!
   - НЕ УДАЛЯЙ ссылки!
   - Сохрани их ТОЧНО как в оригинале!
4. Сохрани ВСЕ тексты из всех колонок - каждое слово, каждую деталь
5. Сохрани ВСЕ таймстемпы (даты, время)
6. НЕ добавляй ```markdown или ``` code blocks
7. НЕ создавай новые секции или структуру - только стандартизируй строку таблицы

Верни ТОЛЬКО стандартизированную строку таблицы (заголовок + разделитель + строка данных), чистый markdown без code blocks."""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Ты эксперт по стандартизации документации встреч. Сохраняй ВСЕ данные без потерь."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
                max_tokens=2000
            )
            
            result = response.choices[0].message.content
            result = self.clean_markdown_blocks(result)
            result = self.fix_name_format(result)
            result = self.fix_placeholder_emails(result, source_file)
            
            return result
            
        except Exception as e:
            print(f"   [ERROR] Ошибка при обработке строки {row_num}: {e}", flush=True)
            return None

    def standardize_file_chunked(self, file_info: Dict) -> bool:
        """
        Стандартизация большого файла по частям.
        1. Сначала обрабатываем заголовок и Agenda
        2. Потом умно определяем структуру и обрабатываем чанки
        """
        try:
            # Читаем исходный файл
            with open(file_info['source'], 'r', encoding='utf-8') as f:
                original_content = f.read()
            
            print(f"   [FILE] Большой файл, используем chunked обработку", flush=True)
            
            # КРИТИЧНО: Проверяем, является ли документ таблицей
            is_table_doc = bool(re.search(r'\|[^\n]+\|\s*\n\s*\|[-\s:]+\|', original_content[:5000], re.MULTILINE))
            
            if is_table_doc:
                # ТАБЛИЦЫ ОСТАВЛЯЕМ В ОРИГИНАЛЬНОМ ВИДЕ
                print(f"   [INFO] Документ - таблица, копируем без изменений", flush=True)
                
                # Просто копируем файл как есть
                with open(file_info['target'], 'w', encoding='utf-8') as f:
                    f.write(original_content)
                
                print(f"   [OK] Таблица скопирована без изменений: {file_info['target'].name}")
                self.log_progress(file_info, 'success_table_copy', 'Table copied as-is')
                return True
            
            # КРИТИЧНО: Извлекаем ВСЕ URLs ДО обработки
            print(f"   [URLS] Извлечение всех URLs из оригинала...", flush=True)
            original_urls = self.extract_urls_with_context(original_content)
            print(f"   [OK] Найдено {len(original_urls)} URLs", flush=True)
            
            # Проверяем структуру документа - есть ли Agenda/Questions/Recording в оригинале
            has_agenda = bool(re.search(r'##\s+Agenda|^-\s+\[', original_content, re.MULTILINE))
            has_questions = bool(re.search(r'##\s+Questions|Questions\s*$', original_content, re.MULTILINE | re.IGNORECASE))
            has_recording = bool(re.search(r'Recording|recording|zoom\.us|drive\.google', original_content, re.IGNORECASE))
            has_passcode = bool(re.search(r'Passcode|passcode|Код доступа|код доступа', original_content, re.IGNORECASE))
            
            # CHUNK 1: Заголовок и Agenda
            print(f"\n   [CHUNK] CHUNK 1: Заголовок и Agenda", flush=True)
            print(f"   [API] Отправка запроса к GPT-4o-mini...", flush=True)
            
            # Формируем инструкции в зависимости от того, что есть в оригинале
            sections_instructions = []
            sections_instructions.append("# Заголовок (извлеки из оригинала)")
            
            if has_agenda:
                sections_instructions.append("## Agenda - ПЕРВЫМ после заголовка")
            if has_questions:
                sections_instructions.append("## Questions - после Agenda")
            if has_recording or has_passcode:
                sections_instructions.append("------")
                if has_recording:
                    sections_instructions.append("**Recording:** [ССЫЛКА ИЗ ОРИГИНАЛА - НЕ МЕНЯЙ!]")
                if has_passcode:
                    sections_instructions.append("**Passcode:** [КОД ИЗ ОРИГИНАЛА - НЕ МЕНЯЙ!]")
                sections_instructions.append("------")
            
            sections_text = "\n".join(f"   {i+1}. {s}" for i, s in enumerate(sections_instructions))
            
            prompt_header = f"""Задача: Стандартизировать ТОЛЬКО заголовок и Agenda файла Product Review.

**КРИТИЧЕСКИ ВАЖНО:**
- Сохрани ВСЕ слова из оригинала
- НЕ создавай секции, которых НЕТ в оригинале!
- НЕ обрабатывай темы обсуждения (только заголовок и Agenda)
- Сохрани ВСЕ URLs ТОЧНО как в оригинале - НЕ ЗАМЕНЯЙ на example.com!

**Правила стандартизации:**
{self.rules}

**Исходный файл:**
{original_content[:5000]}
...
(файл продолжается, но сейчас обрабатываем только заголовок и Agenda)

**КРИТИЧНО - ФОРМАТ ИМЕН (самое важное!):**

ЗАПРЕЩЕНО (это ОШИБКА):
- Gurgen Hakobyan (gurgen.hakobyan@route4me.com)
- Owner: Vladim Fedorov (email@example.com)
- Gurgen сказал...
- Владимир предложил...

ОБЯЗАТЕЛЬНО (только так!):
- [Gurgen Hakobyan](mailto:gurgen.hakobyan@route4me.com)
- Owner: [Vladimir Fedorov](mailto:vladimirfedorov@route4me.com)
- [Gurgen Hakobyan](mailto:gurgen.hakobyan@route4me.com) сказал...
- [Владимир Федоров](mailto:vladimirfedorov@route4me.com) предложил...

**Инструкции:**
1. ПОРЯДОК СЕКЦИЙ (строго - создавай ТОЛЬКО то, что есть в оригинале!):
{sections_text}

2. **ФОРМАТ ИМЕН:** КАЖДОЕ имя ОБЯЗАТЕЛЬНО [Имя Фамилия](mailto:email) - БЕЗ ИСКЛЮЧЕНИЙ!
3. **КРИТИЧНО:** НЕ ТЕРЯЙ НИ ОДНОГО СЛОВА из оригинала!
4. **КРИТИЧНО:** Сохрани ВСЕ URLs и ссылки ПОЛНОСТЬЮ И ТОЧНО! https://... ОБЯЗАТЕЛЬНЫ!
   - НЕ ЗАМЕНЯЙ реальные ссылки на example.com или placeholder!
   - ЕСЛИ в Agenda есть ссылки (Google Docs, GitHub, etc.) - сохрани их ВНУТРИ Agenda ТОЧНО!
   - Developer Memo: ссылка ДОЛЖНА остаться в Agenda ТОЧНО как в оригинале!
5. НЕ обрабатывай темы обсуждения
6. НЕ добавляй ```markdown или ``` code blocks
7. НЕ создавай секции Questions/Recording/Passcode, если их НЕТ в оригинале!

Верни ТОЛЬКО: Заголовок + (Agenda если есть) + (Questions если есть) + (Recording/Passcode если есть) + Separator, без code blocks."""

            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Ты эксперт по стандартизации документации встреч."},
                    {"role": "user", "content": prompt_header}
                ],
                temperature=0.0,  # Минимальная температура для точного следования инструкциям
                max_tokens=4000
            )
            
            print(f"   [OK] Получен ответ от API", flush=True)
            
            header_content = response.choices[0].message.content
            
            # Очистка от markdown code blocks
            header_content = self.clean_markdown_blocks(header_content)
            
            # КРИТИЧНО: Извлекаем имена и email из ВСЕГО оригинального документа СРАЗУ
            # чтобы знать всех участников до обработки тем
            print(f"   [NAMES] Извлечение ВСЕХ имен и email из ВСЕГО документа...", flush=True)
            self.extract_names_from_text(original_content)
            
            # НОВОЕ: Разрешаем неоднозначность имен через LLM
            print(f"\n   [DISAMB] Проверка неоднозначных имен (Владимир, Игорь, и т.д.)...", flush=True)
            
            # Извлекаем Agenda для анализа
            agenda_match = re.search(r'## Agenda\n(.*?)(?=\n##|$)', original_content, re.DOTALL)
            agenda_section = agenda_match.group(1) if agenda_match else ""
            
            disambiguations = self.resolve_name_disambiguation(original_content, agenda_section)
            
            # Применяем разрешенные имена к name_to_email
            if disambiguations:
                print(f"   [OK] Разрешено {len(disambiguations)} конфликтов имен", flush=True)
                for name, email in disambiguations.items():
                    # Обновляем mapping - теперь это имя однозначно указывает на конкретный email
                    self.name_to_email[name] = email
                    
                    # Добавляем все склонения для разрешенного имени
                    if hasattr(self, 'email_to_ru_first') and email in self.email_to_ru_first:
                        ru_first = self.email_to_ru_first[email]
                        full_name = self.email_to_full_name.get(email, '')
                        ru_name = self.email_to_ru_name.get(email, '')
                        self._add_name_mappings(full_name, ru_name, ru_first, email)

            
            # Исправление формата имен (ПОСЛЕ извлечения имен!)
            header_content = self.fix_name_format(header_content)
            
            # Заменяем placeholder @example.com на реальные email в header
            header_content = self.fix_placeholder_emails(header_content, str(file_info['source']))
            
            # КРИТИЧНО: Проверяем, что все URLs из оригинала сохранены в header
            header_urls = set(re.findall(r'https?://[^\s\)\]]+', header_content))
            original_urls_in_header_section = set()
            # Ищем URLs в первых 2000 символов оригинала (где обычно заголовок/Agenda)
            header_section_original = original_content[:2000]
            original_urls_in_header_section = set(re.findall(r'https?://[^\s\)\]]+', header_section_original))
            
            missing_urls = original_urls_in_header_section - header_urls
            if missing_urls:
                print(f"   [WARN] Пропущены URLs в заголовке: {missing_urls}", flush=True)
                # Восстанавливаем пропущенные URLs
                for url in missing_urls:
                    # Ищем контекст URL в оригинале
                    url_pos = header_section_original.find(url)
                    if url_pos > 0:
                        context_before = header_section_original[max(0, url_pos-30):url_pos]
                        # Пытаемся найти место для вставки в header_content
                        if context_before.strip() in header_content:
                            insert_pos = header_content.find(context_before.strip()) + len(context_before.strip())
                            header_content = header_content[:insert_pos] + ' ' + url + header_content[insert_pos:]
                            print(f"   [FIX] Восстановлен URL: {url[:50]}...", flush=True)
            
            # Получаем список известных имен для передачи в промпт тем
            known_names = self.get_known_names_list()
            
            # Сохраняем заголовок
            print(f"   [SAVE] Запись в файл...", flush=True)
            with open(file_info['target'], 'w', encoding='utf-8') as f:
                f.write(header_content)
                # Для таблиц не добавляем "Темы обсуждения"
                if not (is_table_doc and not (has_agenda or has_questions or has_recording)):
                    f.write("\n\n")
                    f.write("## Темы обсуждения\n\n")
                    f.write("------\n\n")
            
            print(f"   [OK] Заголовок и Agenda записаны в файл", flush=True)
            
            # CHUNK 2+: Умное определение структуры и обработка чанков
            print(f"\n   [CHUNK] CHUNK 2+: Анализ структуры документа", flush=True)
            
            # Определяем структуру документа
            doc_structure = self.detect_document_structure(original_content)
            
            # Находим начало контента после заголовка/Agenda
            # Ищем где заканчивается Agenda/Questions/Recording
            # ВАЖНО: Ищем ВСЕ возможные секции, включая "Summary по каждому топику"
            # ПРИОРИТЕТ: Ищем сначала секции с темами (###), потом другие маркеры
            content_start = 0
            
            # ШАГ 1: Ищем секции с ### (это основной контент)
            first_section_match = re.search(r'\n###\s+\d+\.', original_content)
            if first_section_match:
                content_start = first_section_match.start() + 1  # +1 чтобы включить \n
                print(f"   [STRUCT] Найдена первая секция ### на позиции {content_start}", flush=True)
            else:
                # ШАГ 2: Ищем другие маркеры
                content_start_patterns = [
                    r'## Summary по каждому топику',
                    r'## Summary',
                    r'## Темы обсуждения',
                    r'## Детальный Анализ',
                    r'\|[^\n]+\|',  # Начало таблицы
                ]
                
                for pattern in content_start_patterns:
                    match = re.search(pattern, original_content)
                    if match:
                        # Ищем начало предыдущей строки
                        content_start = original_content.rfind('\n', 0, match.start()) + 1
                        print(f"   [STRUCT] Найден маркер '{pattern}' на позиции {match.start()}, начало контента: {content_start}", flush=True)
                        break
            
            # Извлекаем контент для анализа структуры (после заголовка)
            # Если не нашли маркер - анализируем весь документ
            content_to_analyze = original_content[content_start:] if content_start > 0 else original_content
            
            print(f"   [STRUCT] Анализ контента с позиции {content_start} (длина: {len(content_to_analyze)} символов)", flush=True)
            
            # Дополнительная проверка: считаем количество секций ### в найденном контенте
            sections_in_content = len(list(re.finditer(r'\n###\s+\d+\.', content_to_analyze)))
            if sections_in_content > 0:
                print(f"   [STRUCT] В найденном контенте обнаружено {sections_in_content} секций с ###", flush=True)
            
            # Переопределяем структуру на основе контента после заголовка
            doc_structure = self.detect_document_structure(content_to_analyze)
            
            total_chunks = len(doc_structure['chunks'])
            print(f"   [STAT] Найдено чанков для обработки: {total_chunks} (тип: {doc_structure['type']})", flush=True)
            
            if total_chunks == 0:
                print(f"   [WARN] Чанки не найдены автоматически, пробуем альтернативные методы...", flush=True)
                
                # Альтернативный метод: ищем любые заголовки ### (даже без номера)
                alt_sections = list(re.finditer(r'\n###\s+', content_to_analyze))
                if alt_sections:
                    print(f"   [INFO] Найдено {len(alt_sections)} секций с ### (без номера)", flush=True)
                    # Разбиваем по этим секциям
                    for i, match in enumerate(alt_sections):
                        section_start = match.start()
                        section_end = alt_sections[i + 1].start() if i + 1 < len(alt_sections) else len(content_to_analyze)
                        section_content = content_to_analyze[section_start:section_end].strip()
                        
                        chunk = {
                            'type': 'section',
                            'content': section_content,
                            'section_number': i + 1
                        }
                        doc_structure['chunks'].append(chunk)
                    total_chunks = len(doc_structure['chunks'])
                    doc_structure['type'] = 'sections'
                    print(f"   [OK] Найдено {total_chunks} секций альтернативным методом", flush=True)
                else:
                    print(f"   [WARN] Альтернативные методы не помогли, обрабатываем весь контент как один чанк", flush=True)
                    # Fallback - обрабатываем весь контент
                    doc_structure['chunks'] = [{
                        'type': 'full_content',
                        'content': content_to_analyze,
                        'chunk_number': 1
                    }]
                    total_chunks = 1
            
            # ПАРАЛЛЕЛЬНАЯ ОБРАБОТКА ЧАНКОВ
            max_workers = 15
            print(f"   [INFO] Запуск параллельной обработки ({max_workers} потоков)...", flush=True)
            
            # Результаты обработки (номер_чанка -> контент)
            chunk_results = {}
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Создаем задачи для всех чанков
                future_to_chunk = {}
                
                for i, chunk in enumerate(doc_structure['chunks'], 1):
                    chunk['chunk_number'] = i
                    
                    if chunk['type'] == 'table_row':
                        future = executor.submit(
                            self.process_table_row_chunk,
                            chunk,
                            i,
                            total_chunks,
                            known_names,
                            str(file_info['source'])
                        )
                    else:
                        # Для секций, списков, параграфов используем стандартную обработку
                        future = executor.submit(
                            self.process_single_topic_with_retry,
                            chunk['content'],
                            i,
                            total_chunks,
                            known_names,
                            str(file_info['source'])
                        )
                    
                    future_to_chunk[future] = i
                
                # Собираем результаты по мере завершения
                for future in as_completed(future_to_chunk):
                    chunk_num = future_to_chunk[future]
                    try:
                        result = future.result()
                        if result:
                            chunk_results[chunk_num] = result
                            print(f"   [OK] Чанк {chunk_num}/{total_chunks} обработан", flush=True)
                        else:
                            print(f"   [ERROR] Не удалось обработать чанк {chunk_num}", flush=True)
                    except Exception as e:
                        print(f"   [ERROR] Исключение при обработке чанка {chunk_num}: {e}", flush=True)
            
            # Записываем чанки в правильном порядке
            print(f"\n   [SAVE] Запись чанков в файл в правильном порядке...", flush=True)
            
            # Для таблиц - собираем заголовок один раз
            if doc_structure['type'] == 'table' and doc_structure['chunks']:
                first_chunk = doc_structure['chunks'][0]
                if 'content' in first_chunk:
                    # Извлекаем заголовок и разделитель из первой строки
                    lines = first_chunk['content'].split('\n')
                    if len(lines) >= 2:
                        header = lines[0]
                        separator = lines[1]
                        with open(file_info['target'], 'a', encoding='utf-8') as f:
                            f.write(header + '\n')
                            f.write(separator + '\n')
            
            for i in range(1, total_chunks + 1):
                if i in chunk_results:
                    with open(file_info['target'], 'a', encoding='utf-8') as f:
                        result = chunk_results[i]
                        
                        # Для таблиц - убираем заголовок и разделитель (они уже записаны)
                        if doc_structure['type'] == 'table':
                            lines = result.split('\n')
                            if len(lines) >= 3:
                                # Пропускаем заголовок и разделитель, берем только строку данных
                                data_line = lines[2] if len(lines) > 2 else lines[-1]
                                f.write(data_line + '\n')
                            else:
                                f.write(result + '\n')
                        else:
                            f.write(result)
                            f.write("\n\n")
                    
                    print(f"   [OK] Чанк {i}/{total_chunks} записан", flush=True)
                else:
                    # КРИТИЧНО: Если чанк не обработан - сохраняем оригинальный контент!
                    print(f"   [WARN] Чанк {i} пропущен (не обработан), сохраняем оригинал как fallback", flush=True)
                    
                    if i <= len(doc_structure['chunks']):
                        original_chunk = doc_structure['chunks'][i - 1]
                        original_content = original_chunk.get('content', original_chunk.get('original_line', ''))
                        
                        # Сохраняем оригинал с пометкой
                        with open(file_info['target'], 'a', encoding='utf-8') as f:
                            f.write(f"\n<!-- ORIGINAL CHUNK {i} (не обработан) -->\n")
                            f.write(original_content)
                            f.write("\n\n")
                        
                        print(f"   [FALLBACK] Оригинальный контент чанка {i} сохранен", flush=True)
            
            print(f"\n   [STAT] Проверка сохранности контента...", flush=True)
            
            # Проверка сохранности контента для всего файла
            with open(file_info['target'], 'r', encoding='utf-8') as f:
                full_standardized = f.read()
            
            verification = self.verify_content_preservation(original_content, full_standardized)
            
            # КРИТИЧНО: Если потеряно > 20% контента - предупреждение
            if not verification['preserved']:
                print(f"   [WARNING] Обнаружена потеря контента!", flush=True)
                for issue in verification.get('issues', []):
                    print(f"      - {issue}", flush=True)
                
                # Проверяем количество чанков
                original_chunks_count = len(doc_structure['chunks'])
                processed_chunks_count = len(chunk_results)
                if processed_chunks_count < original_chunks_count:
                    print(f"   [ERROR] Обработано только {processed_chunks_count} из {original_chunks_count} чанков!", flush=True)
                    print(f"   [ERROR] Пропущено {original_chunks_count - processed_chunks_count} чанков!", flush=True)
            
            # КРИТИЧНО: Восстанавливаем URLs
            print(f"   [URLS] Восстановление URLs...", flush=True)
            full_standardized = self.restore_urls(full_standardized, original_urls)
            
            # Сохраняем файл с восстановленными URLs
            with open(file_info['target'], 'w', encoding='utf-8') as f:
                f.write(full_standardized)
            print(f"   [OK] URLs восстановлены", flush=True)
            
            # Добавляем раздел "Упомянуты" в конец файла
            mentioned_section = self.generate_mentioned_section()
            if mentioned_section:
                print(f"   [INFO] Добавление раздела 'Упомянуты' с {len(self.mentioned_names_no_email)} именами...", flush=True)
                with open(file_info['target'], 'a', encoding='utf-8') as f:
                    f.write(mentioned_section)
            
            # Сохраняем/обновляем employees.md
            self.save_employees_database()
            
            # Сохраняем неизвестные имена
            self.save_unattributed_names(file_info)
            
            print(f"   [OK] Сохранено: {file_info['target'].name}", flush=True)
            
            self.log_progress(file_info, 'success_chunked', f'Processed in {total_chunks + 1} chunks')
            
            return True
            
        except Exception as e:
            print(f"   [ERROR] Ошибка: {e}", flush=True)
            traceback.print_exc()
            self.log_progress(file_info, 'error', str(e))
            return False
    
    def process_all_files(self, skip_existing: bool = True, max_files: Optional[int] = None):
        """Обрабатывает все файлы в папке Product_Review_2025."""
        
        print("=" * 80)
        print("АВТОМАТИЧЕСКАЯ СТАНДАРТИЗАЦИЯ PRODUCT REVIEW")
        print("=" * 80)
        print()
        
        # Находим файлы
        files = self.find_files_to_process()
        
        if skip_existing:
            files = [f for f in files if not f['exists']]
        
        if max_files:
            files = files[:max_files]
        
        print(f"📋 Найдено файлов для обработки: {len(files)}")
        print()
        
        if not files:
            print("[OK] Нет файлов для обработки!")
            return
        
        # Показываем список
        for i, f in enumerate(files, 1):
            status = "[WARN]  СУЩЕСТВУЕТ" if f['exists'] else "🆕 NEW"
            print(f"{i:2d}. [{status}] {f['folder']:40s} | {f['source'].name}")
        
        print()
        input("Нажмите Enter для начала обработки...")
        print()
        
        # Обрабатываем
        success_count = 0
        error_count = 0
        
        for i, file_info in enumerate(files, 1):
            print(f"\n{'=' * 80}")
            print(f"[{i}/{len(files)}] Обработка: {file_info['folder']}")
            print(f"{'=' * 80}")
            print(f"📂 Файл: {file_info['source'].name}")
            
            # Определяем стратегию обработки - ПРОСТО ПО РАЗМЕРУ
            file_size_kb = file_info['size'] / 1024
            
            if file_size_kb < 50:  # Файлы < 50KB обрабатываем целиком
                print(f"   [INFO] Стратегия: Full mode (файл < 50KB)", flush=True)
                success = self.standardize_file_full(file_info)
            else:  # Большие файлы обрабатываем по частям
                print(f"   [INFO] Стратегия: Chunked mode (файл ≥ 50KB)", flush=True)
                success = self.standardize_file_chunked(file_info)
            
            if success:
                success_count += 1
            else:
                error_count += 1
            
            # Пауза между запросами (rate limiting)
            if i < len(files):
                time.sleep(2)
        
        # Итоговая статистика
        print()
        print("=" * 80)
        print("ЗАВЕРШЕНО")
        print("=" * 80)
        print(f"[OK] Успешно обработано: {success_count}")
        print(f"[ERROR] Ошибок: {error_count}")
        print(f"[STAT] Лог сохранен: {self.log_file}")
        print()


def main():
    import sys
    
    # Загружаем .env файл
    if DOTENV_AVAILABLE:
        load_dotenv()
        print("[OK] Загружены переменные из .env")
    
    # Получаем API ключ
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("[ERROR] OPENAI_API_KEY не найден!")
        print("Добавьте в файл .env: OPENAI_API_KEY='your-key-here'")
        print("Или установите: export OPENAI_API_KEY='your-key-here'")
        exit(1)
    
    # Пути
    base_dir = "/home/vadim/Projects/route4me.com/turboscribe/Product_Review_2025"
    rules_file = "/home/vadim/Projects/route4me.com/turboscribe/Product_Review_2025/STANDARDIZATION_RULES.md"
    
    # Создаем стандартизатор
    standardizer = ProductReviewStandardizer(api_key, base_dir, rules_file)
    
    # Режим работы
    test_mode = '--test' in sys.argv
    test_file = None
    
    # Проверяем аргументы командной строки
    for arg in sys.argv[1:]:
        if arg.startswith('--file='):
            test_file = arg.split('=', 1)[1]
    
    if test_mode:
        print("\n" + "=" * 80)
        print("ТЕСТОВЫЙ РЕЖИМ")
        print("=" * 80)
        
        # Если файл не указан, используем дефолтный
        if not test_file:
            test_file = "4. Product Review 29 May/4.Product_Review_29_May.md"
        
        test_path = Path(base_dir) / test_file
        if not test_path.exists():
            print(f"[ERROR] Файл не найден: {test_path}")
            exit(1)
        
        # Подготовка информации о файле
        output_path = test_path.parent / (test_path.stem + "_CLEAN.md")
        
        file_info = {
            'source': test_path,
            'target': output_path,
            'folder': test_path.parent.name,
            'size': test_path.stat().st_size,
            'exists': output_path.exists()
        }
        
        print(f"\n📂 Тестовый файл: {file_info['source'].name}")
        print(f"📁 Папка: {file_info['folder']}")
        print(f"[STAT] Размер: {file_info['size']} байт ({file_info['size']/1024:.1f} KB)")
        print(f"[INFO] Выходной файл: {file_info['target'].name}")
        
        if file_info['exists']:
            print(f"[WARN]  Выходной файл существует и будет перезаписан!")
        
        print("\n" + "=" * 80)
        
        # Определяем стратегию обработки - ПРОСТО ПО РАЗМЕРУ
        file_size_kb = file_info['size'] / 1024
        
        if file_size_kb < 50:
            print(f"[INFO] Стратегия: Full mode (файл < 50KB)")
            success = standardizer.standardize_file_full(file_info)
        else:
            print(f"[INFO] Стратегия: Chunked mode (файл ≥ 50KB)")
            success = standardizer.standardize_file_chunked(file_info)
        
        print("\n" + "=" * 80)
        if success:
            print("[OK] ТЕСТ ЗАВЕРШЕН УСПЕШНО!")
            print("=" * 80)
            print(f"\nРезультат сохранен: {file_info['target']}")
            print(f"\nПроверьте файл:")
            print(f"  head -100 '{file_info['target']}'")
            print(f"  wc -l '{file_info['target']}'")
        else:
            print("[ERROR] ТЕСТ ПРОВАЛЕН!")
            print("=" * 80)
            print(f"\nПроверьте лог: {standardizer.log_file}")
    else:
        # Обычный режим - обработка всех файлов
        # skip_existing=True - пропускаем файлы, у которых уже есть _CLEAN версия
        # max_files=None - обрабатываем все (можно установить, например, 5 для теста)
        standardizer.process_all_files(skip_existing=True, max_files=None)


if __name__ == "__main__":
    main()

