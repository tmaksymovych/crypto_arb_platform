import asyncio
import json
import logging
import redis.asyncio as redis
import time
from common.schemas import Ticker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("Analyzer")

THRESHOLD = 1.0  # Arbitrage threshold in percentage
SIGNAL_TTL = 1800  # Time to live for arbitrage signals in seconds (30 minutes)

async def check_arbitrage(r, symbol, buy_exchange, sell_exchange, buy_price, sell_price):
    """
    check arbitrage between two exchanges nad control timer
    """
    if buy_price == 0 or sell_price == 0:
        return

    profit = (sell_price / buy_price - 1) * 100

    signal_key = f"signal:{symbol}:{buy_exchange}_to_{sell_exchange}"

    if profit >= THRESHOLD: # if we have profit
        start_time = await r.get(signal_key)

        if not start_time:
            # it is 1st signal, start timer
            await r.set(signal_key, time.time())
            logger.info(f"New arbitrage signal: {symbol} {buy_exchange}→{sell_exchange} profit={profit:.2f}%")
        else:
            # signal already exists, check duration
            duration = time.time() - float(start_time)

            if duration >= SIGNAL_TTL:
                logger.info(f"Signal confirmed: {symbol} {buy_exchange}→{sell_exchange} duration={duration/60:.1f}min profit={profit:.2f}%")
                # here you call telegram bot
            else:
                # to not spam logs, we log only once per minute
                if int(duration) % 60 < 5:
                    logger.info(f"Signal pending: {symbol} {buy_exchange}→{sell_exchange} duration={duration/60:.1f}min profit={profit:.2f}%")
    else:
        # if profit drops below threshold, remove signal
        if await r.exists(signal_key):
            logger.info(f"Signal removed: {symbol} {buy_exchange}→{sell_exchange} profit={profit:.2f}%")
            await r.delete(signal_key)



async def main():
    r = redis.Redis(host='127.0.0.1', port=6379, decode_responses=True)
    logger.info("Redis connected, starting analyzer")
    logger.info(f"Threshold={THRESHOLD}% TTL={SIGNAL_TTL/60:.1f}min")

    while True:
        try:
            binance_keys = await r.keys("ticker:binance:*")

            for b_key in binance_keys:
                # extract symbol from the key   ticker:binance:BTC/USDT -> BTC/USDT
                symbol = b_key.split(":")[-1]
                #forming the corresponding key for Bybit
                by_key = f"ticker:bybit:{symbol}"
                # collect pair of tickers for the same symbol from both exchanges
                raw_data = await r.mget([b_key, by_key])
                if not raw_data[0] or not raw_data[1]:
                    continue

                try:
                    bn_ticker = Ticker.model_validate_json(raw_data[0])
                    by_ticker = Ticker.model_validate_json(raw_data[1])

                    # A. buy on Binance, sell on Bybit
                    await check_arbitrage(r, symbol, "binance", "bybit", bn_ticker.ask, by_ticker.bid)
                    # B. buy on Bybit, sell on Binance
                    await check_arbitrage(r, symbol, "bybit", "binance", by_ticker.ask, bn_ticker.bid)

                except Exception as e:
                    continue

            await asyncio.sleep(3)  # pause before next check of all tickers
        
        except Exception as e:
            logger.error(f"Main loop error: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
