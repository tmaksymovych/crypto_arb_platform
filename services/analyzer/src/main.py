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

REDIS_HOST = os.getenv('REDIS_HOST', '127.0.0.1')

TG_TOKEN = os.getenv("TG_BOT_TOKEN")
raw_ids = os.getenv("CHAT_IDS", "")
CHAT_IDS = [x.strip() for x in raw_ids.split(",") if x.strip()]

logger.info(f"Загруженные ID: {CHAT_IDS}")

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


LEVERAGE = 6    # Arbitrage threshold in percentage
THRESHOLD = 0.6   # Minimum spread percentage to consider for arbitrage
ESTIMATED_FEE_TOTAL = 0.22  # Estimated total fees for arbitrage
MIN_VOLUME_USDT = 5000000 # 5 million USD minimum volume to consider for arbitrage
SIGNAL_TTL = 10 
BLACKLIST = ['U/USDT']

async def check_futures_arbitrage(r, symbol, long_exchange, short_exchange, long_ticker, short_ticker):
    """
    check arbitrage between two exchanges nad control timer
    """
    long_price = long_ticker.ask
    short_price = short_ticker.bid

    if long_price == 0 or short_price == 0:
        return
    
   # 1. "Грязный" спред в процентах
    spread = ((short_price - long_price) / long_price) * 100

    # Если спред меньше порога (0.6%), даже не смотрим, чтобы не кормить биржу
    if spread < THRESHOLD:
        return

    # 2. Расчет чистой прибыли
    # Сколько мы отдадим бирже за круг (4 сделки)
    fees_cost = ESTIMATED_FEE_TOTAL # 0.22%
    
    # Чистый спред (Spread - Fees)
    net_spread = spread - fees_cost
    
    # 3. ROE (Прибыль на вложенные свои деньги с учетом плеча)
    # Пример: Спред 1%, Комиссия 0.22%, Чистыми 0.78%. Плечо x6.
    # ROE = 0.78% * 6 = 4.68%
    roe = net_spread * LEVERAGE

    signal_key = f"futures_signal:{symbol}:{long_exchange}->{short_exchange}"

    if net_spread > 0 and net_spread < 5:
        start_time = await r.get(signal_key)

        if not start_time:
            # ex=60: Ключ живет в Redis 60 секунд. 
            # Это дает запас времени, чтобы таймер (10 сек) успел сработать.
            await r.set(signal_key, time.time(), ex=60)
            # logger.info(f"NEW {symbol} {long_exchange}->{short_exchange} Spread: {spread:.2f}%")    
        else:
            duration = time.time() - float(start_time)
            if duration >= SIGNAL_TTL:
                logger.info(f"CONFIRMED {symbol} Profit: {net_spread:.2f}% ROE: {roe:.2f}%")
                msg = (
                        f"🚀 <b>FUTURES ARB (x{LEVERAGE})</b>\n\n"
                        f"💎 <b>{symbol}</b>\n"
                        f"📉 <b>SHORT: {short_exchange.upper()}</b> ({short_price})\n"
                        f"📈 <b>LONG:  {long_exchange.upper()}</b> ({long_price})\n\n"     
                        f"📊 Raw Spread: {spread:.2f}%\n"
                        f"💸 Fees: -{fees_cost}%\n"
                        f"🟢 <b>Net Spread: {net_spread:.2f}%</b>\n\n"
                        
                        f"🔥 <b>Est. ROE: {roe:.2f}%</b> (Net Profit)\n"
                        f"⏱ Duration: {duration:.1f}s"
                    )
                await send_telegram(msg)
                await r.delete(signal_key)
    else:
        if await r.exists(signal_key):
            await r.delete(signal_key)




async def main():
    r = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)
    logger.info("Redis connected, starting analyzer")
    logger.info(f"Threshold={THRESHOLD}% TTL={SIGNAL_TTL/60:.1f}min")

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

                        await check_futures_arbitrage(r, symbol, EX1, EX2, ticker1, ticker2)
                        await check_futures_arbitrage(r, symbol, EX2, EX1, ticker2, ticker1)

            await asyncio.sleep(2)  # small pause to not overload Redis

        
        except Exception as e:
            logger.error(f"Main loop error: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())