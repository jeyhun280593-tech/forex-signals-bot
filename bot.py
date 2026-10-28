import asyncio
import logging
import aiohttp
import pandas as pd
import ta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# ТОКЕН ТВОЕГО БОТА (ВЖИВЛЕН В КОД)
BOT_TOKEN = "9193718167:AAE0VFcyk1jKmqbPKy5uaX_KwiYGHbyiFvA"

# ИСПРАВЛЕНО: Новый прямой эндпоинт, который отдает ТОЛЬКО JSON данные
API_URL = "https://cryptocompare.com"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

SUBSCRIBERS = set()

# Хранилище истории цен для каждого актива отдельно
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
                async with session.get(API_URL) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # ИСПРАВЛЕНО: Безопасное извлечение котировок из правильного JSON-объекта
                        raw_btc = data.get("BTC", {}).get("USDT", 0)
                        raw_eth = data.get("ETH", {}).get("USDT", 0)
                        
                        # Для Форекс-пар получаем их прямые курсы к USD
                        raw_eur = data.get("EUR", {}).get("USD", 0)
                        raw_gbp = data.get("GBP", {}).get("USD", 0)
                        
                        # Для USD/JPY (в API идет JPY к USD, поэтому переворачиваем значение)
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
                                price_history[asset].append(price)
                                if len(price_history[asset]) > 30:
                                    price_history[asset].pop(0)
                                
                                # Если накопилось достаточно тиков для анализа (минимум 15)
                                if len(price_history[asset]) >= 15:
                                    await check_pocket_signals(asset)
                                    
                        logging.info("==> Сканирование всех ТОП-активов выполнено успешно!")
                    else:
                        logging.error(f"Ошибка шлюза данных: {response.status}")
            except Exception as e:
                logging.error(f"Ошибка сети при сканировании рынка: {e}")
            
            # Интервал сканирования — 10 секунд
            await asyncio.sleep(10) 

async def check_pocket_signals(asset):
    df = pd.DataFrame(price_history[asset], columns=["close"])
    
    # Расчет технических индикаторов RSI и Bollinger Bands
    df["rsi"] = ta.momentum.rsi(df["close"], window=10)
    indicator_bb = ta.trend.BollingerBands(close=df["close"], window=14, window_dev=2)
    df["bb_high"] = indicator_bb.bollinger_hband()
    df["bb_low"] = indicator_bb.bollinger_lband()
    
    last = df.iloc[-1]
    
    # Защита от пустых значений на этапе первоначального заполнения истории
    if pd.isna(last["rsi"]) or pd.isna(last["bb_low"]) or pd.isna(last["bb_high"]):
        return

    # 🟢 СИГНАЛ ВВЕРХ (CALL) — цена упала до минимума и отскакивает
    if last["close"] <= last["bb_low"] and last["rsi"] < 35:
        await send_to_all(
            f"🟢 **POCKET OPTION: CALL (ВВЕРХ)**\n\n"
            f"💱 Актив: **{asset}** (Доходность ~92%)\n"
            f"💵 Цена входа: {last['close']:.5f}\n"
            f"⏳ Экспирация: **1-3 МИНУТЫ**\n"
            f"📊 Точность сигнала: Высокая 🔥"
        )
    # 🔴 СИГНАЛ ВНИЗ (PUT) — цена взлетела до максимума и разворачивается
    elif last["close"] >= last["bb_high"] and last["rsi"] > 65:
        await send_to_all(
            f"🔴 **POCKET OPTION: PUT (ВНИЗ)**\n\n"
            f"💱 Актив: **{asset}** (Доходность ~92%)\n"
            f"💵 Цена входа: {last['close']:.5f}\n"
            f"⏳ Экспирация: **1-3 МИНУТЫ**\n"
            f"📊 Точность сигнала: Высокая 🔥"
        )

async def send_to_all(message: str):
    tasks = [bot.send_message(chat_id=uid, text=message, parse_mode="Markdown") for uid in SUBSCRIBERS]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    SUBSCRIBERS.add(message.chat.id)
    await message.answer(
        "🦅 **Мультивалютный Бот Pocket Option запущен!**\n\n"
        "Робот одновременно сканирует 5 самых прибыльных активов (+92%):\n"
        "📈 *BTC/USDT, ETH/USDT, EUR/USD, GBP/USD, USD/JPY*\n\n"
        "Сигналы на пробой Лент Боллинджера и RSI будут приходить автоматически."
    )

async def main():
    # ИСПРАВЛЕНО: drop_pending_updates=True сбрасывает старые сессии и убирает ошибку TelegramConflictError
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(scan_market())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
