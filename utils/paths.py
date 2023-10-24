def mapPath(path: str, pathmaps: dict[str,str]) -> str:
    # Apply remote path mappings
    for remote in pathmaps:
        if not path.startswith(remote):
            continue
        local = pathmaps[remote]
        if remote[-1] != "/":
            remote += "/"
        if local[-1] != "/":
            local += "/"
        path = local + path.removeprefix(remote)
        break
    return path