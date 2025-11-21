#!/usr/bin/env python3
"""
Собирает все email и имена из всех .md файлов в Product_Review_2025
и создает emails.csv
"""

import re
import csv
from pathlib import Path
from collections import defaultdict

def is_declined_form(name):
    """Проверяет, является ли имя склоненной формой."""
    # Русские имена в падежах:
    # Родительный: Артура, Евгения, Игоря
    # Творительный: Евгением, Владимиром, Артуром
    # Дательный: Евгению, Владимиру
    
    name_lower = name.lower()
    
    # Творительный падеж (кем? чем?) - окончания -ом/-ем/-ым для имен
    instrumental_endings = ['ием', 'ем', 'ом', 'ым', 'им']
    
    # Родительный падеж (кого? чего?) - окончания -а/-я
    genitive_endings = ['ура', 'има', 'ёма', 'ена', 'ана', 'она', 'ия', 'ья', 'ра']
    
    # Дательный падеж (кому? чему?) - окончания -у/-ю
    dative_endings = ['ию', 'ому', 'ему']
    
    all_endings = instrumental_endings + genitive_endings + dative_endings
    
    words = name.split()
    
    # Проверяем каждое слово
    for word in words:
        word_lower = word.lower()
        for ending in all_endings:
            if word_lower.endswith(ending) and len(word) > len(ending) + 2:
                # Исключаем некоторые нормальные слова
                if word_lower not in ['sasha', 'саша', 'roman', 'роман', 'artem', 'артем']:
                    return True
    
    return False

def get_russian_transcription(english_name):
    """Возвращает русскую/украинскую транскрипцию английского имени."""
    transcriptions = {
        'alexey': 'Алексей',
        'alex': 'Алекс',
        'alexander': 'Александр',
        'alexandr': 'Александр',
        'artur': 'Артур',
        'eugene': 'Евгений',
        'evgeny': 'Евгений',
        'vladimir': 'Владимир',
        'volodymyr': 'Володимир',
        'gurgen': 'Гурген',
        'davron': 'Даврон',
        'dan': 'Дэн',
        'daniel': 'Даниэль',
        'igor': 'Игорь',
        'oleksandr': 'Олександр',
        'oleksander': 'Олександр',
        'roman': 'Роман',
        'anton': 'Антон',
        'dmitry': 'Дмитрий',
        'dmitriy': 'Дмитрий',
        'serhii': 'Сергей',
        'sergey': 'Сергей',
        'maksym': 'Максим',
        'maxim': 'Максим',
        'yuriy': 'Юрий',
        'yuri': 'Юрий',
        'victor': 'Виктор',
        'gaspar': 'Гаспар',
        'oleg': 'Олег',
        'manar': 'Манар',
        'sasha': 'Саша',
        'olga': 'Ольга',
        'olha': 'Ольга',
        'klopov': 'Клопов',
        'artem': 'Артем',
        'semeyon': 'Семён',
        'semyon': 'Семён',
    }
    
    # Словарь для фамилий
    surname_transcriptions = {
        'moskalenko': 'Москаленко',
        'bondarenko': 'Бондаренко',
        'fedorov': 'Федоров',
        'afanasiev': 'Афанасьев',
        'gusentsov': 'Гузенцов',
        'kuznetsov': 'Гусенцов',
        'kovtunov': 'Ковтунов',
        'dylevskiy': 'Делевский',
        'khasis': 'Хасис',
        'usmonov': 'Усмонов',
        'ishchenko': 'Ищенко',
        'zhakhavets': 'Жахавец',
        'svetliy': 'Светлый',
        'svetly': 'Светлый',
        'smaliak': 'Смаляк',
        'lyubetsky': 'Любецкий',
        'hakobyan': 'Хакобян',
        'golovtsov': 'Головцов',
        'khavanskii': 'Хаванский',
        'zadyraka': 'Задыряка',
        'shulga': 'Шульга',
        'yasko': 'Ясько',
        'eross': 'Эросс',
        'kasainov': 'Касаинов',
        'silman': 'Сильман',
        'kurmanov': 'Курманов',
        'pravyk': 'Правик',
        'skulska': 'Скульска',
        'kozodoi': 'Козодой',
        'zyabko': 'Зябко',
        'zharskiy': 'Жарский',
        'skrynkovskyy': 'Скрыньковский',
    }
    
    words = english_name.split()
    result = []
    
    for word in words:
        word_lower = word.lower()
        if word_lower in transcriptions:
            result.append(transcriptions[word_lower])
        elif word_lower in surname_transcriptions:
            result.append(surname_transcriptions[word_lower])
        else:
            result.append(word)  # Оставляем как есть, если транскрипция неизвестна
    
    return ' '.join(result) if result else ''

def is_cyrillic(text):
    """Проверяет, содержит ли текст кириллицу."""
    return bool(re.search('[а-яА-ЯёЁіІїЇєЄ]', text))

def is_latin(text):
    """Проверяет, содержит ли текст латиницу."""
    return bool(re.search('[a-zA-Z]', text))

def choose_best_full_name(all_names):
    """Выбирает лучший вариант для Full Name (предпочтение английскому с фамилией)."""
    if not all_names:
        return None, []
    
    # Сортируем: сначала латиница с пробелом (полное имя), потом кириллица с пробелом, потом одиночные
    priority_names = []
    
    for name in all_names:
        has_space = ' ' in name
        is_latin_name = is_latin(name) and not is_cyrillic(name)
        is_cyrillic_name = is_cyrillic(name)
        words_count = len(name.split())
        
        # Приоритет: латиница с фамилией > кириллица с фамилией > латиница без > кириллица без
        if is_latin_name and has_space:
            priority = (0, -words_count, -len(name))
        elif is_cyrillic_name and has_space:
            priority = (1, -words_count, -len(name))
        elif is_latin_name:
            priority = (2, -len(name))
        else:
            priority = (3, -len(name))
        
        priority_names.append((priority, name))
    
    # Сортируем по приоритету
    priority_names.sort()
    
    full_name = priority_names[0][1]
    other_names = [name for _, name in priority_names[1:]]
    
    return full_name, other_names

def collect_emails_from_file(file_path):
    """Извлекает все [Name](mailto:email) из файла."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Паттерн: [Name](mailto:email) или [[Name]](mailto:email)
    pattern = r'\[+([^\]]+?)\]+\(mailto:([^)]+)\)'
    
    matches = re.findall(pattern, content)
    
    results = []
    for name, email in matches:
        name = name.strip()
        email = email.strip()
        
        # Очищаем имя от лишних символов
        name = name.replace('[', '').replace(']', '').strip()
        
        # Пропускаем пустые
        if not name or not email:
            continue
        
        # Пропускаем placeholder @example.com
        if '@example.com' in email.lower():
            continue
        
        # Пропускаем где email = имя (placeholder)
        if email == name or email.replace('_', ' ').lower() == name.lower():
            continue
        
        # Пропускаем технические термины
        technical = ['http', 'https', 'team', 'команда', 'api', 'url']
        if name.lower() in technical or email.lower() in technical:
            continue
        
        # Пропускаем склоненные формы
        if is_declined_form(name):
            continue
        
        results.append((name, email))
    
    return results

def main():
    base_dir = Path('/home/vadim/Projects/route4me.com/turboscribe/Product_Review_2025')
    
    # Словарь: email -> {names: set, files: set}
    email_data = defaultdict(lambda: {
        'names': set(),
        'files': set()
    })
    
    # Ищем все .md файлы
    md_files = list(base_dir.rglob('*.md'))
    
    print(f"[INFO] Найдено {len(md_files)} .md файлов")
    
    for md_file in md_files:
        if md_file.name == 'STANDARDIZATION_RULES.md':
            continue
        
        # Только имя файла
        file_name = md_file.name
        
        matches = collect_emails_from_file(md_file)
        
        for name, email in matches:
            email_data[email]['names'].add(name)
            email_data[email]['files'].add(file_name)
    
    print(f"[INFO] Найдено уникальных email: {len(email_data)}")
    
    # Создаем CSV
    output_file = base_dir.parent / 'emails.csv'
    
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        
        # Заголовок
        writer.writerow(['Email', 'Full Name', 'RU/UA Transcription from ENGLISH'])
        
        # Сортируем по email
        for email in sorted(email_data.keys()):
            data = email_data[email]
            
            # Все имена (фильтруем дубликаты)
            all_names_list = list(data['names'])
            
            if not all_names_list:
                continue
            
            # Выбираем лучший Full Name (предпочтение английскому)
            full_name, other_names_list = choose_best_full_name(all_names_list)
            
            # Русская транскрипция
            ru_transcription = ''
            
            # Если Full Name на английском, ищем русский вариант
            if full_name and is_latin(full_name) and not is_cyrillic(full_name):
                # Сначала ищем в other_names готовый русский вариант
                # Берем только полностью кириллические варианты (без латиницы)
                cyrillic_variants = [n for n in other_names_list if is_cyrillic(n) and not is_latin(n) and ' ' in n]
                if cyrillic_variants:
                    # Берем самый полный кириллический вариант
                    ru_transcription = max(cyrillic_variants, key=lambda x: len(x))
                else:
                    # Генерируем автоматически
                    ru_transcription = get_russian_transcription(full_name)
            
            # Если Full Name на русском, ищем английский вариант
            elif full_name and is_cyrillic(full_name):
                # Ищем в other_names английский вариант
                latin_variants = [n for n in other_names_list if is_latin(n) and not is_cyrillic(n) and ' ' in n]
                if latin_variants:
                    # Меняем местами: Full Name = английский, транскрипция = русский
                    ru_transcription = full_name
                    full_name = max(latin_variants, key=lambda x: len(x))
                    # Удаляем из other_names то, что стало full_name
                    other_names_list = [n for n in other_names_list if n != full_name and n != ru_transcription]
            
            writer.writerow([
                email,
                full_name,
                ru_transcription
            ])
    
    print(f"[OK] Создан файл: {output_file}")
    print(f"[OK] Всего email адресов: {len(email_data)}")
    
    # Статистика
    total_files = sum(len(data['files']) for data in email_data.values())
    print(f"[OK] Всего упоминаний email: {total_files}")

if __name__ == '__main__':
    main()

