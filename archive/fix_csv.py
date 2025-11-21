#!/usr/bin/env python3
"""
Скрипт для очистки CSV файла от дублированных URL
"""

import csv
import re

def clean_url(url):
    """
    Очищает URL от markdown ссылок
    Пример: 'https://example.com](https://example.com' -> 'https://example.com'
    """
    # Если есть '](', берем только часть до него
    if '](' in url:
        url = url.split('](')[0]
    return url.strip()

def fix_csv(input_file='recordings.csv', output_file='recordings_clean.csv'):
    """
    Очищает CSV файл и сохраняет в новый файл
    """
    rows = []
    
    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            cleaned_url = clean_url(row['URL'])
            rows.append({
                'Dir': row['Dir'],
                'URL': cleaned_url,
                'Password': row['Password']
            })
            print(f"Очищен URL: {row['URL'][:50]}... -> {cleaned_url[:50]}...")
    
    # Сохраняем очищенный файл
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['Dir', 'URL', 'Password'])
        writer.writeheader()
        writer.writerows(rows)
    
    print(f"\nОчищенный файл сохранен: {output_file}")
    print(f"Всего записей: {len(rows)}")

if __name__ == "__main__":
    fix_csv()

