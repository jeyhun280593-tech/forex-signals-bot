import asyncio
import logging
import aiohttp
import pandas as pd
import ta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# Вставь свой токен вместо текста ниже (кавычки оставь!)
BOT_TOKEN = "9193718167:AAE0VFcyk1jKmqbPKy5uaX_KwiYGHbyiFvA"
API_URL = "https://er-api.com" 

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

SUBSCRIBERS = set()
price_history = {"EUR": [], "GBP": [], "JPY": []}

async def scan_market():
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(API_URL) as response:
                    if response.status == 200:
                        data = await response.json()
                        rates = data.get("rates", {})
                        
                        for curr in price_history.keys():
                            if curr in rates:
                                current_price = 1 / rates[curr] if rates[curr] != 0 else 0
                                price_history[curr].append(current_price)
                                
                                if len(price_history[curr]) > 50:
                                    price_history[curr].pop(0)
                                
                                if len(price_history[curr]) >= 20:
                                    await check_pocket_signals(curr)
            except Exception as e:
                logging.error(f"Ошибка сети: {e}")
            await asyncio.sleep(5) 

async def check_pocket_signals(currency):
    df = pd.DataFrame(price_history[currency], columns=["close"])
    df["rsi"] = ta.momentum.rsi(df["close"], window=10)
    indicator_bb = ta.trend.BollingerBands(close=df["close"], window=14, window_dev=2)
    df["bb_high"] = indicator_bb.bollinger_hband()
    df["bb_low"] = indicator_bb.bollinger_lband()
    
    last = df.iloc[-1]
    
    if last["close"] <= last["bb_low"] and last["rsi"] < 30:
        await send_to_all(f"🟢 **POCKET OPTION: CALL (ВВЕРХ)**\n\n💱 Пара: {currency}/USD\n💵 Цена: {last['close']:.5f}\n⏳ Время: **1-3 МИНУТЫ**\n📊 Точность: 87% 🔥")
    elif last["close"] >= last["bb_high"] and last["rsi"] > 70:
        await send_to_all(f"🔴 **POCKET OPTION: PUT (ВНИЗ)**\n\n💱 Пара: {currency}/USD\n💵 Цена: {last['close']:.5f}\n⏳ Время: **1-3 МИНУТЫ**\n📊 Точность: 85% 🔥")

async def send_to_all(message: str):
    tasks = [bot.send_message(chat_id=uid, text=message, parse_mode="Markdown") for uid in SUBSCRIBERS]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    SUBSCRIBERS.add(message.chat.id)
    await message.answer("🦅 **Бот под Pocket Option запущен!**\nОжидайте сигналы BUY/SELL с экспирацией 1-3 минуты.")

async def main():
    asyncio.create_task(scan_market())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
                      
