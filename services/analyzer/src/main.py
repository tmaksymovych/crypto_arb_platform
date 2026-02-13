import asyncio
import json
import logging
import os
import redis.asyncio as redis
import time
import aiohttp
from dotenv import load_dotenv
from common.schemas import Ticker

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("Analyzer")

# Загрузка настроек
TG_TOKEN = os.getenv("TG_BOT_TOKEN")
raw_ids = os.getenv("CHAT_IDS", "")
CHAT_IDS = [x.strip() for x in raw_ids.split(",") if x.strip()]

logger.info(f"Загруженные ID: {CHAT_IDS}")



REDIS_HOST = os.getenv('REDIS_HOST', '127.0.0.1')
MIN_VOLUME_USDT = 50000.0
THRESHOLD = 1.0  # Arbitrage threshold in percentage
SIGNAL_TTL = 300  # Time to live for arbitrage signals in seconds (2.5 minutes)
BLACKLIST = ['U/USDT']

if not TG_TOKEN or not CHAT_IDS:
    logger.error("Критическая ошибка: TG_BOT_TOKEN или MY_TG_ID не найдены в переменных окружения!")

async def send_telegram(message):
    if not TG_TOKEN:
        return
    async with aiohttp.ClientSession() as session:
        for chatId in CHAT_IDS:

            cleanId = str(chatId).strip()
            if not cleanId:
                continue

            url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
            payload = {
                "chat_id":chatId,
                "text":message,
                "parse_mode":"HTML"
            }
            try:
                async with session.post(url, json=payload) as response:
                        if response.status != 200:
                            logger.error(f"ошибка отправки в TG: {await response.text()}")
                        else:
                            logger.info(f"Успешно отправлен в чат {chatId}")
            except Exception as e:
                logger.error(f"TG Connection Error: {e}")

async def check_arbitrage(r, symbol, buy_exchange, sell_exchange, buy_ticker, sell_ticker):
    """
    check arbitrage between two exchanges nad control timer
    """
    buy_price = buy_ticker.ask
    sell_price = sell_ticker.bid
    
    if buy_price == 0 or sell_price == 0:
        return

    profit = (sell_price / buy_price - 1) * 100
    signal_key = f"signal:{symbol}:{buy_exchange}_to_{sell_exchange}"

    if profit >= THRESHOLD and profit <= 50: # if we have profit
        

        start_time = await r.get(signal_key)

        if not start_time:
            # it is 1st signal, start timer
            await r.set(signal_key, time.time())
            # logger.info(f"New arbitrage signal: {symbol} {buy_exchange}→{sell_exchange} profit={profit:.2f}%")
        else:
            # signal already exists, check duration
            duration = time.time() - float(start_time)

            if duration >= SIGNAL_TTL:
                msg = (
                    f"✅ <b>CONFIRMED ARBITRAGE</b>\n\n"
                    f"💎 <b>{symbol}</b>\n"
                    f"🟢 Buy: {buy_exchange.upper()} ({buy_price})\n"
                    f"🔴 Sell: {sell_exchange.upper()} ({sell_price})\n"
                    f"💰 <b>Profit: {profit:.2f}%</b>\n"
                    f"⏱ Duration: {duration/60:.1f} min"
                )
                logger.info(f"Signal confirmed: {symbol} {buy_exchange}→{sell_exchange} duration={duration/60:.1f}min profit={profit:.2f}%")
                # here you call telegram bot
                await send_telegram(msg)
                await r.delete(signal_key)    
            # else:
        #     # to not spam logs, we log only once per minute
        #     if int(duration) % 60 < 5:
        #         logger.info(f"Signal pending: {symbol} {buy_exchange}→{sell_exchange} duration={duration/60:.1f}min profit={profit:.2f}%")
    else:
        # if profit drops below threshold, remove signal
        if await r.exists(signal_key):
            await r.delete(signal_key)
            # logger.info(f"Signal removed: {symbol} {buy_exchange}→{sell_exchange} profit={profit:.2f}%")


async def main():
    r = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)
    logger.info("Redis connected, starting analyzer")
    logger.info(f"Threshold={THRESHOLD}% TTL={SIGNAL_TTL/60:.1f}min")
    logger.info(f"Analyzer started. Active chats: {len(CHAT_IDS)}")

    while True:
        try:
            keys = await r.keys("ticker:*:*")

            market_snapshot = {}

            for key in keys:

                parts = key.split(":")
                if len(parts) != 3:
                    continue

                exchange_id = parts[1]
                # extract symbol from the key   ticker:binance:BTC/USDT -> BTC/USDT
                symbol = parts[2]
                
                if symbol in BLACKLIST:
                    continue

                raw_data = await r.get(key)
                if raw_data:
                    if symbol not in market_snapshot:
                        market_snapshot[symbol] = {}
                    try:
                        market_snapshot[symbol][exchange_id] = Ticker.model_validate_json(raw_data)
                    except:
                        continue

            for symbol, exchanges in market_snapshot.items():

                exchanges_names = list(exchanges.keys())

                if len(exchanges_names) < 2:
                    continue

                for i in range(len(exchanges_names)):
                    for j in range(i + 1, len(exchanges_names)):
                        EX1 = exchanges_names[i]
                        EX2 = exchanges_names[j]

                        ticker1 = exchanges[EX1]
                        ticker2 = exchanges[EX2]

                        if ticker1.quoteVolume < MIN_VOLUME_USDT or ticker2.quoteVolume < MIN_VOLUME_USDT:
                            continue

                        await check_arbitrage(r, symbol, EX1, EX2, ticker1, ticker2)
                        await check_arbitrage(r, symbol, EX2, EX1, ticker2, ticker1)

            await asyncio.sleep(2)  # small pause to not overload Redis

        
        except Exception as e:
            logger.error(f"Main loop error: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())