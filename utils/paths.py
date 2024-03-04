import os


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


def get_dir_size(path):
    total = 0
    with os.scandir(path) as it:
        for entry in it:
            if entry.is_file():
                total += entry.stat().st_size
            elif entry.is_dir():
                total += get_dir_size(entry.path)
    return total
