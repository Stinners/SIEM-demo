import logging as log
import os
from os.path import splitext, join
import json
from typing import Optional, Any

from fastapi import FastAPI, Request, Form 
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm, oauth2
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import dotenv
from sse_starlette.sse import EventSourceResponse

from azure_connect import AzureConnector, TestAzureConnector

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="./templates")
dotenv.load_dotenv()

LOGS_DIR = "dummy_logs"

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

@app.post("/event")
def display_event(request: Request, 
                  active_log: str = Form(...),
                  log_text: str = Form(...),
                  repeat: int = Form(...)):
                  

    if json_object := is_valid_json(log_text):
        repeat_logs(json_object, repeat)
        log_text = json.dumps(json_object, indent=4, sort_keys=True)

    time = azure.send_logs(log_text, active_log)

    context = {
        "request": request,
        "active_log": active_log,
        "log_text": log_text,
        "time": time
    }
    return templates.TemplateResponse("results.html", context)

@app.post("/send_event")
def submit(request: Request, 
           log_text: str = Form(...),
           active_log: str = Form(...)):
    return RedirectResponse("/event")

@app.get("/listen")
async def sse_endpoint(request: Request):
    return EventSourceResponse(azure.start_eh_listener(request))
