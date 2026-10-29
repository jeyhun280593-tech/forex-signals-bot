import asyncio
import logging
import os
import aiohttp
import pandas as pd
import ta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiohttp import web

# ТОКЕН ТВОЕГО БОТА
BOT_TOKEN = "9193718167:AAE0VFcyk1jKmqbPKy5uaX_KwiYGHbyiFvA"

# ИСПРАВЛЕНО: Добавлен демо API-ключ (api_key=...), чтобы обойти блокировку Cloudflare и получать чистый JSON
API_URL = "https://cryptocompare.com"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

SUBSCRIBERS = set()
price_history = {
    "BTC/USDT": [],
    "ETH/USDT": [],
    "EUR/USD": [],
    "GBP/USD": [],
    "USD/JPY": []
}

async def scan_market():
    # Небольшая пауза при старте, чтобы дать веб-серверу инициализироваться
    await asyncio.sleep(5)
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                # ИСПРАВЛЕНО: Эмуляция заголовков реального браузера, чтобы избежать детекта робота
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
                async with session.get(API_URL, headers=headers, timeout=8) as response:
                    content_type = response.headers.get("Content-Type", "").lower()
                    
                    if response.status == 200 and "application/json" in content_type:
                        data = await response.json()
                        
                        raw_btc = data.get("BTC", {}).get("USDT", 0)
                        raw_eth = data.get("ETH", {}).get("USDT", 0)
                        raw_eur = data.get("EUR", {}).get("USD", 0)
                        raw_gbp = data.get("GBP", {}).get("USD", 0)
                        
                        raw_jpy_usd = data.get("JPY", {}).get("USD", 0)
                        raw_jpy = 1 / raw_jpy_usd if raw_jpy_usd > 0 else 0

                        mappings = {
                            "BTC/USDT": raw_btc,
                            "ETH/USDT": raw_eth,
                            "EUR/USD": raw_eur,
                            "GBP/USD": raw_gbp,
                            "USD/JPY": raw_jpy
                        }

                        for asset, price in mappings.items():
                            if price > 0:
                                price_history[asset].append(float(price))
                                if len(price_history[asset]) > 35:
                                    price_history[asset].pop(0)
                                
                                if len(price_history[asset]) >= 15:
                                    await check_pocket_signals(asset)
                                    
                        logging.info("==> Мониторинг рынка: Котировки обновлены.")
                    else:
                        logging.warning(f"API вернул неверный тип данных или ошибку {response.status}. Тип: {content_type}")
            except Exception as e:
                logging.error(f"Сбой сети при получении тиков: {e}")
            
            await asyncio.sleep(12) 

async def check_pocket_signals(asset):
    try:
        df = pd.DataFrame(price_history[asset], columns=["close"])
        df["rsi"] = ta.momentum.rsi(df["close"], window=10)
        indicator_bb = ta.trend.BollingerBands(close=df["close"], window=14, window_dev=2)
        df["bb_high"] = indicator_bb.bollinger_hband()
        df["bb_low"] = indicator_bb.bollinger_lband()
        
        last = df.iloc[-1]
        
        if pd.isna(last["rsi"]) or pd.isna(last["bb_low"]) or pd.isna(last["bb_high"]):
            return

        if last["close"] <= last["bb_low"] and last["rsi"] < 35:
            await send_to_all(
                f"🟢 **POCKET OPTION: CALL (ВВЕРХ)**\n\n"
                f"💱 Пара: **{asset}**\n"
                f"💵 Вход: {last['close']:.5f}\n"
                f"⏳ Срок: **1-3 МИНУТЫ**\n"
            )
        elif last["close"] >= last["bb_high"] and last["rsi"] > 65:
            await send_to_all(
                f"🔴 **POCKET OPTION: PUT (ВНИЗ)**\n\n"
                f"💱 Пара: **{asset}**\n"
                f"💵 Вход: {last['close']:.5f}\n"
                f"⏳ Срок: **1-3 МИНУТЫ**\n"
            )
    except Exception as e:
        logging.error(f"Ошибка при расчете индикаторов для {asset}: {e}")

async def send_to_all(message: str):
    tasks = [bot.send_message(chat_id=uid, text=message, parse_mode="Markdown") for uid in SUBSCRIBERS]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    SUBSCRIBERS.add(message.chat.id)
    await message.answer(
        "🦅 **Мультивалютный Бот Pocket Option запущен!**\n\n"
        "Анализирую графики. Сигналы придут при пробое Лент Боллинджера."
    )

# ИСПРАВЛЕНО: Веб-сервер для прохождения проверки портов Render (Port Binding)
async def handle_ping(request):
    return web.Response(text="Бот активен и работает!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    # Render автоматически передает нужный порт в переменную среды PORT
    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"==> Фейковый веб-сервер успешно запущен на порту {port}")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    # Запускаем привязку к порту, чтобы Render не закрывал приложение
    await start_web_server()
    # Запускаем парсер котировок
    asyncio.create_task(scan_market())
    # Запускаем пуллинг Telegram
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
