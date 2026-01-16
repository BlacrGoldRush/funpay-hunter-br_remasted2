import os
import logging
import requests
import re
from flask import Flask
from bs4 import BeautifulSoup
from datetime import datetime
import threading
import time
import json

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Конфигурация Telegram
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '').strip()

# Глобальные переменные
found_items = {}
monitoring_active = False
monitoring_thread = None

def send_telegram_message(text):
    """Отправка сообщения в Telegram через API напрямую"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("⚠️ Telegram не настроен")
        return False
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': text,
            'parse_mode': 'HTML',
            'disable_web_page_preview': False
        }
        
        response = requests.post(url, json=payload, timeout=10)
        result = response.json()
        
        if response.status_code == 200 and result.get('ok'):
            logger.info(f"📨 Сообщение отправлено в Telegram")
            return True
        else:
            logger.error(f"❌ Ошибка Telegram API: {result.get('description', 'Unknown error')}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка отправки в Telegram: {e}")
        return False

def test_telegram_connection():
    """Тест подключения к Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe"
        response = requests.get(url, timeout=5)
        result = response.json()
        
        if response.status_code == 200 and result.get('ok'):
            logger.info(f"✅ Telegram бот доступен: @{result['result'].get('username')}")
            return True
        else:
            logger.error(f"❌ Ошибка Telegram API: {result.get('description', 'Unknown error')}")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к Telegram: {e}")
        return False

def fast_parse_funpay():
    """Быстрый парсинг"""
    try:
        url = "https://funpay.com/chips/186/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        }
        
        logger.info("⚡ Быстрый парсинг...")
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            logger.error(f"❌ HTTP {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Ищем онлайн карточки
        cards = soup.find_all('a', class_='tc-item', attrs={'data-online': '1'})
        logger.info(f"📦 Найдено онлайн карточек: {len(cards)}")
        
        items = []
        
        # Обрабатываем первые 15
        for card in cards[:15]:
            try:
                # Сервер
                server_elem = card.find('div', class_='tc-server')
                server = server_elem.get_text(strip=True) if server_elem else "Неизвестен"
                
                # Продавец
                seller_elem = card.find('div', class_='media-user-name')
                seller = seller_elem.get_text(strip=True) if seller_elem else "Неизвестен"
                
                # Цена
                price_elem = card.find('div', class_='tc-price')
                if not price_elem:
                    continue
                
                price_text = price_elem.get_text(strip=True)
                price_match = re.search(r'([\d,.]+)', price_text.replace(' ', ''))
                if not price_match:
                    continue
                
                price_str = price_match.group(1).replace(',', '.')
                try:
                    price = float(price_str)
                except:
                    continue
                
                if price < 10 or price > 50000:
                    continue
                
                # Ссылка
                href = card.get('href', '')
                link = f"https://funpay.com{href}" if href.startswith('/') else href
                
                # ID
                item_id = f"{server}_{seller}_{price}"
                
                items.append({
                    'id': item_id,
                    'title': f"Black Russia | {server}",
                    'price': price,
                    'link': link,
                    'server': server,
                    'seller': seller
                })
                
            except Exception as e:
                logger.debug(f"Ошибка обработки карточки: {e}")
                continue
        
        logger.info(f"✅ Найдено товаров: {len(items)}")
        return items
        
    except requests.exceptions.Timeout:
        logger.error("⏱️ Таймаут запроса")
        return []
    except Exception as e:
        logger.error(f"💥 Ошибка: {e}")
        return []

def check_new_items():
    """Проверка новых товаров"""
    global found_items
    
    if not monitoring_active:
        return
    
    logger.info("🔍 Проверка...")
    
    items = fast_parse_funpay()
    
    for item in items:
        item_id = item['id']
        if item_id not in found_items:
            found_items[item_id] = item
            
            # Формируем и отправляем сообщение
            message = (
                f"🎮 <b>НОВОЕ ПРЕДЛОЖЕНИЕ BLACK RUSSIA</b>\n\n"
                f"📦 <b>Сервер:</b> {item['server']}\n"
                f"👤 <b>Продавец:</b> {item['seller']}\n"
                f"💰 <b>Цена:</b> {item['price']} руб.\n"
                f"🟢 <b>Статус:</b> Продавец онлайн\n"
                f"🔗 <a href='{item['link']}'>Купить на FunPay</a>\n\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}"
            )
            send_telegram_message(message)
    
    logger.info(f"📊 Всего товаров в памяти: {len(found_items)}")

def monitoring_loop():
    """Цикл мониторинга"""
    global monitoring_active
    
    logger.info("🔄 Мониторинг запущен")
    
    while monitoring_active:
        try:
            check_new_items()
            # Ждем 60 секунд между проверками
            for i in range(60):
                if not monitoring_active:
                    break
                time.sleep(1)
        except Exception as e:
            logger.error(f"❌ Ошибка мониторинга: {e}")
            time.sleep(30)

# ==================== FLASK ROUTES ====================

@app.route('/')
def index():
    telegram_status = test_telegram_connection()
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>FunPay Hunter</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
            .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            .btn {{ display: inline-block; padding: 12px 24px; margin: 8px; color: white; text-decoration: none; border-radius: 5px; font-weight: bold; }}
            .btn-green {{ background: #28a745; }}
            .btn-blue {{ background: #007bff; }}
            .btn-red {{ background: #dc3545; }}
            .btn-orange {{ background: #fd7e14; }}
            .status {{ padding: 15px; border-radius: 5px; margin: 15px 0; }}
            .status-ok {{ background: #d4edda; border: 1px solid #c3e6cb; color: #155724; }}
            .status-error {{ background: #f8d7da; border: 1px solid #f5c6cb; color: #721c24; }}
            h1 {{ color: #333; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 FunPay Hunter для Black Russia</h1>
            
            <div class="status {'status-ok' if telegram_status else 'status-error'}">
                <h3>Telegram статус: {'✅ РАБОТАЕТ' if telegram_status else '❌ ОШИБКА'}</h3>
                <p>{'Бот готов к отправке сообщений' if telegram_status else 'Проверьте TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID в Render'}</p>
            </div>
            
            <div style="margin: 20px 0;">
                <p><strong>Мониторинг:</strong> {'🟢 АКТИВЕН' if monitoring_active else '🔴 ОСТАНОВЛЕН'}</p>
                <p><strong>Найдено товаров:</strong> {len(found_items)}</p>
                <p><strong>Время сервера:</strong> {datetime.now().strftime("%H:%M:%S")}</p>
            </div>
            
            <div>
                <a href="/test" class="btn btn-blue">🔍 Тест парсинга</a>
                <a href="/telegram_test" class="btn btn-orange">🤖 Тест Telegram</a>
                <a href="/start_monitor" class="btn btn-green">▶️ Запустить мониторинг</a>
                <a href="/stop_monitor" class="btn btn-red">⏹️ Остановить мониторинг</a>
            </div>
            
            <div style="margin-top: 30px; padding: 20px; background: #f8f9fa; border-radius: 5px;">
                <h3>📋 Быстрая проверка:</h3>
                <ol>
                    <li>Нажмите "Тест парсинга" - должен показать товары</li>
                    <li>Нажмите "Тест Telegram" - получите сообщение в Telegram</li>
                    <li>Запустите мониторинг - бот начнет отправлять уведомления</li>
                </ol>
            </div>
        </div>
    </body>
    </html>
    '''

@app.route('/test')
def test():
    """Тест парсинга"""
    items = fast_parse_funpay()
    
    if items:
        result = f"<h2>✅ Найдено {len(items)} товаров (онлайн продавцы):</h2>"
        for item in items:
            result += f'''
            <div style="border:1px solid #ddd; padding:15px; margin:10px; border-radius:5px; background: #f9f9f9;">
                <h4>{item['title']}</h4>
                <p><strong>Цена:</strong> {item['price']} руб.</p>
                <p><strong>Сервер:</strong> {item['server']}</p>
                <p><strong>Продавец:</strong> {item['seller']}</p>
                <p><a href="{item['link']}" target="_blank" style="color: #007bff;">Открыть на FunPay</a></p>
            </div>
            '''
    else:
        result = '''
        <div style="background:#f8d7da; padding:20px; border-radius:5px; color: #721c24;">
            <h2>❌ Товары не найдены</h2>
            <p>Возможные причины:</p>
            <ul>
                <li>Нет онлайн продавцов в данный момент</li>
                <li>Проблемы с подключением к FunPay</li>
                <li>Сайт FunPay недоступен или изменил структуру</li>
            </ul>
        </div>
        '''
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Тест парсинга</title>
        <style>
            body {{ font-family: Arial; margin: 20px; background: #f5f5f5; }}
            a {{ color: #007bff; text-decoration: none; }}
            a:hover {{ text-decoration: underline; }}
        </style>
    </head>
    <body>
        <a href="/">← На главную</a>
        <div style="max-width: 800px; margin: 20px auto; background: white; padding: 30px; border-radius: 10px;">
            {result}
        </div>
    </body>
    </html>
    '''

@app.route('/telegram_test')
def telegram_test():
    """Тест Telegram"""
    test_message = (
        "🤖 <b>Тестовое сообщение от FunPay Hunter</b>\n\n"
        "✅ Если вы видите это сообщение, значит Telegram настроен правильно!\n\n"
        "🕐 Время отправки: " + datetime.now().strftime("%H:%M:%S") + "\n\n"
        "Теперь вы можете запустить мониторинг - бот будет присылать уведомления о новых товарах Black Russia."
    )
    
    success = send_telegram_message(test_message)
    
    if success:
        return '''
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial; margin: 20px; background: #f5f5f5;">
            <a href="/">← На главную</a>
            <div style="max-width: 600px; margin: 20px auto; background: white; padding: 30px; border-radius: 10px;">
                <div style="background: #d4edda; padding: 20px; border-radius: 5px;">
                    <h2 style="color: #155724;">✅ Тестовое сообщение отправлено!</h2>
                    <p>Проверьте ваш Telegram. Вы должны получить сообщение от бота.</p>
                    <p><strong>Если сообщение не пришло:</strong></p>
                    <ul>
                        <li>Проверьте TELEGRAM_BOT_TOKEN в Render</li>
                        <li>Проверьте TELEGRAM_CHAT_ID в Render</li>
                        <li>Убедитесь, что бот не заблокирован</li>
                        <li>Отправьте боту команду /start в Telegram</li>
                    </ul>
                </div>
            </div>
        </body>
        </html>
        '''
    else:
        return '''
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial; margin: 20px; background: #f5f5f5;">
            <a href="/">← На главную</a>
            <div style="max-width: 600px; margin: 20px auto; background: white; padding: 30px; border-radius: 10px;">
                <div style="background: #f8d7da; padding: 20px; border-radius: 5px; color: #721c24;">
                    <h2>❌ Ошибка отправки сообщения</h2>
                    <p>Не удалось отправить тестовое сообщение в Telegram.</p>
                    <p><strong>Проверьте:</strong></p>
                    <ol>
                        <li>Зайдите на Render Dashboard → ваш сервис → Environment</li>
                        <li>Убедитесь, что заданы TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID</li>
                        <li>Перезапустите сервис после добавления переменных</li>
                        <li>Проверьте логи на Render для детальной ошибки</li>
                    </ol>
                </div>
            </div>
        </body>
        </html>
        '''

@app.route('/start_monitor')
def start_monitor():
    """Запуск мониторинга"""
    global monitoring_active, monitoring_thread
    
    if not monitoring_active:
        monitoring_active = True
        monitoring_thread = threading.Thread(target=monitoring_loop)
        monitoring_thread.daemon = True
        monitoring_thread.start()
        
        send_telegram_message(
            "✅ <b>Мониторинг запущен!</b>\n\n"
            "Я начал отслеживать новые предложения Black Russia на FunPay.\n"
            "Проверка каждые 60 секунд.\n\n"
            "🕐 Время запуска: " + datetime.now().strftime("%H:%M:%S")
        )
        
        return '''
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial; margin: 20px; background: #f5f5f5;">
            <a href="/">← На главную</a>
            <div style="max-width: 600px; margin: 20px auto; background: white; padding: 30px; border-radius: 10px;">
                <div style="background: #d4edda; padding: 20px; border-radius: 5px;">
                    <h2 style="color: #155724;">✅ Мониторинг запущен</h2>
                    <p>Бот начал проверять новые предложения Black Russia.</p>
                    <p><strong>Режим работы:</strong></p>
                    <ul>
                        <li>Проверка каждые 60 секунд</li>
                        <li>Только онлайн продавцы</li>
                        <li>Цена от 10 до 50000 руб</li>
                        <li>Автоматические уведомления в Telegram</li>
                    </ul>
                    <p>Вы получили сообщение в Telegram о запуске мониторинга.</p>
                </div>
            </div>
        </body>
        </html>
        '''
    else:
        return '''
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial; margin: 20px; background: #f5f5f5;">
            <a href="/">← На главную</a>
            <div style="max-width: 600px; margin: 20px auto; background: white; padding: 30px; border-radius: 10px;">
                <div style="background: #fff3cd; padding: 20px; border-radius: 5px; color: #856404;">
                    <h2>⚠️ Мониторинг уже запущен</h2>
                    <p>Бот уже отслеживает новые предложения.</p>
                    <p>Если хотите остановить мониторинг, нажмите "Остановить мониторинг".</p>
                </div>
            </div>
        </body>
        </html>
        '''

@app.route('/stop_monitor')
def stop_monitor():
    """Остановка мониторинга"""
    global monitoring_active
    monitoring_active = False
    
    send_telegram_message(
        "⏸️ <b>Мониторинг остановлен</b>\n\n"
        "Я больше не проверяю новые предложения.\n\n"
        "🕐 Время остановки: " + datetime.now().strftime("%H:%M:%S")
    )
    
    return '''
    <!DOCTYPE html>
    <html>
    <body style="font-family: Arial; margin: 20px; background: #f5f5f5;">
        <a href="/">← На главную</a>
        <div style="max-width: 600px; margin: 20px auto; background: white; padding: 30px; border-radius: 10px;">
            <div style="background: #d1ecf1; padding: 20px; border-radius: 5px; color: #0c5460;">
                <h2>⏸️ Мониторинг остановлен</h2>
                <p>Бот больше не проверяет новые предложения.</p>
                <p>Вы получили сообщение в Telegram об остановке.</p>
                <p>Для возобновления работы нажмите "Запустить мониторинг".</p>
            </div>
        </div>
    </body>
    </html>
    '''

@app.route('/health')
def health():
    """Health check для Render"""
    return json.dumps({
        'status': 'ok',
        'monitoring': monitoring_active,
        'items_count': len(found_items),
        'telegram_configured': bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
    }), 200, {'Content-Type': 'application/json'}

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
