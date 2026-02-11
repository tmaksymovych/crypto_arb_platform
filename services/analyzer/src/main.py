import asyncio
import json
import logging
import os
import redis.asyncio as redis
import time
from common.schemas import Ticker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("Analyzer")

REDIS_HOST = os.getenv('REDIS_HOST', '127.0.0.1')

MIN_VOLUME_USDT = 90000.0
THRESHOLD = 0.75  # Arbitrage threshold in percentage
SIGNAL_TTL = 30  # Time to live for arbitrage signals in seconds (2.5 minutes)
BLACKLIST = ['U/USDT']

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
                logger.info(f"Signal confirmed: {symbol} {buy_exchange}→{sell_exchange} duration={duration/60:.1f}min profit={profit:.2f}%")
                # here you call telegram bot
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
