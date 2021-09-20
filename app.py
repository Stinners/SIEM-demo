import logging as log
import os
from os.path import splitext, join
import json
import pathlib
from typing import Optional, Any
import asyncio

from fastapi import FastAPI, Request, Form 
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.logger import logger
from fastapi.templating import Jinja2Templates
import dotenv
from starlette.status import HTTP_303_SEE_OTHER

from azure_connect import AzureConnector, TestAzureConnector

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="./templates")
dotenv.load_dotenv()

LOGS_DIR = "dummy_logs"

if os.getenv("ENV") == 'prod':
    gunicorn_logger = log.getLogger('gunicorn.error')
    logger.handlers = gunicorn_logger.handlers
    logger.setLevel(gunicorn_logger.level)
    log = logger
else:
    log.basicConfig(level=log.WARNING)

if os.getenv("ENV") == 'prod':
    azure = AzureConnector()
else:
    azure = TestAzureConnector()

# Either returns the json object or None
def is_valid_json(text: str) -> Optional[Any]:
    try:
        return json.loads(text)
    except json.decoder.JSONDecodeError:
        return None

def repeat_logs(parsed, n):
    if type(parsed) == list:
        parsed *= n

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

@app.get("/put/logs")
def new_logs_form(request: Request):
    return templates.TemplateResponse("new_logs.html", {"request": request})

def check_path(path):
    name = os.path.join(LOGS_DIR, f"{path}.json")

    new_filepath = pathlib.Path(name)
    logs_dir = pathlib.Path(LOGS_DIR)

    if logs_dir == new_filepath.parent:
        print("Working")
        return name 
    else:
        print("Not working")
        raise Exception()


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

@app.post("/put/logs")
def new_log_file(request: Request, filename: str = Form(...), log_text: str = Form(...)):
    name = filename.strip()
    name = os.path.splitext(name)[0]
    try:
        cleaned = check_path(name)
        with open(cleaned, 'w') as f:
            f.write(log_text)
    except:
        name = "Custom"
    url_filename = os.path.splitext(filename)[0]
    return RedirectResponse(f"/examples/{name}", status_code=HTTP_303_SEE_OTHER)

@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    return examples(request, "Custom")

@app.post("/event")
def display_event(request: Request, 
                  active_log: str = Form(...),
                  log_text: str = Form(...),
                  repeat: int = Form(...)):
                  

    json_object = is_valid_json(log_text)
    if json_object:
        repeat_logs(json_object, repeat)
        log_text = json.dumps(json_object, indent=4, sort_keys=True)

    time = azure.send_logs(log_text, active_log)

    context = {
        "request": request,
        "active_log": active_log,
        "log_text": log_text,
        "time": time
    }
    return templates.TemplateResponse("results_poll.html", context)

@app.post("/send_event")
def submit(request: Request, 
           log_text: str = Form(...),
           active_log: str = Form(...)):
    return RedirectResponse("/event")

@app.post("/poll/subscribe")
async def listen():
    try: 
        app.queue 
    except AttributeError:
        app.queue = asyncio.Queue()
        asyncio.create_task(azure.eh_listener(app.queue))
    return {"listen": "started"}

async def get_events(queue, num_retries):
    events = []
    retries = 0 
    while retries < num_retries:
        try:
            print("Subscribing")
            next_event = queue.get_nowait()
            events.append(next_event)
        except asyncio.QueueEmpty:
            if events:
                break
            else:
                await asyncio.sleep(2)
                retries += 1 
    return events


@app.get("/poll/poll")
async def poll():
    try:
        app.queue
    except AttributeError:
        return {"poll": "not started"}

    events = await get_events(app.queue, num_retries=5)
    print("EVENTS")
    print(events)

    events = [azure.render_message(text, time) for (text, time) in events]
    return {"poll": "polling", "events": events}
