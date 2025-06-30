import os

from loguru import logger


def mapPath(path: str, pathmaps: dict[str, str]) -> str:
    # Apply remote path mappings
    for remote, local in pathmaps.items():
        if not path.startswith(remote):
            continue
        if remote[-1] != "/":
            remote += "/"
        if local[-1] != "/":
            local += "/"
        path = local + path.removeprefix(remote)
        break
    return path


def delete_temp_file(path: str):
    logger.debug(f"Cleaning up temporary file {path}")
    os.remove(path)
