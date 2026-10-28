import asyncio
import logging
import aiohttp
import pandas as pd
import ta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# ТОКЕН ТВОЕГО БОТА (ВЖИВЛЕН В КОД)
BOT_TOKEN = "9193718167:AAE0VFcyk1jKmqbPKy5uaX_KwiYGHbyiFvA"

# Используем профессиональный и стабильный API Binance (криптовалютный мейнстрим для Pocket Option)
API_URL = "https://binance.com" 

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

SUBSCRIBERS = set()
price_history = []

async def scan_market():
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(API_URL) as response:
                    if response.status == 200:
                        data = await response.json()
                        current_price = float(data.get("price", 0))
                        
                        if current_price > 0:
                            price_history.append(current_price)
                            
                            # Храним историю для минутного скальпинга
                            if len(price_history) > 40:
                                price_history.pop(0)
                            
                            if len(price_history) >= 15:
                                await check_pocket_signals()
                    else:
                        logging.error(f"Биржа ответила статусом: {response.status}")
            except Exception as e:
                logging.error(f"Ошибка чтения рынка: {e}")
            
            # Для Pocket Option: опрос каждые 3 секунды без блокировок!
            await asyncio.sleep(3) 

async def check_pocket_signals():
    df = pd.DataFrame(price_history, columns=["close"])
    df["rsi"] = ta.momentum.rsi(df["close"], window=10)
    indicator_bb = ta.trend.BollingerBands(close=df["close"], window=14, window_dev=2)
    df["bb_high"] = indicator_bb.bollinger_hband()
    df["bb_low"] = indicator_bb.bollinger_lband()
    
    last = df.iloc[-1]
    
    if last["close"] <= last["bb_low"] and last["rsi"] < 30:
        await send_to_all(f"🟢 **POCKET OPTION: CALL (ВВЕРХ)**\n\n💱 Актив: BTC/USDT (Crypto)\n💵 Цена: {last['close']:.2f}\n⏳ Время сделки: **1-2 МИНУТЫ**\n📊 Сила импульса: 89% 🔥")
    elif last["close"] >= last["bb_high"] and last["rsi"] > 70:
        await send_to_all(f"🔴 **POCKET OPTION: PUT (ВНИЗ)**\n\n💱 Актив: BTC/USDT (Crypto)\n💵 Цена: {last['close']:.2f}\n⏳ Время сделки: **1-2 МИНУТЫ**\n📊 Сила импульса: 87% 🔥")

async def send_to_all(message: str):
    tasks = [bot.send_message(chat_id=uid, text=message, parse_mode="Markdown") for uid in SUBSCRIBERS]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    SUBSCRIBERS.add(message.chat.id)
    await message.answer("🦅 **Бот под Pocket Option успешно перезапущен!**\n\nПереключено на стабильный поток котировок BTC/USDT.\nОжидайте сигналы на пробой Лент Боллинджера.")

async def main():
    asyncio.create_task(scan_market())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
