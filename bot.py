import asyncio
import logging
import aiohttp
import pandas as pd
import ta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# ТОКЕН ТВОЕГО БОТА (Оставляем прямо в коде, как у тебя и сделано)
BOT_TOKEN = "9193718167:AAE0VFcyk1jKmqbPKy5uaX_KwiYGHbyiFvA"

# ИСПРАВЛЕНО: Официальный JSON эндпоинт для стабильного получения котировок
API_URL = "https://cryptocompare.com"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Настройка логирования для панели Render (чтобы ты видел логи в консоли)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Список подписчиков (для Render в рамках одного сеанса)
SUBSCRIBERS = set()

# История котировок для технического анализа
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
                headers = {"User-Agent": "Mozilla/5.0 PocketOptionBot"}
                async with session.get(API_URL, headers=headers, timeout=8) as response:
                    # Строгая проверка типа контента: исключаем HTML-заглушки Cloudflare
                    if response.status == 200 and "application/json" in response.headers.get("Content-Type", "").lower():
                        data = await response.json()
                        
                        raw_btc = data.get("BTC", {}).get("USDT", 0)
                        raw_eth = data.get("ETH", {}).get("USDT", 0)
                        raw_eur = data.get("EUR", {}).get("USD", 0)
                        raw_gbp = data.get("GBP", {}).get("USD", 0)
                        
                        # Расчет обратного курса для пары USD/JPY
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
                                
                                # Анализ запускается, когда накопилось минимум 15 тиков
                                if len(price_history[asset]) >= 15:
                                    await check_pocket_signals(asset)
                                    
                        logging.info("==> Мониторинг рынка: Котировки обновлены.")
                    else:
                        logging.warning(f"API вернул ошибку или HTML-страницу: {response.status}")
            except Exception as e:
                logging.error(f"Сбой сети при парсинге тиков: {e}")
            
            # Оптимальный интервал в 12 секунд для предотвращения банов на Render
            await asyncio.sleep(12) 

async def check_pocket_signals(asset):
    try:
        df = pd.DataFrame(price_history[asset], columns=["close"])
        
        # Расчет профессиональных индикаторов
        df["rsi"] = ta.momentum.rsi(df["close"], window=10)
        indicator_bb = ta.trend.BollingerBands(close=df["close"], window=14, window_dev=2)
        df["bb_high"] = indicator_bb.bollinger_hband()
        df["bb_low"] = indicator_bb.bollinger_lband()
        
        last = df.iloc[-1]
        
        # Защита от пустых значений в начале расчета
        if pd.isna(last["rsi"]) or pd.isna(last["bb_low"]) or pd.isna(last["bb_high"]):
            return

        # Стратегия: пробой Лент Боллинджера + фильтрация зон RSI (30/70)
        if last["close"] <= last["bb_low"] and last["rsi"] < 30:
            await send_to_all(
                f"🟢 **POCKET OPTION: CALL (ВВЕРХ)**\n\n"
                f"💱 Пара: **{asset}**\n"
                f"💵 Вход: `{last['close']:.5f}`\n"
                f"📊 RSI: `{last['rsi']:.1f}`\n"
                f"⏳ Срок: **1-3 МИНУТЫ**\n"
            )
        elif last["close"] >= last["bb_high"] and last["rsi"] > 70:
            await send_to_all(
                f"🔴 **POCKET OPTION: PUT (ВНИЗ)**\n\n"
                f"💱 Пара: **{asset}**\n"
                f"💵 Вход: `{last['close']:.5f}`\n"
                f"📊 RSI: `{last['rsi']:.1f}`\n"
                f"⏳ Срок: **1-3 МИНУТЫ**\n"
            )
    except Exception as e:
        logging.error(f"Ошибка при расчете индикаторов для {asset}: {e}")

async def send_to_all(message: str):
    if not SUBSCRIBERS:
        return
    tasks = [bot.send_message(chat_id=uid, text=message, parse_mode="Markdown") for uid in SUBSCRIBERS]
    await asyncio.gather(*tasks, return_exceptions=True)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    SUBSCRIBERS.add(message.chat.id)
    await message.answer(
        "🦅 **Мультивалютный Бот Pocket Option запущен на сервере!**\n\n"
        "Анализирую графики. Как только маркет пробьет Ленты Боллинджера и RSI зайдет в экстремальную зону, сюда придет сигнал."
    )

async def main():
    # Удаляем старые зависшие вебхуки Telegram, предотвращая ConflictError в логах Render
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(scan_market())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
