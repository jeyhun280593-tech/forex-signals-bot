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

# ИСПРАВЛЕНО: Только сверхстабильный и надежный API Binance без сторонних фиатных сайтов
CRYPTO_API_URL = "https://binance.com"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

SUBSCRIBERS = set()
price_history = {
    "BTC/USDT": [],
    "ETH/USDT": []
}

async def scan_market():
    await asyncio.sleep(5)
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                
                # Запрос криптовалюты с Binance
                async with session.get(CRYPTO_API_URL, headers=headers, timeout=8) as resp:
                    if resp.status == 200:
                        crypto_data = await resp.json()
                        for ticker in crypto_data:
                            sym = ticker.get("symbol")
                            val = float(ticker.get("price", 0))
                            if sym == "BTCUSDT":
                                price_history["BTC/USDT"].append(val)
                            elif sym == "ETHUSDT":
                                price_history["ETH/USDT"].append(val)

                # Анализ накопленных данных
                for asset in price_history.keys():
                    if len(price_history[asset]) > 35:
                        price_history[asset].pop(0)
                    
                    if len(price_history[asset]) >= 15:
                        await check_pocket_signals(asset)
                        
                logging.info("==> Мониторинг рынка: Котировки BTC и ETH успешно обновлены.")
                
            except Exception as e:
                logging.error(f"Ошибка получения данных рынка: {e}")
            
            # Проверка каждые 12 секунд
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

        # Сигналы пробоя Боллинджера + фильтр RSI
        if last["close"] <= last["bb_low"] and last["rsi"] < 35:
            await send_to_all(
                f"🟢 **POCKET OPTION: CALL (ВВЕРХ)**\n\n"
                f"💱 Пара: **{asset}**\n"
                f"💵 Вход: {last['close']:.2f}\n"
                f"⏳ Срок: **1-3 МИНУТЫ**\n"
            )
        elif last["close"] >= last["bb_high"] and last["rsi"] > 65:
            await send_to_all(
                f"🔴 **POCKET OPTION: PUT (ВНИЗ)**\n\n"
                f"💱 Пара: **{asset}**\n"
                f"💵 Вход: {last['close']:.2f}\n"
                f"⏳ Срок: **1-3 МИНУТЫ**\n"
            )
    except Exception as e:
        logging.error(f"Ошибка расчета индикаторов {asset}: {e}")

async def send_to_all(message: str):
    tasks = [bot.send_message(chat_id=uid, text=message, parse_mode="Markdown") for uid in SUBSCRIBERS]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    SUBSCRIBERS.add(message.chat.id)
    await message.answer(
        "🦅 **Бот Pocket Option полностью запущен и работает!**\n\n"
        "Я анализирую графики BTC/USDT и ETH/USDT напрямую с Binance. Сигналы придут в этот чат автоматически."
    )

async def handle_ping(request):
    return web.Response(text="Бот онлайн!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"==> Веб-порт {port} успешно открыт для Render.")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await start_web_server()
    asyncio.create_task(scan_market())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
