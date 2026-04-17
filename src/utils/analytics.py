from pymongo import MongoClient
from datetime import datetime

client = MongoClient("mongodb://localhost:27017/")
db = client["aegis_ai"]

def track_event(event_type, user="guest"):
    db.analytics.insert_one({
        "event": event_type,
        "user": user,
        "timestamp": datetime.utcnow()
    })
