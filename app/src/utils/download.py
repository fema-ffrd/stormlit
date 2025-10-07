import os
import zipfile
from datetime import datetime


def create_session_directory(base_directory: str) -> str:
    """
    Creates a session directory with a unique name based on the current timestamp.

    Args:
        base_directory (str): The base directory where the session directory will be created.

    Returns:
        str: The path to the created session directory.
    """
    session_id = datetime.now()
    session_id_str = session_id.strftime("%Y_%b_%d_%H_%M_%S_%f")
    session_directory = os.path.join(base_directory, "session_" + session_id_str)
    if not os.path.exists(session_directory):
        os.makedirs(session_directory)
    return session_directory


def compress_directory(session_directory: str, output_zip_file: str) -> str:
    """
    Compresses the contents of a directory into a zip file.

    Args:
        session_directory (str): The path to the session directory to compress.
        output_zip_file (str): The path where the zip file will be saved.

    Returns:
        str: The path to the created zip file.
    """
    with zipfile.ZipFile(output_zip_file, "a") as zf:
        for dirname, subdirs, files in os.walk(session_directory):
            for filename in files:
                file_path = os.path.join(dirname, filename)
                arcname = os.path.relpath(file_path, session_directory)
                zf.write(file_path, arcname=arcname)
    os.rmdir(session_directory)
    return output_zip_file
