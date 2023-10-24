from venv import logger
from xmlrpc import client
from utils.paths import mapPath
import os
import logging

class TorrentClient:
    "Base torrent client class"
    pathmaps: dict[str,str] = {}
    logger: logging.Logger
    label: str = ""

    def __init__(self, settings: dict) -> None:
        self.logger = logging.getLogger(__name__)
        if "pathmaps" in settings:
            self.pathmaps = settings["pathmaps"]
        if "label" in settings:
            self.label = settings["label"]

    def add(self, torrent_path: str, file_path: str) -> None:
        raise NotImplementedError

class RTorrent(TorrentClient):
    """Implements rtorrent's XMLRPC protocol to
    allow adding torrents"""
    server: client.Server

    def __init__(self, settings: dict) -> None:
        super().__init__(settings)
        userstring = ""
        safe_userstring = ""
        if "username" in settings and len(settings["username"]) > 0:
            userstring = settings["username"]
            safe_userstring = userstring
            if "password" in settings and len(settings["password"]) > 0:
                userstring += ":" + settings["password"]
                safe_userstring += ":[REDACTED]"
            userstring += "@"
            safe_userstring += "@"
        host = settings["host"]
        ssl = settings["ssl"]
        if "port" not in settings:
            port = 443 if ssl else 8080
        else:
            port = settings["port"]
        uri = f"http{'s' if ssl else ''}://{userstring}{host}:{port}/{settings['path']}"
        self.server = client.Server(uri)
        if "password" in settings:
            uri = uri.replace(settings['password'], '[REDACTED]')
        self.logger.info(f"Connecting to rtorrent at '{uri}'")

    def add(self, torrent_path: str, file_path: str) -> None:
        file_path = mapPath(file_path, self.pathmaps)
        dir = os.path.split(file_path)[0]
        self.logger.debug(f"Adding torrent {torrent_path} to directory {dir}")
        with open(torrent_path, "rb") as torrent:
            self.server.load.raw_verbose("", client.Binary(torrent.read()), f"d.directory.set={dir}", f"d.custom1.set={self.label}", "d.check_hash=")
