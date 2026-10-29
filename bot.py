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

# ИСПРАВЛЕНО: Прямые, готовые ссылки без склеек строк во избежание опечаток
CRYPTO_API_URL = "https://binance.com"
FIAT_API_URL = "https://er-api.com"

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
    await asyncio.sleep(5)
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                
                # 1. Запрос криптовалюты с Binance
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

                # 2. Запрос фиатных курсов
                async with session.get(FIAT_API_URL, headers=headers, timeout=8) as resp:
                    if resp.status == 200:
                        fiat_data = await resp.json()
                        rates = fiat_data.get("rates", {})
                        
                        eur_usd = 1 / rates.get("EUR") if rates.get("EUR") else 0
                        gbp_usd = 1 / rates.get("GBP") if rates.get("GBP") else 0
                        usd_jpy = float(rates.get("JPY", 0))

                        if eur_usd > 0: price_history["EUR/USD"].append(eur_usd)
                        if gbp_usd > 0: price_history["GBP/USD"].append(gbp_usd)
                        if usd_jpy > 0: price_history["USD/JPY"].append(usd_jpy)

                # Анализ накопленных данных
                for asset in price_history.keys():
                    if len(price_history[asset]) > 35:
                        price_history[asset].pop(0)
                    
                    if len(price_history[asset]) >= 15:
                        await check_pocket_signals(asset)
                        
                logging.info("==> Мониторинг рынка: Котировки успешно обновлены.")
                
            except Exception as e:
                logging.error(f"Ошибка получения данных рынка: {e}")
            
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
        logging.error(f"Ошибка расчета индикаторов {asset}: {e}")

async def send_to_all(message: str):
    tasks = [bot.send_message(chat_id=uid, text=message, parse_mode="Markdown") for uid in SUBSCRIBERS]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    SUBSCRIBERS.add(message.chat.id)
    await message.answer(
        "🦅 **Мультивалютный Бот Pocket Option запущен!**\n\n"
        "Я собираю данные с биржи Binance и вычисляю Ленты Боллинджера + RSI. Сигналы придут автоматически."
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
