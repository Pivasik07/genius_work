import asyncio
from binance.client import Client
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
import time

# Конфігурація
TELEGRAM_TOKEN = '8188731974:AAGBnpQ-w1gG36JJOA8V0CbVb1rzjqFvRQo'
CHAT_ID = '-1002315794441'
API_KEY = '4vihoWHQ4HTAZqOe1LqMeATfIWd14OCtW49tABC5RFxDLar7ojfh2mfLdZfKcYJe'
API_SECRET = 'HXd3WF6vKNgLFBIUOTTjkgvkawZyCPFhYKpfXPc8CLJkBF6PrxubRJM3OkIGkf5o'

COINGLASS_URL = 'https://www.coinglass.com/tv/ru/Binance_{symbol}'

bot = Bot(token=TELEGRAM_TOKEN)

# Змінні для відстеження даних
previous_oi = {}  # Зберігаємо попереднє значення OI
oi_start_time = {}  # Час, коли ми зафіксували початкове значення OI для символу
signals_count = {}  # Лічильник сигналів для кожного символу

# Ініціалізація клієнта Binance
client = Client(API_KEY, API_SECRET)
# Змінні для зберігання часу останнього сповіщення
last_alert_time = {}

# Мінімальний інтервал між сповіщеннями для однієї монети (в секундах)
MIN_ALERT_INTERVAL = 1200  # 15 хвилин

async def send_alerts(signal):
    """Надсилаємо відформатоване сповіщення в Telegram."""
    # Перевіряємо час останнього сповіщення для цієї монети
    current_time = time.time()
    last_time = last_alert_time.get(signal['symbol'], 0)
    
    if current_time - last_time < MIN_ALERT_INTERVAL:
        return  # Якщо час між сповіщеннями менший за мінімальний інтервал, пропускаємо сповіщення
    
    # Оновлюємо час останнього сповіщення
    last_alert_time[signal['symbol']] = current_time

    url = COINGLASS_URL.format(symbol=signal['symbol'])

    # Форматуємо текст повідомлення
    message = (
    f"📊 *Сигнал Binance – 20 хвилин*\n"
    f"🔹 *Монета*: `{signal['symbol']}`\n"
    f"🔹 *Тип сигналу*: {signal['type']}\n"
    f"🔹 *Відкритий інтерес (OI)*: +{signal['oi_change']}% "
    f"({signal['oi_value'] / 1_000_000:,.2f} млн $)\n"  # Форматування суми в мільйонах
    f"🔹 *Зміна ціни*: {signal['price_change']}%\n"
    f"🔹 *Обсяг торгів*: {signal['volume'] / 1_000_000:,.2f} млн $\n"
    f"🔹 *Кількість сигналів за добу*: {signal['signals_today']}\n\n"
)


    # Клавіатура з кнопкою
    keyboard = [[InlineKeyboardButton("Деталі", url=url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Відправка повідомлення
    await bot.send_message(chat_id=CHAT_ID, text=message, reply_markup=reply_markup, parse_mode="Markdown")

async def fetch_symbol_data(symbol):
    """Асинхронно отримуємо OI, зміну ціни та обсяги для символу."""
    try:
        # Запит OI
        oi_info = await asyncio.to_thread(client.futures_open_interest, symbol=symbol)
        current_oi = float(oi_info['openInterest'])

        # Запит ціни та обсягів
        price_change, volume = await asyncio.to_thread(fetch_price_and_volume, symbol)

        return symbol, current_oi, price_change, volume
    except Exception as e:
        print(f"Не вдалося отримати дані для {symbol}: {e}")
        return symbol, None, None, None

def fetch_price_and_volume(symbol):
    """Отримуємо зміну ціни та обсяг торгів для символу."""
    try:
        # Отримуємо інформацію про останні 10 хвилин
        klines = client.futures_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_1MINUTE, limit=10)
        close_prices = [float(kline[4]) for kline in klines]  # Ціни закриття
        volumes = [float(kline[5]) for kline in klines]  # Обсяги торгів

        # Розрахунок змін ціни
        price_change = ((close_prices[-1] - close_prices[0]) / close_prices[0]) * 100

        # Загальний обсяг за останні 10 хвилин
        total_volume = sum(volumes)

        return price_change, total_volume
    except Exception as e:
        print(f"Не вдалося отримати дані про ціну та обсяг для {symbol}: {e}")
        return 0, 0

def calculate_changes(symbol, current_oi, price_change, volume, interval=1200):
    """Обчислюємо зміни OI, ціни та обсягів та визначаємо тип сигналу."""
    global previous_oi, signals_count, oi_start_time
    signals = []

    current_time = time.time()

    # Якщо ще не зафіксовано початкове значення OI для цього символу
    if symbol not in oi_start_time or current_time - oi_start_time[symbol] > interval:
        # Оновлюємо початкове значення OI та час
        previous_oi[symbol] = current_oi
        oi_start_time[symbol] = current_time

    # Обчислення змін OI
    oi_change_percent = ((current_oi - previous_oi[symbol]) / previous_oi[symbol]) * 100

    # Логіка перевірки умов (OI, зміна ціни, обсяги)
    if abs(oi_change_percent) >= 5:  # Зміна OI понад 5%
        if volume > 1_000_000:  # Високий обсяг торгів
            if oi_change_percent > 0:
                signal_type = "🔼 Відкриття позицій (тренд посилюється)"
            else:
                signal_type = "🔽 Закриття позицій (тренд завершується)"
        else:
            signal_type = "⚠️ Низький обсяг (потенційно слабкий сигнал)"
        
        signals_count[symbol] = signals_count.get(symbol, 0) + 1
        signals.append({
            'symbol': symbol,
            'oi_change': round(oi_change_percent, 2),
            'oi_value': round(current_oi - previous_oi[symbol], 2),
            'price_change': round(price_change, 2),
            'volume': round(volume, 2),
            'signals_today': signals_count[symbol],
            'type': signal_type
        })

    return signals


def fetch_open_interest(symbols):
    """Отримуємо поточний відкритий інтерес (OI) для заданих символів."""
    oi_data = {}
    for symbol in symbols:
        try:
            oi_info = client.futures_open_interest(symbol=symbol)
            oi_data[symbol] = float(oi_info['openInterest'])
        except Exception as e:
            print(f"Не вдалося отримати OI для {symbol}: {e}")
    return oi_data

async def get_all_symbols():
    """Отримуємо всі символи для ф'ючерсних пар на Binance."""
    exchange_info = client.futures_exchange_info()
    symbols = []
    for symbol_info in exchange_info['symbols']:
        if symbol_info['status'] == 'TRADING':  # Перевіряємо, чи символ торгується
            symbols.append(symbol_info['symbol'])
    return symbols

async def monitor_open_interest():
    """Періодично оновлюємо дані OI та перевіряємо зміни для всіх символів."""
    symbols = await get_all_symbols()
    while True:
        try:
            # Паралельний збір даних для всіх символів
            results = await asyncio.gather(*(fetch_symbol_data(symbol) for symbol in symbols))
            
            for symbol, current_oi, price_change, volume in results:
                if current_oi is None or price_change is None or volume is None:
                    continue  # Пропускаємо символи з помилками

                # Розраховуємо сигнали
                signals = calculate_changes(symbol, current_oi, price_change, volume)

                # Надсилаємо сповіщення для кожного сигналу
                for signal in signals:
                    await send_alerts(signal)

        except Exception as e:
            print(f"Помилка під час моніторингу: {e}")
        
        await asyncio.sleep(15)  # Оновлюємо дані раз на хвилину




async def main():
    """Основна функція для запуску моніторингу."""
    await monitor_open_interest()

if __name__ == "__main__":
    asyncio.run(main())