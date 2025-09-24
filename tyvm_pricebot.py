import re
import requests
import xml.etree.ElementTree as ET
import logging

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

import asyncio
from config import API_TOKEN

# ======================== Логирование ========================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ======================== Инициализация бота ========================
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# ======================== Загрузка кошельков ========================
wallets = []
with open("wallets.txt", "r", encoding="utf-8") as f:
    for line in f:
        if line.strip():
            parts = line.strip().split("|")
            if len(parts) == 3:
                name, xpath, address = [p.strip() for p in parts]
                wallets.append({"name": name, "xpath": xpath, "address": address})

# ======================== Функции для работы ========================

def escape_md(text: str) -> str:
    """Экранирует все спецсимволы MarkdownV2"""
    return re.sub(r'([_*\[\]()~`>#+\-=|{}.!$])', r'\\\1', text)

def format_number_md(n):
    """Форматируем число с пробелами, двумя знаками после запятой и экранируем для MarkdownV2"""
    formatted = f"{n:,.2f}".replace(",", " ")  # 8 084 496.13
    # теперь экранируем точки и все спецсимволы
    formatted_escaped = escape_md(formatted)
    return formatted_escaped


def md_link(name, url):
    """Создаёт MarkdownV2 ссылку, экранируя спецсимволы в тексте и URL"""
    name_escaped = escape_md(name)
    url_escaped = url.replace("(", "%28").replace(")", "%29")
    return f"[{name_escaped}]({url_escaped})"

# ======================== Получение данных TYVM ========================

def get_tyvm_data():
    logging.info("Запуск Selenium для парсинга кошельков...")
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    tonviewer_url = "https://tonviewer.com/EQAaAXF948uK1jAi4RyM5ywd_ggIjx8uZK4WL5GZX6HlkEAX?section=holders"
    driver.get(tonviewer_url)

    values = []
    for w in wallets:
        elem = driver.find_element(By.XPATH, w["xpath"])
        text_value = elem.text.replace(" ", "").replace(",", "")
        match = re.search(r"([\d\.]+)", text_value)
        if match:
            num = float(match.group(1))
            values.append(num)
        else:
            values.append(0.0)

    driver.quit()
    total_tokens = sum(values)

    # Цена TYVM в TON
    price_per_tyvm_in_ton = 571365 / total_tokens

    # Цена TON через Binance
    def get_ton_price_binance():
        url = "https://api.binance.com/api/v3/ticker/price?symbol=TONUSDT"
        response = requests.get(url)
        data = response.json()
        return float(data['price'])

    ton_price_usd = get_ton_price_binance()
    price_per_tyvm_in_usd = price_per_tyvm_in_ton * ton_price_usd

    # Курс USD → RUB с ЦБ РФ
    def get_usd_to_rub_cbr():
        url = "https://www.cbr.ru/scripts/XML_daily.asp"
        response = requests.get(url)
        root = ET.fromstring(response.content)
        for valute in root.findall('Valute'):
            if valute.find('CharCode').text == 'USD':
                value_str = valute.find('Value').text
                value = float(value_str.replace(',', '.'))
                nominal = int(valute.find('Nominal').text)
                return value / nominal
        raise ValueError("Курс USD не найден")

    usd_to_rub = get_usd_to_rub_cbr()
    price_per_tyvm_in_rub = price_per_tyvm_in_usd * usd_to_rub

    # Округление до тысячных
    price_per_tyvm_in_ton = round(price_per_tyvm_in_ton, 3)
    price_per_tyvm_in_usd = round(price_per_tyvm_in_usd, 3)
    price_per_tyvm_in_rub = round(price_per_tyvm_in_rub, 3)
    ton_price_usd = round(ton_price_usd, 3)
    usd_to_rub = round(usd_to_rub, 3)

    logging.info(f"Данные TYVM получены: {values}, сумма={total_tokens}, TYVM в TON={price_per_tyvm_in_ton}, USD={price_per_tyvm_in_usd}, RUB={price_per_tyvm_in_rub}")
    return values, total_tokens, price_per_tyvm_in_ton, price_per_tyvm_in_usd, price_per_tyvm_in_rub, ton_price_usd, usd_to_rub

# ======================== Главное меню ========================

def main_menu_kb():
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Цена"), KeyboardButton(text="Калькулятор")]],
        resize_keyboard=True
    )
    return kb

# ======================== Обработчики ========================

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    logging.info(f"Пользователь {message.from_user.id} нажал /start")
    await message.answer(
        "Привет! Нажми кнопку 'Цена', чтобы узнать текущую стоимость TYVM или 'Калькулятор' для расчета токенов.",
        reply_markup=main_menu_kb()
    )

@dp.message(F.text == "Цена")
async def price_handler(message: types.Message):
    logging.info(f"Пользователь {message.from_user.id} нажал 'Цена'")
    await message.answer("Считаю значения, это может занять несколько секунд...")

    try:
        values, total_tokens, price_ton, price_usd, price_rub, ton_price, usd_to_rub = get_tyvm_data()

        msg_lines = []
        for i, w in enumerate(wallets):
            wallet_name = md_link(w['name'], f"https://tonviewer.com/{w['address']}")
            token_balance = format_number_md(values[i])
            msg_lines.append(f"{i+1}\. {wallet_name}, токенов: {token_balance}")  # Точка уже экранирована

        # Форматируем числа (уже экранированы в format_number_md)
        total_tokens_md = format_number_md(total_tokens)
        price_ton_md = format_number_md(price_ton)
        price_usd_md = format_number_md(price_usd)
        ton_price_md = format_number_md(ton_price)
        price_rub_md = format_number_md(price_rub)
        usd_to_rub_md = format_number_md(usd_to_rub)

        # Собираем строки, экранируя скобки
        msg_lines.append(f"\nСумма токенов: {total_tokens_md}\n")
        msg_lines.append(f"Цена TYVM в TON: {price_ton_md}")
        msg_lines.append(f"Цена TYVM в USD: {escape_md('$')}{price_usd_md} \({escape_md('TON $')}{ton_price_md}\)")
        msg_lines.append(f"Цена TYVM в RUB: {price_rub_md} \({escape_md('USD ')}{usd_to_rub_md}\)")  # Экранируем ( и )

        # Объединяем строки без дополнительного escape_md
        msg = "\n".join(msg_lines)
        await message.answer(msg, parse_mode="MarkdownV2", disable_web_page_preview=False)

    except Exception as e:
        logging.error(f"Ошибка при расчёте: {e}")
        await message.answer(f"Ошибка при расчёте: {escape_md(str(e))}", parse_mode="MarkdownV2")


@dp.message(F.text == "Калькулятор")
async def calculator_start(message: types.Message):
    logging.info(f"Пользователь {message.from_user.id} нажал 'Калькулятор'")
    await message.answer("Введите количество токенов TYVM, которое хотите рассчитать:")

    @dp.message()
    async def get_amount(msg: types.Message):
        try:
            amount = float(msg.text.replace(" ", ""))
            logging.info(f"Пользователь {msg.from_user.id} ввел количество токенов: {amount}")

            _, _, price_ton, price_usd, price_rub, _, _ = get_tyvm_data()

            ton_value = amount * price_ton
            usd_value = amount * price_usd
            rub_value = amount * price_rub

            result_msg = (
                f"Баланс для {amount:.2f} TYVM:\n\n"
                f"В TON: {ton_value:.2f}\n"
                f"В USD: {usd_value:.2f}\n"
                f"В RUB: {rub_value:.2f}"
            )

            await msg.answer(result_msg)
        except ValueError:
            await msg.answer("Пожалуйста, введите корректное число токенов.")

# ======================== Запуск бота ========================

if __name__ == "__main__":
    logging.info("Бот запущен")
    asyncio.run(dp.start_polling(bot))
