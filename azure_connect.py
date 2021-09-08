import os
import uuid
from datetime import datetime
import logging as log
import asyncio

from azure.storage.blob import BlobClient
from azure.eventhub.aio import EventHubConsumerClient, EventHubSharedKeyCredential
from azure.eventhub.extensions.checkpointstoreblobaio import BlobCheckpointStore
from azure.eventhub import TransportType
from jinja2 import Environment, FileSystemLoader, select_autoescape

DATE_BLOB_PATH = "%Y/%m/%d/%H/"
DATE_DISPLAY_STRING = "%H:%M %S"

log_type_to_container = {
    "AAD": "insights-logs-auditlogs",
    "Linux": "insights-logs-auditlogs",
    "Custom": "insights-logs-auditlogs",
}

def current_time(formater):
    return datetime.now().strftime(formater)

def make_name(basename: str):
    now = datetime.now().strftime(DATE_BLOB_PATH)
    now = datetime.now().strftime(DATE_BLOB_PATH)
    id = str(uuid.uuid4())
    name = now + basename + "-" + id + ".json"
    return name

def send_logs(logs: str, log_type: str):
    name = make_name("test")
    container = log_type_to_container[log_type]
    try:
        client = BlobClient.from_connection_string(
            conn_str = os.getenv("STORAGE_CONNECTION_STRING"),
            container_name = container,
            blob_name = name
        )
    except:
        log.error(os.getenv("STORAGE_CONNECTION_STRING"))
        log.error("Could not get blob storage client, check the env variable STORAGE_CONNECTION_STRING is set")

    data = bytes(logs, "utf-8")
    client.upload_blob(data)

    return datetime.now().strftime(DATE_DISPLAY_STRING)

async def eh_listener(queue):
    event_connection = os.getenv("EVENT_CONNECTION_STRING")
    storage_connection = os.getenv("STORAGE_CONNECTION_STRING")

    checkpoint = BlobCheckpointStore.from_connection_string(
        storage_connection,
         "insights-logs-auditlogs", # TODO work out if this is an appropriate store
    )

    client = EventHubConsumerClient.from_connection_string(
        event_connection,
        consumer_group="$Default",
        eventhub_name="siem-test",
        #checkpoint_store=checkpoint
    )

    async def handle_event(partition_context, event):
        event_text = event.body_as_str(encoding="UTF-8")
        time = current_time(DATE_DISPLAY_STRING)
        await queue.put((event_text, time))
        #await partition_context.update_checkpoint(event)

    async with client:
        await client.receive(on_event=handle_event, starting_position="-1")

async def eh_responder(request, queue, listener):
    template_env = Environment(
        loader=FileSystemLoader("templates"),
        autoescape=select_autoescape()
    )

    template = template_env.get_template("message.html")

    while True:
        if await request.is_disconnected():
            listener.cancel()
            break

        text, time = await queue.get()
        response = template.render(message_content=text, time=time)
        yield response

def start_eh_listener(request):
    queue = asyncio.Queue()
    listener = asyncio.create_task(eh_listener(queue))
    return eh_responder(request, queue, listener)




