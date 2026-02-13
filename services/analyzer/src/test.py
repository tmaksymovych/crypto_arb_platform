from dotenv import load_dotenv
import os
load_dotenv()

raw_ids = os.getenv("CHAT_IDS")
CHAT_IDS = [int(x) for x in raw_ids.split(",")]

for el in CHAT_IDS:
    print(el, type(el))