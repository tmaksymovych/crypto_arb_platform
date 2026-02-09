import asyncio
import json
import logging
import os
import sys

import ccxt.async_support as ccxt
import redis.asyncio as redis


from common.schemas import Ticker
from common.mapper import normalize_symbol

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)   
logger = logging.getLogger("Collector")

REDIS_HOST = os.getenv('REDIS_HOST', '127.0.0.1')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
MIN_VOLUME = float(os.getenv("MIN_VOLUME_USD", 0))
EXCHANGE_ID = os.getenv('EXCHANGE_ID', 'binance')


async def fetch_and_process(exchange, redis_client):
    """
    main logic: fetch from exchange -> validate -> save to redis
    """

    try:
        #1. ask for all tickers at once
        tickers = await exchange.fetch_tickers()

        pipe = redis_client.pipeline()
        count = 0

        for symbol, data in tickers.items():
            vol = data.get('quoteVolume', 0)

            if vol < MIN_VOLUME:
                continue 

            norm_symbol = normalize_symbol(symbol, exchange.id)

            try:
                ticker_obj = Ticker(
                    symbol=norm_symbol,
                    exchange=exchange.id,
                    bid=float(data['bid']) if data['bid'] else 0.0,
                    ask=float(data['ask']) if data['ask'] else 0.0,
                    volume=float(vol) if vol else 0.0
                )
                
                key = f"ticker:{EXCHANGE_ID}:{norm_symbol}"
                pipe.set(key, ticker_obj.model_dump_json())
                pipe.expire(key, 60)
                count += 1

            except Exception as e:
                #  мы увидим, почему тикер не прошел
                # logger.info(f"Validation error for {symbol}: {e}")
                continue
        
        await pipe.execute()
        logger.info(f"Updated {count} tickers from {EXCHANGE_ID}")

    except ccxt.NetworkError:
        logger.error("Network error. Retrying...")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")


async def main():
    """
    Service entry point: initialize exchange and redis, then run main loop
    """

    #1. Initialize Redis client
    logger.info(f"Connecting to Redis at {REDIS_HOST}:{REDIS_PORT}...")
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

    #2. Initialize exchange client
    if not hasattr(ccxt, EXCHANGE_ID):
        logger.error(f"Exchange '{EXCHANGE_ID}' not supported by ccxt.")
        return
    
    exchange_class = getattr(ccxt, EXCHANGE_ID)
    exchange = exchange_class({
        "enableRateLimit": True, # built-in rate limiter to avoid hitting API limits
        "options": {
            "defaultType": "spot"
        }
    })

    logger.info(f"Starting Collector loop for {EXCHANGE_ID.upper()}...")

    try:
        #3. Main loop
        while True:
            await fetch_and_process(exchange, redis_client)
            # pause before next update
            await asyncio.sleep(2)
    finally:
        await exchange.close()
        await redis_client.close()

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())