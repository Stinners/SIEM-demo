
import os
import logging

from fastapi.logger import logger

is_gunicorn = "gunicorn" in os.environ.get("SERVER_SOFTWARE", "")

def get_logger():
    # Using guniron the log level is passed using the --log_level flag on startup 
    if is_gunicorn:
        gunicorn_logger = logging.getLogger('gunicorn.error')
        logger.handlers = gunicorn_logger.handlers
        logger.setLevel(gunicorn_logger.level)
        return logger
    # Using anything else we are probably not in production so use 
    # debug as the default
    else:
        logging.basicConfig(level=logging.DEBUG)
        return logging

