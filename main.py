import os
from datetime import datetime

import pytz
from supabase import create_client
from dotenv import load_dotenv
from fasthtml.common import*


load_dotenv()

TIMESTAMP_FMT = "%Y-%m-%d %I:%M:%S %p KST"

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
app, rt = fast_app()

def get_kst_time():
    kst_tz = pytz.timezone("Asia/Seoul")
    return datetime.now(kst_tz)

def add_message(name, message):
    timestamp = get_kst_time().strftime(TIMESTAMP_FMT)
    supabase.table("messages").insert(
        {"name": name, "message": message, "timestamp": timestamp}
    ).execute()

def get_messages():
    response = (
        supabase.table("messages").select("*").order("id", desc=True).execute()
    )
    return response.data

def render_message(entry):
    return Article(
        Header(f"Name: {entry['name']}"),
        P(entry['message']),
        Footer(Small(Em(f"Posted: {entry['timestamp']}"))),
    )

def render_message_list():
    messages = get_messages()

    return Div(
        *[render_message(entry) for entry in messages],
        id="message-list",
    )

def render_content():
    form = Form(
        Fieldset(
            Input(
                type="text",
                name="name",
                placeholder="Name",
                required=True,
                maxlength=15,
            ),
            Input(
                type="text",
                name="message",
                placeholder="Message",
                required=True,
                maxlength=50,
            ),
            Button("Submit", type="submit"),
            #role="group",
        ),
        method="post",
        hx_post="/submit-message",
        hx_target="#message-list",
        hx_swap="outerHTML",
        hx_on__after_request="this.reset()",
    )

    return Div(
        P(Em("Write something nice!")),
        form,
        Hr(),
        render_message_list()
    )

@rt("/")
def get():
    return Titled("LLM Optimizer", render_content())

@rt("/submit-message", methods=["POST"])
def post(name: str, message:str):
    add_message(name, message)
    return render_message_list()

serve()