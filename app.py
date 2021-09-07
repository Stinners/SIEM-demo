# Currently I can't connect to the event hub, research indicates this is a problem with
# not having access to particular ports


from fastapi import FastAPI, Request, Form, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import dotenv

import logging as log
import os
from os.path import splitext, join

from azure_connect import event_hub_listen, send_logs

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="./templates")
dotenv.load_dotenv()

LOGS_DIR = "dummy_logs"

log.basicConfig(level=log.DEBUG)

def get_file(path):
    path = join(LOGS_DIR, path)
    try:
        with open(path, 'r') as f:
                return f.read()
    except:
        log.error(f"Couldn't read target file: {path}")
        return ""

# NB target will not have the .json prefix
def get_dummy_logs(target="Custom"):
    """ Checks the folder 'dummy_logs' for json files, returns the list of
    log file names and the contents of the file "target", if target is set to
    None, returns the contents of the first file"""
    contents = os.listdir(LOGS_DIR)
    json_files = [f for f in contents if splitext(f)[-1] == ".json"]

    if len(json_files) == 0:
        log.debug(f"No .json files found in {LOGS_DIR}")
        return ([["Custom"], ""])

    if target == "Custom":
        text = ""
    else:
        target += ".json"
        text = get_file(target)

    files = [splitext(f)[0] for f in json_files] + ["Custom"]

    return (files, text)

@app.get("/examples/{active_log}", response_class=HTMLResponse)
def examples(request: Request, active_log: str):
    log_types, log_text = get_dummy_logs(target=active_log)
    context = {
        "request": request,
        "buttons": log_types,
        "contents": log_text,
        "active_button": active_log,
    }
    return templates.TemplateResponse("submit.html", context)

@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    return examples(request, "Custom")

@app.post("/send_event", response_class="HTMLResponse")
def submit(request: Request, log_text: str = Form(...), active_log: str = Form(...)):
    time = send_logs(log_text, active_log)
    print("GETTING TIME")
    context = {
        "request": request,
        "active_log": active_log,
        "log_text": log_text,
        "time": time
    }
    print("SERVING RESPONSE")
    return templates.TemplateResponse("results.html", context)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    await event_hub_listen(websocket)

@app.get("/listen")
async def sse_endpoint(request: Request):
    import azure_connect
    import asyncio
    loop = asyncio.get_event_loop()
    queue = asyncio.Queue()
    listener = loop.create_task(azure_connect.sse_listener(queue))
    return EventSourceResponse(azure_connect.sse_responder(request, queue, listener))
