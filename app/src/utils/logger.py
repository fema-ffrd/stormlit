import glob
import inspect
import json
import logging
import os
import shutil
import traceback
from collections import defaultdict
from typing import Any, Dict

import pandas as pd
import streamlit as st


class LogFormatter(logging.Formatter):
    def __init__(self, log_type: str):
        self.log_type = log_type

    def format(self, record):
        # Get the function name of the caller
        stack = inspect.stack()
        # Start from 1 to skip the current frame
        for frame_info in stack[1:]:
            if frame_info.function != "log":
                record.funcName = frame_info.function
                break

        log_entry = {
            "@type": self.log_type,
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "msg": record.getMessage(),
            "logger_name": record.name,
            "function_name": record.funcName,
            "line_number": record.lineno,
            "filename": record.pathname,
            "error": None,
            "traceback": None,
        }

        if record.exc_info:
            log_entry["error"] = str(record.exc_info[1])
            log_entry["traceback"] = traceback.format_exc()

        return json.dumps(log_entry)


def setup_logging(
    log_type: str, log_level: int = logging.INFO, log_to_file: bool = False, log_file_path: str = "log.json"
):
    """
    Sets up logging for the application. Configures log levels for ripple1d and main script.
    """
    logger = logging.getLogger()
    logger.setLevel(log_level)

    formatter = LogFormatter(log_type)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    if log_to_file:
        file_handler = logging.FileHandler(log_file_path)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)


def log(
    level: int,
    msg: Dict[str, Any] = None,
    error: Exception = None,
    include_traceback: bool = True,
):
    """
    Logs a custom msg for ripple production with the specified log level.
    """
    logger = logging.getLogger()
    # if isinstance(msg, dict) and "func" in msg.keys():
    #     func = msg["func"].__name__

    log_entry = {
        "msg": msg or {},
    }

    if level >= logging.ERROR and error:
        log_entry["error"] = str(error)
        if include_traceback:
            log_entry["traceback"] = traceback.format_exc()

    logger.log(level, log_entry)


def move_existing_logs(log_dir):
    log_files = glob.glob(os.path.join(log_dir, "*.jsonld"))
    if log_files:
        dep_logs_dir = os.path.join(log_dir, "archive")
        os.makedirs(dep_logs_dir, exist_ok=True)
        for log_file in log_files:
            shutil.move(log_file, os.path.join(dep_logs_dir, os.path.basename(log_file)))


def find_huey_log(log_dir):
    log_files = glob.glob(os.path.join(log_dir, "*huey.jsonld"))
    st.write(log_files)
    if log_files:
        return log_files[0]
    else:
        if log_dir == "":
            st.warning("Please update the working directory to search for logs")
        else:
            st.warning(f"No *huey.jsonld files found in {log_dir}.")
        return None


def read_logs(log_file):
    try:
        with open(log_file, "r") as file:
            return file.readlines()
    except Exception as e:
        st.error(f"Failed to read logs: {e}")
        return []


def parse_logs_to_dict(logs: str) -> dict:
    log_dict = defaultdict(list)

    for line in logs:
        log_entry = json.loads(line)
        level = log_entry.get("level")
        log_dict[level].append(log_entry)

    return dict(log_dict)


def logs_to_dataframe(log_entries: list, all_columns: bool = True) -> pd.DataFrame:
    processed_logs = []

    for log_entry in log_entries:
        # If the 'msg' field is a string that looks like a dictionary, convert it
        if isinstance(log_entry["msg"], str):
            try:
                msg_dict = eval(log_entry["msg"])
                if isinstance(msg_dict, dict) and "msg" in msg_dict:
                    log_entry.update(msg_dict["msg"])

                    # Check for 'error' and 'traceback' keys and include them
                    if "error" in msg_dict:
                        log_entry["error"] = msg_dict["error"]
                    if "traceback" in msg_dict:
                        log_entry["traceback"] = msg_dict["traceback"]

                    del log_entry["msg"]
                else:
                    log_entry["message"] = log_entry["msg"]
                    del log_entry["msg"]
            except (SyntaxError, ValueError):
                log_entry["message"] = log_entry["msg"]
                del log_entry["msg"]
        else:
            log_entry["message"] = log_entry["msg"]
            del log_entry["msg"]

        processed_logs.append(log_entry)

    df = pd.DataFrame(processed_logs)
    if all_columns:
        return df
    else:
        return df.drop(columns=["@type", "level", "link"], errors="ignore")
