import os
import json
from datetime import datetime

import pytz
from supabase import create_client
from dotenv import load_dotenv
from openai import OpenAI
from fasthtml.common import*


load_dotenv()

TIMESTAMP_FMT = "%Y-%m-%d %I:%M:%S %p KST"

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
app, rt = fast_app()
msgList = []

def gpt_call(msg, mode):

  messages = [
    {"role": "user", "content": msg}
  ]

  response = openai.chat.completions.create(
    model = "gpt-4o",
    messages = messages,
    response_format = {"type": mode},
    temperature = 0.1
  )

  return json.loads(response.choices[0].message.content), messages

def get_kst_time():
    kst_tz = pytz.timezone("Asia/Seoul")
    return datetime.now(kst_tz)

def add_task(context, data):
    supabase.table("task").insert(
        {"context": context, "data": data}
    ).execute()

def add_message(sender, content):
    timestamp = get_kst_time().strftime(TIMESTAMP_FMT)
    supabase.table("messages").insert(
        {"sender": sender, "content": content, "timestamp": timestamp}
    ).execute()

def get_messages():
    response = (
        supabase.table("messages").select("*").order("id", desc=False).execute()
    )
    return response.data

def get_prompts():
    response = (
        supabase.table("prompts").select("*").order("id", desc=False).execute()
    )
    return response.data

def get_prompt(prompt, context):
    response = (
        supabase.table(prompt).select("*").eq("name", context).execute()
    )
    return response.data[0]['content']

def render_process(entry):
    return Details(
        Summary(
            entry['name'],
            role="button",
            cls="secondary",
            id="process",
        ),
        P(entry['content']),
    )

def render_message(entry):
    return Article(
        Header(entry["name"]),
        P(entry['content']),
        Footer
    ),

def render_process_list():
    prompts = get_prompts()

    return Div(
        *[render_process(entry) for entry in prompts],
        id="process-list",
        style="overflow: scroll"
    )

def render_message_list():
    messages = get_messages()

    return Div(
        *[render_message(entry) for entry in messages],
        id="message-list",
        style="overflow: scroll"
    )

def render_content():
    header = Form(
        Fieldset(
            Label(
                "Context",
                Input(
                type="text",
                name="context",
                value=get_prompt("contexts", "food"),
                required=True,
                ),
            ),
            Label(
                "Data",
                Grid(
                    Select(
                        Option(
                            "food",
                        ),
                        Option(
                            "calendar",
                        ),
                        name="data",
                        required=True,
                    ),
                    Div(),
                    Div(),
                    Button("Submit", type="submit"),
                ),
            ),
            method="post",
            hx_post="/submit-context-data",
        ),
    ),

    footer = Form(
        Group(
            Input(
                type="text",
                name="message",
                placeholder="Type in your message",
                required=True
            ),
            Button("Send", type="submit"),
        ),
        method="post",
        hx_post="/submit-preference",
        hx_target="#message-list",
        hx_swap="outerHTML",
        hx_on__after_request="this.reset()",
    ),

    return Div(
        header,
        Hr(),
        render_process_list(),
        Hr(),
        render_message_list(),
        footer,
    )

@rt("/")
def get():
    return Titled("LLM Optimizer", render_content())

@rt("/submit-context-data", methods=["POST"])
def post(context: str, data: str):
    add_task(context, data)

@rt("/submit-preference", methods=["POST"])
def post(message: str):
    add_message("user", message)
    return render_process_list()

serve()