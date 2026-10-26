import time
import requests
import vk_api
from vk_api.utils import get_random_id
from bs4 import BeautifulSoup
import datetime
import sys

# ==========================================
# 1. НАСТРОЙКИ
# ==========================================
VK_TOKEN = "vk1.a.ВАШ_ТОКЕН"
VK_USER_ID = 12345678

MY_COOKIES = "spbkbran=...ВАШИ_КУКИ..."
MY_COMMENT = "Консультация по поводу возможности проведения коррекции позвоночника (операция ASC / динамический аккорд) при S-образном идиопатическом сколиозе 3-4 степени."

BASE_PTASHNIKOV_URL = "https://my.spbkbran.ru/ru/schedule/1/3/-1/0/20001494/-1/568421/"

# Ваш список дат
TARGET_DATES = [
    "2026-10-26", "2026-10-28", "2026-10-29", "2026-11-02", 
    "2026-11-05", "2026-11-09", "2026-11-11", "2026-11-12", "2026-11-16"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9",
}

vk_session = vk_api.VkApi(token=VK_TOKEN)
vk = vk_session.get_api()

# ==========================================
# 2. ФУНКЦИИ (без изменений)
# ==========================================
def send_vk_message(text):
    try:
        vk.messages.send(user_id=VK_USER_ID, message=text, random_id=get_random_id())
        print(f"[{time.strftime('%H:%M:%S')}] Уведомление ВК отправлено.")
    except Exception as e:
        print(f"❌ Ошибка ВК: {e}")

def get_authorized_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    for item in MY_COOKIES.split(';'):
        if '=' in item:
            k, v = item.strip().split('=', 1)
            session.cookies.set(k, v)
    return session

def find_slots_on_date(session, date_url):
    try:
        response = session.get(date_url, timeout=15)
        soup = BeautifulSoup(response.text, "html.parser")
        
        no_records = soup.find("div", class_="alert-danger")
        if no_records and "Записи не найдены" in no_records.text:
            return []
            
        slots = []
        for a in soup.find_all('a', href=True):
            if '/schedule/' in a['href'] and 'disabled' not in a.get('class', []):
                text = a.get_text(" ", strip=True)
                if "-" in text and ":" in text:
                    full_url = f"https://my.spbkbran.ru{a['href']}" if a['href'].startswith('/') else a['href']
                    slots.append({"time": text, "url": full_url})
        return slots
    except Exception as e:
        print(f"Ошибка поиска слотов: {e}")
        return []

def auto_book_slot(session, slot_url):
    print(f"[{time.strftime('%H:%M:%S')}] Попытка автозаписи на {slot_url}...")
    try:
        headers = HEADERS.copy()
        headers["Referer"] = slot_url 
        headers["X-Requested-With"] = "XMLHttpRequest" 
        
        response = session.get(slot_url, headers=headers, timeout=15)
        if "Подтверждение приема" not in response.text:
            return False
            
        soup = BeautifulSoup(response.text, "html.parser")
        
        meta_csrf = soup.find("meta", {"name": "csrf-token"})
        if meta_csrf:
            headers["X-CSRF-Token"] = meta_csrf.get("content")
        
        service_value = None
        select_tag = soup.find("select", {"name": "LinkOrderCompanyService[]"})
        if select_tag:
            for option in select_tag.find_all("option"):
                val = option.get("value")
                if val and val != "":
                    service_value = val
                    break
        
        if not service_value:
            return False

        payload = {inp.get("name"): inp.get("value") for inp in soup.find_all("input", type="hidden") if inp.get("name")}
        payload["LinkOrderCompanyService[]"] = service_value
        payload["Order[Comment]"] = MY_COMMENT
        payload["checkboxagree"] = "1"
        payload["ordersubmit"] = "Подтвердить запись"

        post_response = session.post(slot_url, data=payload, headers=headers, timeout=15, allow_redirects=False)
        location = post_response.headers.get("Location", "")
        
        if post_response.status_code == 302 and ("/orders/success/" in location or "/orders/pay/" in location):
            if "/orders/pay/" in location:
                pay_url = f"https://my.spbkbran.ru{location}" if location.startswith('/') else location
                session.get(pay_url, headers=headers, timeout=15)
            return True
            
        return False
    except Exception as e:
        print(f"❌ Сетевая ошибка: {e}")
        return False

# ==========================================
# 3. ОСНОВНОЙ ЦИКЛ (с поддержкой списка)
# ==========================================
if __name__ == "__main__":
    try:
        print(f"Бот запущен. Слежу за {len(TARGET_DATES)} датами.")
        send_vk_message(f"🤖 Бот запущен! Слежу за {len(TARGET_DATES)} датами Пташникова.")
        
        session = get_authorized_session()
        is_booked = False # Флаг для выхода из бесконечного цикла
        
        while not is_booked:
            now = datetime.datetime.now()
            
            # Турбо-режим (с 23:58 до 00:05)
            is_midnight_window = (now.hour == 23 and now.minute >= 58) or (now.hour == 0 and now.minute <= 5)
            sleep_time = 3 if is_midnight_window else 60
    
            print(f"--- Новый цикл проверки ({now.strftime('%H:%M:%S')}) ---")
    
            # Перебираем все даты по очереди
            for target_date in TARGET_DATES:
                date_url = f"{BASE_PTASHNIKOV_URL}{target_date}/"
                print(f"Проверяю {target_date}...")
                
                # ИСПРАВЛЕНО: передаем правильную переменную date_url
                slots = find_slots_on_date(session, date_url)
                
                if slots:
                    print(f"🔥 Найдено {len(slots)} слотов на {target_date}!")
                    send_vk_message(f"🔥 Появились места на {target_date}! Пробую записаться...")
                    
                    # Берем первый попавшийся слот
                    target_slot = slots[0]
                    success = auto_book_slot(session, target_slot["url"])
                    
                    if success:
                        send_vk_message(f"🎉 УСПЕХ! Вы записаны на {target_date} в {target_slot['time']}.\nПроверьте ЛК!")
                        print("Запись успешна. Завершаю работу.")
                        is_booked = True
                        break # Выходим из цикла перебора дат
                    else:
                        send_vk_message(f"❌ Слот на {target_date} был, но автозапись не удалась.")
                
                time.sleep(1) # Небольшая пауза между проверкой разных дат
                
            if is_booked:
                break # Выходим из бесконечного цикла while, если записались
                
            time.sleep(sleep_time) # Ждем перед новым кругом проверок
            
    except Exception as e:
        print("\n" + "="*50)
        print("❌ ПРОИЗОШЛА КРИТИЧЕСКАЯ ОШИБКА:")
        print(e)
        print("="*50)
    finally:
        # Этот блок сработает при любом раскладе: и при успехе, и при ошибке
        input("\nНажмите Enter, чтобы закрыть окно...")
