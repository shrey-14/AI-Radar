from storage.supabase_client import get_client

db = get_client()

# Insert a test row
response = db.table("ai_news").insert({
    "id": "test_001",
    "source": "anthropic",
    "source_display_name": "Anthropic",
    "url": "https://anthropic.com/test",
    "title": "Test article",
    "full_content": "Test content",
    "content_preview": "Test content",
    "word_count": 2,
}).execute()

print(response.data)

# Read it back
response = db.table("ai_news").select("*").eq("id", "test_001").execute()
print(response.data)

# Clean up
db.table("ai_news").delete().eq("id", "test_001").execute()
print("Connection working")