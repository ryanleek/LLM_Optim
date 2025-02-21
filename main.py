import os
import json
import string
import copy
import numpy as np

from supabase import create_client
from dotenv import load_dotenv
from openai import OpenAI
from ortools.linear_solver import pywraplp
from fasthtml.common import*

from server_component import add_message, get_messages, get_prompts, min_max_normalize


tlink = Script(src="https://cdn.tailwindcss.com")
dlink = Link(rel="stylesheet", href="https://cdn.jsdelivr.net/npm/daisyui@4.11.1/dist/full.min.css")

load_dotenv()
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
app, rt = fast_app(hdrs=(tlink, dlink, picolink))

with open('menu_vector.json', 'r') as f:
    json_data = json.load(f)

CONTEXT = ""
PROMPTS = get_prompts(supabase)
REQUESTS = []
PROCESSES = []
MESSAGES = []
API_MESSAGES = []
OPTIONS = ["food", "calendar"]
CLIENT = {
    "fin_features": [],
    "likes": [],
    "dislikes": [],
    "none": []
}
FEATURES = list(json_data[0]['features'].keys())
MENU = [([item['name']] + list(item['features'].values())) for item in json_data]
n = len(MENU)

DATA = np.array([item[1:] for item in MENU], dtype=float) 

for i in range(142, 152):
    DATA[:, i] = min_max_normalize(DATA[:, i])

def gpt_response(msgL, res_type, is_stream=True):

  return openai.chat.completions.create(
    model = "gpt-4o",
    messages = msgL,
    response_format = {"type": res_type},
    temperature = 0.1,
    stream=is_stream
)

def manage_features(solver, x, data, llm_response):
    objective = 0
    
    for response in llm_response:
        feature = response["name"]
        feat_type = response["type"]
        preference = response["pref"]

        feature_index = FEATURES.index(feature)

        if feat_type == "constraint":

            if preference == 1:
                # For each item i, if it's selected (x[i] = 1), it must satisfy the constraint
                for i in range(n):
                    solver.Add(x[i] <= data[i, feature_index])
            else:
                solver.Add(sum(x[i] * data[i, feature_index] for i in range(n)) == 0)

        else:
            objective += preference * sum(x[i] * data[i, feature_index] for i in range(n))

    solver.Maximize(objective)

def solve_sequentially(menu, data, llm_response, num_suggestions=5):
    selected_items = []
    excluded_items = []
    
    for _ in range(num_suggestions):
        # Reset solver for each iteration
        solver = pywraplp.Solver.CreateSolver("SCIP")
        n = len(menu)
        x = [solver.BoolVar(f'x[{i}]') for i in range(n)]
        
        # Add constraint to select exactly one item
        solver.Add(sum(x[i] for i in range(n)) == 1)
        
        # Exclude previously selected items
        for idx in excluded_items:
            solver.Add(x[idx] == 0)
            
        # Apply original constraints and objectives
        manage_features(solver, x, data, llm_response)
        
        # Solve
        status = solver.Solve()
        
        if status == pywraplp.Solver.OPTIMAL:
            # Find the selected item
            for i in range(n):
                if x[i].solution_value() == 1:
                    selected_items.append(menu[i][0])
                    excluded_items.append(i)
                    break
        else:
            break
            
    return selected_items

def add_new_features(client, response):
    prev = copy.deepcopy(client)

    client['likes'].extend(list(response['preferences']))
    client['dislikes'].extend(list(response['constraints']))

def form_prompt(p_idx, client=CLIENT):
    pTemp = PROMPTS[p_idx%4]

    if pTemp['name'] == "feat_extract":
        prompt = string.Template(pTemp['content']).substitute(context=CONTEXT, req=str(REQUESTS[-1]))

    elif pTemp['name'] == "feat_match":

        while True:
            if PROCESSES[p_idx-1]['generating'] == False:

                response = json.loads(PROCESSES[p_idx-1]['content'])

                add_new_features(client, response)
                client_feat = client['likes'] + client['dislikes']

                prompt = string.Template(pTemp['content']).substitute(cl_feat=str(client_feat), db_feat=str(FEATURES))
                break

    elif pTemp['name'] == "feat_cat":

        while True:
            if PROCESSES[p_idx-1]['generating'] == False:
                response = json.loads(PROCESSES[p_idx-1]['content'])

                client_feat = client['likes'] + client['dislikes']

                for feat in response["result"]:

                    if feat["db_name"] == "none":
                        client["none"].append(feat["feature"])
                        continue

                    else:
                        temp = {'name': feat["feature"]}

                        if temp in client["likes"]:
                            client["likes"].remove(temp)
                            client["likes"].append({'name': feat["db_name"]})
                        else:
                            client["dislikes"].remove(temp)
                            client["dislikes"].append({'name': feat["db_name"]})
                
                prompt = string.Template(pTemp['content']).substitute(req = str(REQUESTS), pref = str(CLIENT["likes"]), const = str(CLIENT["dislikes"]))
                break

    elif pTemp['name'] == "recommend":
        while True:
            if PROCESSES[p_idx-1]['generating'] == False:

                response = json.loads(PROCESSES[p_idx-1]['content'])

                client["fin_features"].extend(list(response["result"]))
                ranked_suggestions = solve_sequentially(MENU, DATA, client["fin_features"])

                prompt = string.Template(pTemp['content']).substitute(msg = str(REQUESTS), menu = str(ranked_suggestions))
                break


    else:
        prompt = "Write error message in json format."

    return [{"role": "user", "content": prompt}]

def Process(pcs_idx):
    pcs = PROCESSES[pcs_idx]
    text = "..." if pcs['content'] == "" else pcs['content']
    generating = 'generating' in PROCESSES[pcs_idx] and PROCESSES[pcs_idx]['generating']
    stream_args = {"hx_trigger": "every 0.1s", "hx_swap": "outerHTML", "hx_get": f"/pcs/{pcs_idx}"}
    
    return Details(
        Summary(
            PROMPTS[pcs_idx%4]['name'],
            Span(
                aria_busy="true" if generating else "false",
            ),
            role="button",
            cls="secondary",
        ),
        P(text),
        id=f"pcs-{pcs_idx}",
        **stream_args if generating else {},
        open=True
    )

@app.get("/pcs/{pcs_idx}")
def get_Process(pcs_idx:int):
    if pcs_idx >= len(PROCESSES): return ""
    return Process(pcs_idx)

@app.get("/pcs-list")
def get_ProcessList():
    return Div(*[Process(len(PROCESSES) - 4 + i) for i in range(4)])

def Message(msg_idx):
    msg = MESSAGES[msg_idx]
    text = "..." if msg['content'] == "" else msg['content']

    bubble_class = "chat-bubble-primary" if msg['role'] == 'user' else "chat-bubble"
    chat_class = "chat-end" if msg['role'] == 'user' else "chat-start"
    generating = 'generating' in MESSAGES[msg_idx] and MESSAGES[msg_idx]['generating']
    not_process = msg['role'] == 'user' or not ('process' in MESSAGES[msg_idx] and MESSAGES[msg_idx]['process'])
    below_process = 'process' in MESSAGES[msg_idx-1] and MESSAGES[msg_idx-1]['process']
    stream_args = {"hx_trigger": "every 0.1s", "hx_swap": "innerHTML", "hx_get": f"/msg/{msg_idx}"}
    return Div(
        Div() if below_process else Div(msg['role'], cls="chat-header") ,
        Div(text, cls=f"chat-bubble {bubble_class}") if not_process else
        Div(
            Div(*[Process(len(PROCESSES) - 4 + i) for i in range(4)],
                id=f"pcs-list-{len(PROCESSES)%4}",
                #hx_trigger= "click[event.target.matches('button')] from:body delay:3s",
                hx_trigger= "every 3s",
                hx_swap= "innerHTML", 
                hx_get= "pcs-list",
            ),
            cls=f"chat-bubble {bubble_class}"
        ),
        #Footer(Small(Em(f"Date: {entry['timestamp']}"))),
        cls = f"chat {chat_class}",
        id = f"msg-{msg_idx}",
        **stream_args if generating else {}
    )

@app.get("/msg/{msg_idx}")
def get_Message(msg_idx:int):
    if msg_idx >= len(MESSAGES): return ""
    return Message(msg_idx)

@app.get("/msg-list")
def get_MessageList():
    return Div(*[Message(i) for i in range(len(MESSAGES))])

def ChatInput():
    return Input(
        type="text",
        name="user_input",
        cls="input input-lg input-bordered w-full",
        id="msg-input",
        placeholder="Type in your message",
        required=True,
        hx_swap_oob="true"
    )

def render_content():
    header = Form(
        Input(
            type="text",
            cls="input input-lg input-bordered w-full",
            id="context-input",
            name="context",
            value="You work at a shopping mall food court. The food court has 20 vendors with total 200 menu items. You are trying to optimize client's choice of menu.",
            required=True,
        ),
        Select(
            *[Option(opt) for opt in OPTIONS],
            name="data",
            required=True,
            cls="select select-bordered w-60"
        ),
        Button(
            "Submit",
            cls="btn btn-primary"
        ),
        cls="flex space-x-2 mt-2 join",

        method="post",
        hx_post="/submit-context",
        hx_target="#context-input",
        hx_swap="innerHTML",
        hx_on__after_request="this.reset()",
    )
    footer = Form(
    
        ChatInput(),
        Button("Send", cls="btn btn-primary"),

        hx_post="/intent-check",
        #hx_target=f"#pcs-list-{len(PROCESSES)%4}",
        hx_target="#msg-list",
        hx_swap="beforeend",
        cls="join"
    )

    return Body(
        H1("LLM Optimizer", cls="text-4xl font-extrabold"),
        header,
        Div(
            Div(*[Message(i) for i in range(len(MESSAGES))],
                id="msg-list",
                hx_trigger= "every 2s",
                hx_swap= "innerHTML", 
                hx_get= "msg-list"
            ),
            cls="mb-auto overflow-auto p-4",
        ),
        footer,
        cls="p-4 h-screen flex flex-col"
    )

@rt("/")
def home():
    return Title("LLM Optimizer"), render_content()

@rt("/submit-context", methods=["POST"])
def update_context(context: str, data: str):
    CONTEXT = context
    #print(CONTEXT)
    #DATA = data

@threaded
def add_chunk(response, r_list, idx):
    for chunk in response: 
        if chunk.choices[0].delta.content is not None:
            r_list[idx]["content"] += chunk.choices[0].delta.content

    r_list[idx]["generating"] = False


@app.post("/intent-check")
def post(user_input: str):
    m_idx = len(MESSAGES)
    MESSAGES.append({"role": "user", "content": user_input})
    API_MESSAGES.append({"role": "user", "content": user_input})
    #add_message("user", message, supabase)

    intent_check = [
        {"role": "user", "content": """
        Determine whether the user's intention is either one of the following.
            1. Request: informing or investigating their preference or dislikes.
            2. General: general conversation that does not fall into Request.
        If any part of the user's message contains Request, simply reply "request".
        If it doesn't, respond with "general".
        Do not give any explanation or interact with user's message.
        """},
        {"role": "assistant", "content": "Ok"},
        {"role": "user", "content": user_input}
    ]

    response = gpt_response(intent_check, "text", is_stream=False)
    verdict = response.choices[0].message.content

    if verdict == "request":

        MESSAGES.append({"role": "assistant", "content": "", "generating": False, "process": True})

        p_idx = len(PROCESSES)
        REQUESTS.append(user_input)

        for _ in range(len(PROMPTS)):
            PROCESSES.append({"role": "assistant", "content": "", "generating": True})

        for i in range(len(PROMPTS)):
            response = gpt_response(form_prompt(p_idx+i), "json_object")
            add_chunk(response, PROCESSES, p_idx+i)

        #from here should be executed after every generating is true

        response = gpt_response(API_MESSAGES, "text") #add response based on process result

        MESSAGES.append({"role": "assistant", "content": "", "generating": True, "process": False})
        add_chunk(response, MESSAGES, m_idx+2)

        API_MESSAGES.append({"role": "assistant", "content": MESSAGES[-1]["content"]})

    elif verdict == "general":
        response = gpt_response(API_MESSAGES, "text")

        MESSAGES.append({"role": "assistant", "content": "", "generating": True, "process": False})
        add_chunk(response, MESSAGES, m_idx+1)

        API_MESSAGES.append({"role": "assistant", "content": ""})

    else:
        MESSAGES.append({"role": "assistant", "content": "Sorry something went wrong. Please try again.", "generating": False, "process": False})
        API_MESSAGES.append({"role": "assistant", "content": "Sorry something went wrong. Please try again.", "generating": False, "process": False})

    return ChatInput()

serve()