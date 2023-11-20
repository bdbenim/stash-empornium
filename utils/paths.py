def mapPath(path: str, pathmaps: dict[str,str]) -> str:
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