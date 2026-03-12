import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

uri = os.environ["MONGO_URI"]
client = MongoClient(uri)

# Prefer explicit DB name if set; otherwise use the DB from the URI path.
env_db_name = (os.getenv("MONGO_DB_NAME") or "").strip()
default_db = client.get_default_database()
db_name = env_db_name or (default_db.name if default_db is not None else None)
if not db_name:
    raise RuntimeError("Could not determine database name. Set MONGO_DB_NAME in .env.")

db = client[db_name]
print("Connected. Database =", db.name)

collections = [c for c in db.list_collection_names() if not c.startswith("system.")]
print("Collections found:", ", ".join(collections) if collections else "(none)")

confirm = input(
    f"Type WIPE to delete ALL documents from {len(collections)} collections in '{db.name}': "
).strip()
if confirm != "WIPE":
    print("Aborted.")
    raise SystemExit(1)

total_deleted = 0
for name in collections:
    res = db[name].delete_many({})
    deleted = int(getattr(res, "deleted_count", 0) or 0)
    total_deleted += deleted
    print(f"- {name}: deleted {deleted}")

print(f"✅ Done. Total documents deleted: {total_deleted}")