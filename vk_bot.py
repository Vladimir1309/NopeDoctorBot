import time
import requests
import vk_api
from vk_api.utils import get_random_id
from bs4 import BeautifulSoup
import datetime

# ==========================================
# 1. НАСТРОЙКИ
# ==========================================
VK_TOKEN = "ВАШ_ТОКЕН"
VK_USER_ID = ВАШ_ID

MY_COOKIES = "ВАША_СТРОКА_КУКИ"
MY_COMMENT = "Консультация по поводу возможности проведения коррекции позвоночника (операция ASC / динамический аккорд) при S-образном идиопатическом сколиозе 3-4 степени."

BASE_PTASHNIKOV_URL = "https://my.spbkbran.ru/ru/schedule/1/3/-1/0/20001494/-1/568421/"

TARGET_DATES = [
    "2026-10-26", "2026-10-28", "2026-10-29", "2026-11-02", 
    "2026-11-05", "2026-11-09", "2026-11-11", "2026-11-12", "2026-11-16"
]

TURBO_DATES = ["2026-11-11", "2026-11-12"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9",
}

vk_session = vk_api.VkApi(token=VK_TOKEN)
vk = vk_session.get_api()

# ==========================================
# 2. ФУНКЦИИ
# ==========================================
def send_vk_message(text):
    try:
        vk.messages.send(user_id=VK_USER_ID, message=text, random_id=get_random_id())
        print(f"[{time.strftime('%H:%M:%S')}] Уведомление ВК отправлено.")
        time.sleep(1) # <-- УЛУЧШЕНИЕ: Пауза, чтобы ВК не забанил за спам
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

def check_auth(session):
    try:
        res = session.get("https://my.spbkbran.ru/ru/my/profile/", timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        body_tag = soup.find("body")
        if body_tag and "customer-id" in body_tag.attrs:
            return True
        return False
    except Exception:
        return False

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
    except Exception:
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
# 3. ОСНОВНОЙ ЦИКЛ
# ==========================================
if __name__ == "__main__":
    try:
        print("Бот мониторинга запущен...")
        send_vk_message("🤖 Бот нацелен на Пташникова. Ожидаю номерки!")
        
        session = get_authorized_session()
        is_booked = False
        alerted_dates = set() 
        
        while not is_booked:
            now = datetime.datetime.now()
            is_midnight_window = (now.hour == 23 and now.minute >= 58) or (now.hour == 0 and now.minute <= 5)
            
            if is_midnight_window:
                dates_to_check = TURBO_DATES
                sleep_time = 3
                print(f"--- 🚀 ТУРБО-РЕЖИМ ({now.strftime('%H:%M:%S')}) ---")
            else:
                dates_to_check = TARGET_DATES
                sleep_time = 60
                print(f"--- Новый цикл проверки ({now.strftime('%H:%M:%S')}) ---")
    
            for target_date in dates_to_check:
                date_url = f"{BASE_PTASHNIKOV_URL}{target_date}/"
                print(f"Проверяю {target_date}...")
                
                slots = find_slots_on_date(session, date_url)
                
                if slots:
                    print(f"🔥 Найдено {len(slots)} слотов на {target_date}!")
                    
                    if target_date not in alerted_dates:
                        if not check_auth(session):
                            print("⚠️ Куки слетели! Пропускаю автозапись.")
                            send_vk_message(f"⚠️ Сессия истекла! Появились места на {target_date}, но автозапись не сработает. Успейте нажать вручную:\n{slots[0]['url']}")
                            alerted_dates.add(target_date)
                            continue 
                    
                    send_vk_message(f"🔥 Появились места на {target_date}! Пробую записаться...")
                    
                    # УЛУЧШЕНИЕ: Перебираем все слоты, если первый не удался
                    success = False
                    for slot in slots:
                        success = auto_book_slot(session, slot["url"])
                        if success:
                            send_vk_message(f"🎉 УСПЕХ! Вы записаны на {target_date} в {slot['time']}.\nПроверьте ЛК!")
                            print("Запись успешна. Завершаю работу.")
                            is_booked = True
                            break # Выходим из перебора слотов
                        else:
                            print(f"Слот {slot['time']} не взялся, пробую следующий...")
                            time.sleep(1) # Пауза перед следующей попыткой
                    
                    if not success:
                        send_vk_message(f"❌ Все слоты на {target_date} не удалось взять (вероятно, их разобрали).")
                    
                    if is_booked:
                        break # Выходим из перебора дат, если записались
                
                time.sleep(1) 
                
            if is_booked:
                break
                
            time.sleep(sleep_time)
            
    except Exception as e:
        print("\n" + "="*50)
        print("❌ ПРОИЗОШЛА КРИТИЧЕСКАЯ ОШИБКА:")
        print(e)
        print("="*50)
    finally:
        input("\nНажмите Enter, чтобы закрыть окно...")
