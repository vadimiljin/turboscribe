#!/usr/bin/env python3
"""
Интерактивный отладочный скрипт для поиска селектора Download
Позволяет вручную протестировать разные селекторы на странице Zoom
"""

import asyncio
from playwright.async_api import async_playwright

async def debug_zoom_page():
    """
    Открывает страницу Zoom и позволяет интерактивно тестировать селекторы
    """
    # URL и пароль из первой записи
    url = "https://route4me.zoom.us/rec/share/fU6fsyDxbyAaIVaBEuU7mz5yaM1NkUZ2H_IOXNKuN6eXLvE-ON6-2XUerugaXEPj.hRwvJlpoZ9iylHmt"
    password = "L$&t@6hP"
    
    print("Инициализирую Playwright...")
    async with async_playwright() as playwright:
        print("Запускаю браузер...")
        browser = await playwright.chromium.launch(
            headless=False,
            args=['--disable-blink-features=AutomationControlled']
        )
        
        print("Создаю контекст...")
        context = await browser.new_context(
            accept_downloads=True,
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080}
        )
        
        print("Открываю страницу...")
        page = await context.new_page()
        
        print(f"Открываю: {url}")
        await page.goto(url, wait_until='domcontentloaded')
        await asyncio.sleep(3)
        
        print("Ищу поле пароля...")
        password_input = page.locator('input[type="password"]').first
        await password_input.fill(password)
        
        print("Нажимаю Watch Recording...")
        watch_button = page.locator('button:has-text("Watch Recording")').first
        await watch_button.click()
        
        print("Жду редиректов...")
        await asyncio.sleep(5)
        await page.wait_for_load_state('networkidle', timeout=60000)
        
        print(f"\nТекущий URL: {page.url}\n")
        
        # Проверяем cookies
        print("Проверяю cookie баннер...")
        try:
            cookies_button = page.locator('button:has-text("ACCEPT COOKIES")').first
            if await cookies_button.is_visible(timeout=3000):
                print("Нажимаю ACCEPT COOKIES...")
                await cookies_button.click()
                await asyncio.sleep(2)
        except:
            print("Cookie баннер не найден")
        
        await asyncio.sleep(3)
        
        # Тестируем разные селекторы
        print("\n" + "="*80)
        print("ПОИСК ССЫЛКИ DOWNLOAD")
        print("="*80)
        
        selectors = [
            'a:has-text("Download")',
            'button:has-text("Download")',
            'a[href*="download"]',
            '[aria-label*="Download"]',
            '[title*="Download"]',
            'a.zm-btn',
            'button.zm-btn',
            'a[role="button"]',
            '//a[contains(text(), "Download")]',
        ]
        
        for selector in selectors:
            try:
                locator = page.locator(selector)
                count = await locator.count()
                
                if count > 0:
                    print(f"\n✓ Селектор: {selector}")
                    print(f"  Найдено элементов: {count}")
                    
                    for i in range(count):
                        element = locator.nth(i)
                        is_visible = await element.is_visible()
                        text = await element.text_content() if is_visible else "[не видим]"
                        print(f"    [{i}] Видимый: {is_visible}, Текст: '{text}'")
                else:
                    print(f"✗ Селектор: {selector} - ничего не найдено")
            except Exception as e:
                print(f"✗ Селектор: {selector} - ошибка: {e}")
        
        print("\n" + "="*80)
        print("СОХРАНЕНИЕ ОТЛАДОЧНЫХ ФАЙЛОВ")
        print("="*80)
        
        # Сохраняем скриншот
        await page.screenshot(path='debug_zoom_screenshot.png', full_page=True)
        print("Скриншот: debug_zoom_screenshot.png")
        
        # Сохраняем HTML
        with open('debug_zoom_page.html', 'w', encoding='utf-8') as f:
            f.write(await page.content())
        print("HTML: debug_zoom_page.html")
        
        print("\n" + "="*80)
        print("БРАУЗЕР ОСТАЕТСЯ ОТКРЫТЫМ ДЛЯ ИНСПЕКЦИИ")
        print("Нажмите Enter для закрытия...")
        print("="*80)
        
        input()
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_zoom_page())

