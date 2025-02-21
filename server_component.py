from datetime import datetime
import numpy as np
import pytz

TIMESTAMP_FMT = "%Y-%m-%d %I:%M:%S %p KST"

def get_kst_time():
    kst_tz = pytz.timezone("Asia/Seoul")
    return datetime.now(kst_tz)

def add_message(sender, content, sup_client):
    timestamp = get_kst_time().strftime(TIMESTAMP_FMT)
    sup_client.table("messages").insert(
        {"sender": sender, "content": content, "timestamp": timestamp}
    ).execute()

def get_messages(sup_client):
    response = (
        sup_client.table("messages").select("*").order("id", desc=False).execute()
    )
    return response.data

def get_prompts(sup_client):
    response = (
        sup_client.table("prompts").select("*").order("id", desc=False).execute()
    )
    return response.data

def min_max_normalize(column):
    return (column - np.min(column)) / (np.max(column) - np.min(column))