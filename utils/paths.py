import os
from pathlib import Path, PureWindowsPath

from loguru import logger


def normalize_path(path: str) -> Path:
    """Convert both Windows and POSIX paths to normalized Path objects."""
    return Path(PureWindowsPath(path).as_posix())


def remap_path(original_path: str, path_mappings: dict[str, str]) -> str:
    """Remap paths using a dictionary of mount points"""
    original_path = normalize_path(original_path)

    for container_mount, host_mount in path_mappings.items():
        container_mount = normalize_path(container_mount)
        try:
            relative_path = original_path.relative_to(container_mount)
            return str(normalize_path(host_mount) / relative_path)
        except ValueError:
            # Path is not relative to this mount point
            continue

    # No mapping found, return original
    return str(original_path)


def delete_temp_file(path: str | Path) -> None:
    logger.debug(f"Cleaning up temporary file {path}")
    try:
        os.remove(path)
    except FileNotFoundError:
        logger.debug(f"File {path} does not exist")
        pass
    except PermissionError:
        logger.error(f"Could not delete temporary file {path}: Permission denied")


def verify_scene(stash_file: dict) -> tuple[bool, str]:
    if not os.path.isfile(stash_file["path"]):
        return False, f"Couldn't find file {stash_file['path']}"

    try:
        with open(stash_file["path"], "r") as f:
            pass
    except PermissionError:
        return False, f"Permission denied: {stash_file['path']}"

    # Warn user if file size reported by stash doesn't match actual file size
    file_size = os.path.getsize(stash_file["path"])
    if file_size != stash_file["size"]:
        logger.warning(f"File size mismatch: {file_size} != {stash_file['size']}")

    return True, "Success"