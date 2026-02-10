import asyncio
import json
import os
import redis.asyncio as redis
import ccxt.async_support as ccxt
import logging


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
EXCHANGE_ID = os.getenv("EXCHANGE_ID", "binance")
REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")

logger = logging.getLogger(f"WalletCollector-{EXCHANGE_ID.capitalize()}")

async def collect_wallets():
    r = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)
    exchange_class = getattr(ccxt, EXCHANGE_ID)
    exchange = exchange_class({
        "enableRateLimit": True,
        "apiKey":os.getenv("API_KEY"),
        "secret":os.getenv("API_SECRET"),
    })
    logger.info(f"Connecting to {EXCHANGE_ID} to fetch currency networks ...")

    try:
        while True:
            try:
                #get all currencies with networks
                currencies = await exchange.fetch_currencies()

                if not currencies:
                    logger.warning(f"No currency data received from {EXCHANGE_ID}")
                    await asyncio.sleep(60)
                    continue

                pipe = r.pipeline()
                count = 0

                for code, data in currencies.items():
                    networks = {}
                    raw_networks = data.get('networks', {})

                    for net_id, net_data in raw_networks.items():
                        networks[net_id] = {
                            "deposit": net_data.get('deposit', False),
                            "withdraw": net_data.get('withdraw', False),
                            "fee": net_data.get('fee'),
                            "active": net_data.get('active', True)
                        }
                    if networks:
                        key = f"wallet:{EXCHANGE_ID}:{code}"
                        # use json to store dict in redis
                        pipe.set(key, json.dumps(networks))
                        pipe.expire(key, 600) # expire in 5 minutes
                        count += 1

                await pipe.execute()
                logger.info(f"Sucessfully updated status for {count} currencies")
            
            except Exception as e:
                logging.error(f"Error fetching currencies from {EXCHANGE_ID}: {e}")

            await asyncio.sleep(300) # wait 5 minutes before next update
    finally:
        await exchange.close()
        await r.close()

if __name__ == "__main__":
    asyncio.run(collect_wallets())
    






