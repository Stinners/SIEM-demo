import os
import uuid
from datetime import datetime
import logging as log
import asyncio
from abc import ABC, abstractmethod

from azure.storage.blob import BlobClient
from azure.eventhub.aio import EventHubConsumerClient
from azure.eventhub.extensions.checkpointstoreblobaio import BlobCheckpointStore
from jinja2 import Environment, FileSystemLoader, select_autoescape

DATE_BLOB_PATH = "%Y/%m/%d/%H"
#DATE_DISPLAY_STRING = "%H:%M:%S "
DATE_DISPLAY_STRING = "%X "

CONTAINER_NAME = "insights-logs-auditlogs"

def current_time(formater):
    return datetime.now().strftime(formater)

def make_name(basename: str, log_type: str):
    now = datetime.now().strftime(DATE_BLOB_PATH)
    id = str(uuid.uuid4())
    name = f"{log_type}/{now}/{basename}-{id}.json"
    return name

def test_send_logs(logs, log_type):
    return datetime.now().strftime(DATE_DISPLAY_STRING)


class AbstractAzureConnector(ABC):
    @abstractmethod
    def send_logs(self, logs: str, log_type):
        pass

    @abstractmethod
    async def eh_listener(self, queue): 
        pass

    async def eh_responder(self, request, queue, listener):
        """This captures events from the queue and renders them into a template, for use in Turbo Streams
        This function is structured to be used with starlette's EventSourceResponse class"""
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
    
    def start_eh_listener(self, request):
        queue = asyncio.Queue()
        listener = asyncio.create_task(self.eh_listener(queue))
        return self.eh_responder(request, queue, listener)


class TestAzureConnector(AbstractAzureConnector):
    """ Class for testing the frontend without touching azure"""
    def send_logs(self, logs, log_type):
        return datetime.now().strftime(DATE_DISPLAY_STRING)

    async def eh_listener(self, queue):
        for i in range(5):
            time = current_time(DATE_DISPLAY_STRING)
            await queue.put((f"Test Event {i}", time))
            await asyncio.sleep(2)


class AzureConnector(AbstractAzureConnector):
    def __init__(self) -> None:
        super().__init__()
        self.storage_connector = os.getenv("STORAGE_CONNECTION_STRING")
        self.event_connector = os.getenv("EVENT_CONNECTION_STRING")

    def send_logs(self, logs: str, log_type):
        name = make_name("test", log_type)
        try:
            client = BlobClient.from_connection_string(
                conn_str = self.storage_connector,
                container_name = CONTAINER_NAME,
                blob_name = name
            )
            data = bytes(logs, "utf-8")
            client.upload_blob(data)
        except:
            log.error("Could not get blob storage client, check the env variable STORAGE_CONNECTION_STRING is set")

        return datetime.now().strftime(DATE_DISPLAY_STRING)

    async def eh_listener(self, queue):
        """ This sets up a listener that captures events from the event hub and puts them into 
        an asyncio queue. It is intended to be used with 'eh_responder'"""
        checkpoint = BlobCheckpointStore.from_connection_string(
            self.storage_connector,
            "insights-logs-auditlogs", 
        )

        client = EventHubConsumerClient.from_connection_string(
            self.event_connector,
            consumer_group="$Default",
            eventhub_name="siem-test",
            checkpoint_store=checkpoint
        )

        async def handle_event(partition_context, event):
            event_text = event.body_as_str(encoding="UTF-8")
            time = current_time(DATE_DISPLAY_STRING)
            await queue.put((event_text, time))
            await partition_context.update_checkpoint(event)

        async with client:
            await client.receive(on_event=handle_event, starting_position="-1")