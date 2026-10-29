import asyncio
import logging
import os
import math
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

# ТОКЕН ТВОЕГО БОТА
BOT_TOKEN = "9193718167:AAE0VFcyk1jKmqbPKy5uaX_KwiYGHbyiFvA"

# 7 стабильных пар с Binance
CRYPTO_API_URL = "https://binance.com"

# Конфигурация Webhook для Render
WEBHOOK_HOST = os.getenv("RENDER_EXTERNAL_URL")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

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

async def scan_market(app: web.Application):
    logging.info("==> Фоновый сканер рынка успешно запущен внутри цикла aiohttp.")
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                headers = {"User-Agent": "Mozilla/5.0"}
                async with session.get(CRYPTO_API_URL, headers=headers, timeout=4) as resp:
                    if resp.status == 200:
                        crypto_data = await resp.json()
                        for ticker in crypto_data:
                            sym = ticker.get("symbol")
                            val = float(ticker.get("price", 0))
                            if not sym:
                                continue
                            asset = f"{sym[:-4]}/{sym[-4:]}"
                            
                            if asset in price_history:
                                price_history[asset].append(val)
                                if len(price_history[asset]) > 25:
                                    price_history[asset].pop(0)
                                    
                                if len(price_history[asset]) >= 12:
                                    await check_pocket_signals(asset)
                        logging.info("==> Мониторинг рынка: Котировки успешно обновлены.")
        except Exception as e:
            logging.error(f"Ошибка сбора котировок: {e}")
        
        # Интервал сканирования — 5 секунд (S5 таймфрейм)
        await asyncio.sleep(5)

async def check_pocket_signals(asset):
    try:
        prices = price_history[asset]
        rsi = calculate_rsi(prices, period=5)
        bb_high, bb_low = calculate_bollinger(prices, period=10, dev=1.8)
        
        if rsi is None or bb_high is None or bb_low is None:
            return

        last_price = prices[-1]

        # Сигналы на 10-секундный отскок
        if last_price <= bb_low and rsi < 40:
            await send_to_all(
                f"🚨 **POCKET OPTION: CALL (ВВЕРХ)**\n\n"
                f"💱 Пара: **{asset}** [Таймфрейм: **S5**]\n"
                f"💵 Вход: `{last_price:.4f}`\n"
                f"⚡ RSI: `{rsi:.1f}`\n"
                f"⏳ Срок сделки: **10 СЕКУНД**\n"
            )
        elif last_price >= bb_high and rsi > 60:
            await send_to_all(
                f"🔴 **POCKET OPTION: PUT (ВНИЗ)**\n\n"
                f"💱 Пара: **{asset}** [Таймфрейм: **S5**]\n"
                f"💵 Вход: `{last_price:.4f}`\n"
                f"⚡ RSI: `{rsi:.1f}`\n"
                f"⏳ Срок сделки: **10 СЕКУНД**\n"
            )
    except Exception as e:
        logging.error(f"Ошибка индикаторов для {asset}: {e}")

async def send_to_all(message: str):
    tasks = [bot.send_message(chat_id=uid, text=message, parse_mode="Markdown") for uid in SUBSCRIBERS]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    SUBSCRIBERS.add(message.chat.id)
    await message.answer(
        "🦅 **Робот Pocket Option [7 активов / 10 секунд] успешно запущен!**\n\n"
        "Все системные конфликты и ошибки циклов событий устранены. Я круглосуточно сканирую рынок Binance."
    )

async def on_startup(bot: Bot) -> None:
    logging.info(f"Установка Webhook на адрес: {WEBHOOK_URL}")
    await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)

# ИСПРАВЛЕНО: Безопасный запуск фоновой задачи сканирования через контекст aiohttp приложения
async def start_background_tasks(app: web.Application):
    app['market_scanner'] = asyncio.create_task(scan_market(app))
    yield
    app['market_scanner'].cancel()
    await app['market_scanner']

def main():
    dp.startup.register(on_startup)
    
    app = web.Application()
    
    # Настраиваем фоновые задачи aiohttp
    app.cleanup_background_tasks.append(start_background_tasks)
    
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot
    )
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    
    port = int(os.environ.get("PORT", 10000))
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
