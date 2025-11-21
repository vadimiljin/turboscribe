#!/usr/bin/env python3
"""
Скрипт для автоматического скачивания Zoom записей из recordings.csv
Использует Playwright для автоматизации браузера

Использование:
    python download_recordings.py              # Скачать все записи
    python download_recordings.py --test       # Тестовый режим: скачать только первую запись
    python download_recordings.py --test --index 5  # Скачать только 5-ую запись
"""

import csv
import os
import asyncio
import re
import argparse
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('download_recordings.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Таймауты (в миллисекундах)
TIMEOUT = 60000  # 60 секунд для загрузки страниц
DOWNLOAD_TIMEOUT = 300000  # 5 минут для скачивания файлов


def slugify(text: str) -> str:
    """
    Преобразует текст в slug (например, '40. Product Review 23 Oct' -> '40-product-review-23-oct')
    """
    # Извлекаем только имя директории (без пути)
    text = os.path.basename(text)
    
    # Приводим к нижнему регистру
    text = text.lower()
    
    # Заменяем пробелы и небуквенные символы на дефисы
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    
    # Убираем дефисы в начале и конце
    text = text.strip('-')
    
    return text


async def download_recording(playwright, url: str, password: str, output_dir: str):
    """
    Скачивает запись Zoom с указанного URL
    
    Args:
        playwright: Экземпляр Playwright
        url: URL записи Zoom
        password: Пароль для доступа
        output_dir: Директория для сохранения файлов
    """
    # ПРОВЕРКА: Выводим полный путь для контроля
    absolute_output_dir = os.path.abspath(output_dir)
    logger.info(f"=" * 80)
    logger.info(f"ДИРЕКТОРИЯ СОХРАНЕНИЯ: {absolute_output_dir}")
    logger.info(f"=" * 80)
    
    # Создаем директорию если не существует
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # Настраиваем браузер для скачивания файлов
    browser = await playwright.chromium.launch(
        headless=False,  # headless=False для отладки
        args=[
            '--disable-blink-features=AutomationControlled',  # Скрываем автоматизацию
        ]
    )
    
    # Создаем контекст с настройками реального браузера
    context = await browser.new_context(
        accept_downloads=True,
        user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        viewport={'width': 1920, 'height': 1080},
        locale='en-US',
        timezone_id='America/New_York'
    )
    page = await context.new_page()
    
    try:
        logger.info(f"Открываю URL: {url}")
        await page.goto(url, wait_until='domcontentloaded', timeout=TIMEOUT)
        
        # Даем время на редиректы и загрузку
        await asyncio.sleep(3)
        
        # Ждем появления поля для пароля (после редиректа)
        logger.info("Ожидаю поле для ввода пароля...")
        await page.wait_for_selector('input[type="password"], input[placeholder*="Passcode"], input[placeholder*="passcode"]', timeout=TIMEOUT)
        
        # Вводим пароль
        logger.info("Ввожу пароль...")
        password_input = page.locator('input[type="password"], input[placeholder*="Passcode"], input[placeholder*="passcode"]').first
        await password_input.fill(password)
        
        # Нажимаем кнопку "Watch Recording"
        logger.info("Нажимаю кнопку 'Watch Recording'...")
        watch_button = page.locator('button:has-text("Watch Recording"), button:has-text("Смотреть запись")').first
        await watch_button.click()
        
        # Ждем редиректа и загрузки страницы с записью
        logger.info("Ожидаю загрузки страницы с записью (после редиректов)...")
        await asyncio.sleep(5)  # Даем время на редиректы
        await page.wait_for_load_state('networkidle', timeout=TIMEOUT)
        
        # Обработка cookies (если появилось модальное окно)
        logger.info("Проверяю наличие cookie баннера...")
        try:
            # Ищем кнопку "Accept Cookies" или "ACCEPT COOKIES"
            accept_cookies_selectors = [
                'button:has-text("Accept Cookies")',
                'button:has-text("ACCEPT COOKIES")',
                'button:has-text("Accept All")',
                'button[id*="cookie"][id*="accept"]',
                'button[class*="cookie"][class*="accept"]'
            ]
            
            for selector in accept_cookies_selectors:
                try:
                    accept_button = page.locator(selector).first
                    if await accept_button.is_visible(timeout=3000):
                        logger.info(f"Найдена кнопка cookies: {selector}")
                        await accept_button.click()
                        logger.info("Cookies приняты")
                        await asyncio.sleep(2)
                        break
                except:
                    continue
        except Exception as e:
            logger.info(f"Cookie баннер не найден или уже принят: {e}")
        
        # Ждем появления ссылки "Download" (может быть "Download (3 files)" или просто "Download")
        logger.info("Ищу ссылку 'Download'...")
        
        # Даем дополнительное время на загрузку всех элементов
        await asyncio.sleep(3)
        
        # Пробуем разные варианты селекторов
        download_selectors = [
            'a:has-text("Download")',
            'button:has-text("Download")',
            'a:has-text("download")',  # lowercase
            'a:has-text("Скачать")',
            '[aria-label*="Download"]',
            '[title*="Download"]',
            'a[href*="download"]',
            '//a[contains(text(), "Download")]',
            '//button[contains(text(), "Download")]',
            # Более специфичные селекторы для Zoom
            'a.zm-btn',
            'button.zm-btn',
            'a[role="button"]',
        ]
        
        download_link = None
        found_selector = None
        
        for selector in download_selectors:
            try:
                locator = page.locator(selector)
                count = await locator.count()
                
                if count > 0:
                    logger.info(f"Найдено {count} элементов по селектору: {selector}")
                    
                    # Проверяем каждый найденный элемент
                    for i in range(count):
                        element = locator.nth(i)
                        text = await element.text_content() if await element.is_visible() else ""
                        logger.info(f"  Элемент {i}: '{text}'")
                        
                        # Ищем тот что содержит "Download" и видимый
                        if "download" in text.lower() and await element.is_visible():
                            download_link = element
                            found_selector = selector
                            logger.info(f"✓ Выбран элемент: '{text}'")
                            break
                    
                    if download_link:
                        break
            except Exception as e:
                logger.debug(f"Селектор {selector} не сработал: {e}")
                continue
        
        if not download_link:
            logger.error(f"Не найдена ссылка для скачивания на странице: {url}")
            logger.error(f"Текущий URL: {page.url}")
            
            # Делаем скриншот для отладки
            screenshot_path = os.path.join(output_dir, 'debug_screenshot.png')
            await page.screenshot(path=screenshot_path, full_page=True)
            logger.error(f"Скриншот сохранен: {screenshot_path}")
            
            # Сохраняем HTML для анализа
            html_path = os.path.join(output_dir, 'debug_page.html')
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(await page.content())
            logger.error(f"HTML сохранен: {html_path}")
            
            return False
        
        logger.info(f"✓ Найдена ссылка для скачивания (селектор: {found_selector})")
        
        # Zoom дает 3 отдельных файла: .vtt, .mp4 (высокое разрешение), .mp4 (низкое/аудио)
        logger.info("Начинаю скачивание (ожидаю 3 файла)...")
        
        # Создаем slug для переименования файлов
        slug = slugify(output_dir)
        logger.info(f"=" * 80)
        logger.info(f"SLUG ДЛЯ ФАЙЛОВ: {slug}")
        logger.info(f"ОЖИДАЕМЫЕ ИМЕНА ФАЙЛОВ:")
        logger.info(f"  1. {slug}-transcript.vtt")
        logger.info(f"  2. {slug}-video.mp4")
        logger.info(f"  3. {slug}-audio.mp4")
        logger.info(f"=" * 80)
        
        # Список для сбора всех загрузок
        downloads_list = []
        downloaded_files = []
        
        # Создаем обработчик для каждой загрузки
        async def handle_single_download(download):
            try:
                original_filename = download.suggested_filename
                logger.info(f"Получен файл от Zoom: {original_filename}")
                
                # Определяем новое имя на основе типа файла
                if original_filename.endswith('.vtt') or 'transcript' in original_filename.lower():
                    new_filename = f"{slug}-transcript.vtt"
                    file_type = "СУБТИТРЫ"
                elif 'x' in original_filename and original_filename.endswith('.mp4'):
                    # Файл с разрешением в имени (например, Recording_2560x1440.mp4) - это видео
                    new_filename = f"{slug}-video.mp4"
                    file_type = "ВИДЕО"
                elif original_filename.endswith('.mp4'):
                    # Файл без разрешения - это аудио
                    new_filename = f"{slug}-audio.mp4"
                    file_type = "АУДИО"
                else:
                    # Fallback
                    new_filename = f"{slug}-{original_filename}"
                    file_type = "НЕИЗВЕСТНЫЙ ТИП"
                
                filepath = os.path.join(output_dir, new_filename)
                absolute_filepath = os.path.abspath(filepath)
                
                logger.info(f"Тип файла: {file_type}")
                logger.info(f"Новое имя: {new_filename}")
                logger.info(f"ПОЛНЫЙ ПУТЬ: {absolute_filepath}")
                
                await download.save_as(filepath)
                downloaded_files.append(filepath)
                
                # Проверяем что файл действительно создан
                if os.path.exists(filepath):
                    file_size = os.path.getsize(filepath)
                    logger.info(f"✓ УСПЕШНО СОХРАНЕН: {new_filename} ({file_size:,} байт)")
                else:
                    logger.error(f"✗ ОШИБКА: Файл не найден после сохранения!")
                
                return filepath
            except Exception as e:
                logger.error(f"Ошибка при сохранении файла {original_filename}: {e}")
                return None
        
        # Запускаем клик и ожидаем все три загрузки
        logger.info("Подготавливаю ожидание загрузок...")
        
        # Кликаем на ссылку и собираем все загрузки
        logger.info("Кликаю на ссылку Download...")
        
        # Собираем загрузки по мере их появления
        downloads_collected = []
        
        async def collect_download(index):
            try:
                async with page.expect_download(timeout=DOWNLOAD_TIMEOUT) as download_info:
                    if index == 0:
                        # Первый раз кликаем на ссылку
                        await download_link.click()
                download = await download_info.value
                logger.info(f"Получена загрузка #{index+1}")
                return download
            except Exception as e:
                logger.error(f"Ошибка при ожидании загрузки #{index+1}: {e}")
                return None
        
        # Запускаем клик и параллельное ожидание трех загрузок
        logger.info("Ожидаю начала всех загрузок...")
        download_tasks = [collect_download(i) for i in range(3)]
        downloads = await asyncio.gather(*download_tasks, return_exceptions=True)
        
        # Фильтруем успешные загрузки
        valid_downloads = [d for d in downloads if d is not None and not isinstance(d, Exception)]
        logger.info(f"Получено загрузок: {len(valid_downloads)}/3")
        
        if not valid_downloads:
            logger.error("Не удалось получить ни одной загрузки")
            return False
        
        # Обрабатываем каждую загрузку
        handle_tasks = [handle_single_download(d) for d in valid_downloads]
        saved_results = await asyncio.gather(*handle_tasks, return_exceptions=True)
        successful = [r for r in saved_results if r is not None and not isinstance(r, Exception)]
        
        logger.info(f"✓ Успешно скачано файлов: {len(successful)}/{len(valid_downloads)}")
        
        if len(successful) > 0:
            return True
        else:
            logger.error("Не удалось сохранить ни одного файла")
            return False
        
    except PlaywrightTimeoutError as e:
        logger.error(f"Таймаут при обработке {url}: {e}")
        return False
    except Exception as e:
        logger.error(f"Ошибка при обработке {url}: {e}")
        return False
    finally:
        await browser.close()


async def process_all_recordings(csv_path: str, max_concurrent: int = 3, test_mode: bool = False, test_index: int = 0):
    """
    Обрабатывает все записи из CSV файла
    
    Args:
        csv_path: Путь к CSV файлу
        max_concurrent: Максимальное количество одновременных загрузок
        test_mode: Если True, обрабатывает только одну запись (для тестирования)
        test_index: Индекс записи для тестового режима (0-based)
    """
    recordings = []
    
    # Читаем CSV
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            # Очищаем URL от markdown ссылок (если есть '](', берем только часть до него)
            url = row['URL']
            if '](' in url:
                url = url.split('](')[0]
            
            recordings.append({
                'index': idx,
                'dir': row['Dir'].strip('"'),
                'url': url.strip(),
                'password': row['Password']
            })
    
    # Тестовый режим - обрабатываем только одну запись
    if test_mode:
        if test_index >= len(recordings):
            logger.error(f"Индекс {test_index} вне диапазона. Всего записей: {len(recordings)}")
            return
        
        test_recording = recordings[test_index]
        logger.info(f"╔═══════════════════════════════════════════════════════════════════════════╗")
        logger.info(f"║ ТЕСТОВЫЙ РЕЖИМ: Обработка только одной записи (#{test_index})                    ║")
        logger.info(f"╠═══════════════════════════════════════════════════════════════════════════╣")
        logger.info(f"║ Директория: {test_recording['dir']:<60} ║")
        logger.info(f"║ URL: {test_recording['url'][:60]:<60} ║")
        logger.info(f"╚═══════════════════════════════════════════════════════════════════════════╝")
        recordings = [test_recording]
    else:
        logger.info(f"Найдено записей для обработки: {len(recordings)}")
    
    async with async_playwright() as playwright:
        # Обрабатываем записи с ограничением параллелизма
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def process_with_semaphore(recording):
            async with semaphore:
                return await download_recording(
                    playwright,
                    recording['url'],
                    recording['password'],
                    recording['dir']
                )
        
        tasks = [process_with_semaphore(rec) for rec in recordings]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Статистика
        successful = sum(1 for r in results if r is True)
        failed = len(results) - successful
        
        logger.info(f"\n=== ИТОГИ ===")
        logger.info(f"Успешно: {successful}")
        logger.info(f"Ошибок: {failed}")
        logger.info(f"Всего: {len(recordings)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Скачивание Zoom записей из recordings.csv',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  python download_recordings.py              # Скачать все записи
  python download_recordings.py --test       # Тестовый режим: только первая запись
  python download_recordings.py --test --index 5  # Скачать только 5-ую запись (0-based)
        """
    )
    
    parser.add_argument('--test', action='store_true', 
                       help='Тестовый режим: скачать только одну запись')
    parser.add_argument('--index', type=int, default=0,
                       help='Индекс записи для тестового режима (по умолчанию: 0)')
    parser.add_argument('--csv', type=str, default='recordings.csv',
                       help='Путь к CSV файлу (по умолчанию: recordings.csv)')
    parser.add_argument('--concurrent', type=int, default=2,
                       help='Количество параллельных загрузок (по умолчанию: 2)')
    
    args = parser.parse_args()
    
    csv_file = args.csv
    
    if not os.path.exists(csv_file):
        logger.error(f"Файл {csv_file} не найден!")
        exit(1)
    
    # Запускаем обработку
    asyncio.run(process_all_recordings(
        csv_file, 
        max_concurrent=args.concurrent,
        test_mode=args.test,
        test_index=args.index
    ))

