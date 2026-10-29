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

# По-прежнему используем стабильный API Binance
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
                
                async with session.get(CRYPTO_API_URL, headers=headers, timeout=4) as resp:
                    if resp.status == 200:
                        crypto_data = await resp.json()
                        for ticker in crypto_data:
                            sym = ticker.get("symbol")
                            val = float(ticker.get("price", 0))
                            
                            asset = "BTC/USDT" if sym == "BTCUSDT" else "ETH/USDT"
                            price_history[asset].append(val)
                            
                            # Для быстрых свечей держим историю из 30 баров
                            if len(price_history[asset]) > 30:
                                price_history[asset].pop(0)
                                
                            # Начинаем анализ, когда накопилось 12 микро-свечей
                            if len(price_history[asset]) >= 12:
                                await check_pocket_signals(asset)
                                
                logging.info("==> Скальпинг S5: Микро-котировки обновлены.")
                
            except Exception as e:
                logging.error(f"Ошибка в быстром сканере: {e}")
            
            # ИСПРАВЛЕНО: Опрос рынка каждые 5 секунд для формирования таймфрейма S5!
            await asyncio.sleep(5) 

async def check_pocket_signals(asset):
    try:
        df = pd.DataFrame(price_history[asset], columns=["close"])
        
        # Оптимизированные быстрые индикаторы для микро-скальпинга
        df["rsi"] = ta.momentum.rsi(df["close"], window=5)  # Быстрый RSI
        indicator_bb = ta.trend.BollingerBands(close=df["close"], window=10, window_dev=2) # Чувствительный Боллинджер
        df["bb_high"] = indicator_bb.bollinger_hband()
        df["bb_low"] = indicator_bb.bollinger_lband()
        
        last = df.iloc[-1]
        
        if pd.isna(last["rsi"]) or pd.isna(last["bb_low"]) or pd.isna(last["bb_high"]):
            return

        # Сигналы на моментальный откат
        if last["close"] <= last["bb_low"] and last["rsi"] < 25: # Более жесткий фильтр RSI для точности
            await send_to_all(
                f"🚨 **POCKET OPTION: СКАЛЬПИНГ CALL (ВВЕРХ)**\n\n"
                f"💱 Пара: **{asset}** [Таймфрейм: **S5**]\n"
                f"💵 Вход: `{last['close']:.2f}`\n"
                f"⚡ Критический RSI: `{last['rsi']:.1f}`\n"
                f"⏳ Срок сделки: **10 СЕКУНД**\n"
            )
        elif last["close"] >= last["bb_high"] and last["rsi"] > 75: # Более жесткий фильтр RSI
            await send_to_all(
                f"🚨 **POCKET OPTION: СКАЛЬПИНГ PUT (ВНИЗ)**\n\n"
                f"💱 Пара: **{asset}** [Таймфрейм: **S5**]\n"
                f"💵 Вход: `{last['close']:.2f}`\n"
                f"⚡ Критический RSI: `{last['rsi']:.1f}`\n"
                f"⏳ Срок сделки: **10 СЕКУНД**\n"
            )
    except Exception as e:
        logging.error(f"Ошибка индикаторов на S5 для {asset}: {e}")

async def send_to_all(message: str):
    tasks = [bot.send_message(chat_id=uid, text=message, parse_mode="Markdown") for uid in SUBSCRIBERS]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    SUBSCRIBERS.add(message.chat.id)
    await message.answer(
        "⚡ **Бот Pocket Option [Микро-скальпинг 10с] активирован!**\n\n"
        "Анализирую секундные импульсы BTC и ETH с Binance. "
        "При резком выносе цены за пределы Лент Боллинджера выдам сигнал на **10 секунд**."
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
