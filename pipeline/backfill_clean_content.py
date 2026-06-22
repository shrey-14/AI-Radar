# pipeline/backfill_clean_content.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prompts import clean_article_content
from storage.supabase_client import get_client

def backfill():
    db = get_client()
    records = db.table("ai_news").select("id,full_content").execute().data or []
    print(f"Backfilling {len(records)} records...")
    for r in records:
        raw = r.get("full_content", "")
        if not raw:
            continue
        cleaned = clean_article_content(raw)
        db.table("ai_news").update({"full_content": cleaned}).eq("id", r["id"]).execute()
    print("Done.")

if __name__ == "__main__":
    backfill()