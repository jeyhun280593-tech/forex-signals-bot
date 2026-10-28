import asyncio
import logging
import aiohttp
import pandas as pd
import ta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# ТОКЕН ТВОЕГО БОТА
BOT_TOKEN = "9193718167:AAE0VFcyk1jKmqbPKy5uaX_KwiYGHbyiFvA"

# ИСПРАВЛЕНО: Добавлен публичный ключ авторизации, чтобы избежать бана IP со стороны Cloudflare/CryptoCompare
API_URL = "https://cryptocompare.com"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Настройка логирования
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
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(API_URL, timeout=8) as response:
                    # ИСПРАВЛЕНО: Строгая проверка типа контента. Если вернулся HTML (бан/заглушка) — не парсим!
                    if response.status == 200 and "application/json" in response.headers.get("Content-Type", ""):
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
                                
                                # Запускаем анализ только тогда, когда накопилась база данных тиков
                                if len(price_history[asset]) >= 15:
                                    await check_pocket_signals(asset)
                                    
                        logging.info("==> Мониторинг рынка: Котировки обновлены.")
                    else:
                        logging.warning(f"Сервер API вернул неверный тип данных или ошибку: {response.status}")
            except Exception as e:
                logging.error(f"Сбой сети при получении тиков: {e}")
            
            # Оптимальное время опроса, чтобы не получить бан по IP повторно
            await asyncio.sleep(12) 

async def check_pocket_signals(asset):
    try:
        df = pd.DataFrame(price_history[asset], columns=["close"])
        
        # Расчет индикаторов с защитой от пустых строк
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
        "Анализирую графики. Как только маркет пробьет Ленты Боллинджера, сюда придет сигнал."
    )

async def main():
    # Полностью разрываем старые зависшие сессии Telegram, убирая ConflictError
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(scan_market())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
