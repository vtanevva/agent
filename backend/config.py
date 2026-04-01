import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    GRAFIK_TOKEN = os.getenv("GRAFIK_TOKEN")

    GRAFIK_LIST_ID = os.getenv("GRAFIK_LIST_ID")
    GRAFIK_LIST2_ID = os.getenv("GRAFIK_LIST2_ID")
    GRAFIK_LIST3_ID = os.getenv("GRAFIK_LIST3_ID")

    SQLITE_PATH = os.getenv("SQLITE_PATH", "storage/aivis.db")

settings = Settings()

if not settings.GRAFIK_TOKEN:
    raise RuntimeError("GRAFIK_TOKEN is missing. Check your .env.")