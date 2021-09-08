import logging as log
import os
from os.path import splitext, join

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import dotenv
from sse_starlette.sse import EventSourceResponse

from azure_connect import send_logs, start_eh_listener

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
    context = {
        "request": request,
        "active_log": active_log,
        "log_text": log_text,
        "time": time
    }
    return templates.TemplateResponse("results.html", context)

@app.get("/listen")
async def sse_endpoint(request: Request):
    return EventSourceResponse(start_eh_listener(request))