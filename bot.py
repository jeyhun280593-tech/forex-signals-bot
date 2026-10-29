import asyncio
import logging
import os
import math
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiohttp import web

# ТОКЕН ТВОЕГО БОТА
BOT_TOKEN = "9193718167:AAE0VFcyk1jKmqbPKy5uaX_KwiYGHbyiFvA"

# 7 стабильных пар с Binance
CRYPTO_API_URL = "https://binance.com"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

SUBSCRIBERS = set()

# Храним цены закрытия
price_history = {
    "BTC/USDT": [],
    "ETH/USDT": [],
    "SOL/USDT": [],
    "XRP/USDT": [],
    "BNB/USDT": [],
    "ADA/USDT": [],
    "DOGE/USDT": []
}

def calculate_rsi(prices, period=5):
    if len(prices) < period + 1:
        return None
    gains = 0
    losses = 0
    for i in range(1, period + 1):
        diff = prices[-i] - prices[-i - 1]
        if diff > 0:
            gains += diff
        else:
            losses -= diff
    if losses == 0:
        return 100
    rs = gains / losses
    return 100 - (100 / (1 + rs))

def calculate_bollinger(prices, period=10, dev=1.8):
    if len(prices) < period:
        return None, None
    sma_prices = prices[-period:]
    sma = sum(sma_prices) / period
    variance = sum((x - sma) ** 2 for x in sma_prices) / period
    std_dev = math.sqrt(variance)
    bb_high = sma + (dev * std_dev)
    bb_low = sma - (dev * std_dev)
    return bb_high, bb_low

# Изолированная функция одного быстрого сканирования рынка
async def execute_market_scan():
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        async with aiohttp.ClientSession() as session:
            async with session.get(CRYPTO_API_URL, headers=headers, timeout=4) as resp:
                if resp.status == 200:
                    crypto_data = await resp.json()
                    for ticker in crypto_data:
                        sym = ticker.get("symbol")
                        val = float(ticker.get("price", 0))
                        asset = f"{sym[:-4]}/{sym[-4:]}"
                        
                        if asset in price_history:
                            price_history[asset].append(val)
                            if len(price_history[asset]) > 25:
                                price_history[asset].pop(0)
                                
                            if len(price_history[asset]) >= 12:
                                await check_pocket_signals(asset)
                    logging.info("==> Математическое ядро: Котировки успешно обновлены.")
    except Exception as e:
        logging.error(f"Ошибка при прямом сканировании: {e}")

async def check_pocket_signals(asset):
    try:
        prices = price_history[asset]
        rsi = calculate_rsi(prices, period=5)
        bb_high, bb_low = calculate_bollinger(prices, period=10, dev=1.8)
        
        if rsi is None or bb_high is None or bb_low is None:
            return

        last_price = prices[-1]

        # Скальпинг на 10 секунд (повышенная чувствительность индикаторов)
        if last_price <= bb_low and rsi < 40:  # Смягчили фильтр для учащения сигналов
            await send_to_all(
                f"🚨 **POCKET OPTION: CALL (ВВЕРХ)**\n\n"
                f"💱 Пара: **{asset}** [Таймфрейм: **S5**]\n"
                f"💵 Вход: `{last_price:.4f}`\n"
                f"⚡ RSI: `{rsi:.1f}`\n"
                f"⏳ Срок сделки: **10 СЕКУНД**\n"
            )
        elif last_price >= bb_high and rsi > 60:  # Смягчили фильтр для учащения сигналов
            await send_to_all(
                f"🔴 **POCKET OPTION: PUT (ВНИЗ)**\n\n"
                f"💱 Пара: **{asset}** [Таймфрейм: **S5**]\n"
                f"💵 Вход: `{last_price:.4f}`\n"
                f"⚡ RSI: `{rsi:.1f}`\n"
                f"⏳ Срок сделки: **10 СЕКУНД**\n"
            )
    except Exception as e:
        logging.error(f"Ошибка вычисления индикаторов для {asset}: {e}")

async def send_to_all(message: str):
    tasks = [bot.send_message(chat_id=uid, text=message, parse_mode="Markdown") for uid in SUBSCRIBERS]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    SUBSCRIBERS.add(message.chat.id)
    await message.answer(
        "🦅 **Сверхчувствительный Робот Pocket Option активирован!**\n\n"
        "Система переведена на гибридный движок синхронизации с сервером Render.\n"
        "Мониторинг 7 пар запущен. Сигналы начнут поступать автоматически при волатильности."
    )

# Бесконечный цикл сбора котировок, который мы изолируем от Телеграма
async def permanent_loop():
    while True:
        await execute_market_scan()
        await asyncio.sleep(5)

# ИСПРАВЛЕНО НАВСЕГДА: Каждый раз, когда Render пингует веб-сервер, мы принудительно обновляем цены!
async def handle_ping(request):
    asyncio.create_task(execute_market_scan())
    return web.Response(text="Бот онлайн и сканирует рынок!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"==> Веб-порт {port} успешно открыт.")

async def main():
    await start_web_server()
    # Запускаем независимый цикл сбора котировок в основном потоке asyncio
    asyncio.create_task(permanent_loop())
    # Запускаем пуллинг сообщений Telegram
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
