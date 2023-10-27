import logging
from utils.paths import mapPath
import os
from xmlrpc import client
import requests


class TorrentClient:
    "Base torrent client class"
    pathmaps: dict[str, str] = {}
    logger: logging.Logger
    label: str = ""
    name: str = "Torrent Client"

    def __init__(self, settings: dict) -> None:
        self.logger = logging.getLogger(__name__)
        if "pathmaps" in settings:
            self.pathmaps = settings["pathmaps"]
        if "label" in settings:
            self.label = settings["label"]

    def add(self, torrent_path: str, file_path: str) -> None:
        raise NotImplementedError()


class RTorrent(TorrentClient):
    """Implements rtorrent's XMLRPC protocol to
    allow adding torrents"""

    server: client.Server
    name: str = "rTorrent"

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
            uri = uri.replace(settings["password"], "[REDACTED]")
        self.logger.debug(f"Connecting to rtorrent at '{uri}'")

    def add(self, torrent_path: str, file_path: str) -> None:
        file_path = mapPath(file_path, self.pathmaps)
        dir = os.path.split(file_path)[0]
        self.logger.debug(f"Adding torrent {torrent_path} to directory {dir}")
        with open(torrent_path, "rb") as torrent:
            self.server.load.raw_verbose(
                "",
                client.Binary(torrent.read()),
                f"d.directory.set={dir}",
                f"d.custom1.set={self.label}",
                "d.check_hash=",
            )
        self.logger.info("Torrent added to rTorrent")


class Qbittorrent(TorrentClient):
    url: str
    username: str
    password: str
    cookies = None
    host: str = ""
    torrent_dir: str
    logged_in: bool = False
    name: str = "qBittorrent"

    def __init__(self, settings: dict) -> None:
        super().__init__(settings)
        ssl = settings["ssl"] if "ssl" in settings else False
        self.username = settings["username"]
        if "port" in settings:
            port = settings["port"]
        else:
            port = 443 if ssl else 8080
        self.url = f"http{'s' if ssl else ''}://{settings['host']}:{port}/api/v2"
        self.password = settings["password"] if "password" in settings else ""
        self.__login()

    def __login(self):
        path = "/auth/login"
        data = {"username": self.username, "password": self.password}
        r = requests.post(self.url + path, cookies=self.cookies, data=data)
        self.cookies = r.cookies
        self.logged_in = r.content.decode() == "Ok."
        if not self.logged_in:
            self.logger.error("Failed to login to qBittorrent")

    def add(self, torrent_path: str, file_path: str) -> None:
        if not self.logged_in:
            return
        file_path = mapPath(file_path, self.pathmaps)
        dir = os.path.split(file_path)[0]
        torrent_name = os.path.basename(torrent_path)
        path = "/torrents/add"
        options = {"paused": "true", "savepath": dir}
        if len(self.label) > 0:
            options["category"] = self.label
        with open(torrent_path, "rb") as f:
            r = requests.post(
                self.url + path,
                data=options,
                files={"torrents": (torrent_name, f, "application/x-bittorrent")},
                cookies=self.cookies,
                timeout=30,
            )
        if r.ok and r.content.decode() != "Fails.":
            self.logger.info("Torrent added to qBittorrent")
        else:
            self.logger.error("Failed to add torrent to qBittorrent")

    def recheck(self, infohash: str):
        if not self.logged_in:
            return
        path = "/torrents/recheck"
        requests.get(self.url, params={"hashes": infohash}, cookies=self.cookies, timeout=5)


class Deluge(TorrentClient):
    url: str
    password: str
    cookies = None
    host: str = ""
    name: str = "Deluge"

    def __init__(self, settings: dict) -> None:
        super().__init__(settings)
        ssl = settings["ssl"] if "ssl" in settings else False
        if "port" in settings:
            port = settings["port"]
        else:
            port = 443 if ssl else 8112
        self.url = f"http{'s' if ssl else ''}://{settings['host']}:{port}/json"
        self.password = settings["password"] if "password" in settings else ""
        self.__connect()

    def __connect(self):
        self.__login()
        result = requests.post(
            self.url,
            json={"method": "web.get_host_status", "params": [self.host], "id": 1},
            cookies=self.cookies,
            timeout=5,
        )
        j = result.json()
        if "result" in j:
            connected = j["result"] is not None and j["result"][1] == "Connected"
            if not connected:
                requests.post(
                    self.url,
                    json={"method": "web.connect", "params": [self.host], "id": 1},
                    cookies=self.cookies,
                    timeout=5,
                )

    def __login(self):
        if not self.connected():
            body = {"method": "auth.login", "params": [self.password], "id": 1}
            r = requests.post(self.url, json=body, cookies=self.cookies)
            self.cookies = r.cookies

    def connected(self) -> bool:
        result = requests.post(
            self.url, json={"method": "web.connected", "params": [], "id": 1}, cookies=self.cookies, timeout=5
        )
        j = result.json()
        if "result" in j and j["result"]:
            if len(self.host) == 0:
                result = requests.post(
                    self.url, json={"method": "web.get_hosts", "params": [], "id": 1}, cookies=self.cookies, timeout=5
                )
                j = result.json()
                if "result" in j:
                    self.host = j["result"][0][0]
            return True
        return False

    def add(self, torrent_path: str, file_path: str) -> None:
        file_path = mapPath(file_path, self.pathmaps)
        dir = os.path.split(file_path)[0]
        torrent_name = os.path.basename(torrent_path)

        with open(torrent_path, "rb") as f:
            r = requests.post(
                self.url.replace("/json", "/upload"),
                files={"file": (torrent_name, f, "application/x-bittorrent")},
                cookies=self.cookies,
                timeout=30,
            )
        j = r.json()
        self.logger.debug(f"Deluge response: {j}")
        if "success" in j and j["success"]:
            torrent_path = j["files"][0]
            body = {
                "method": "web.add_torrents",
                "params": [[{"path": torrent_path, "options": {"download_location": dir, "add_paused": True}}]],
                "id": 1,
            }
            try:
                result = requests.post(self.url, json=body, cookies=self.cookies, timeout=10)
                j = result.json()
                self.logger.debug(f"Deluge response: {j}")
                if "result" in j and j["result"][0][0]:
                    infohash = j["result"][0][1]
                    self.recheck(infohash)
                    self.logger.info("Torrent added to deluge")
                else:
                    self.logger.error(
                        f"Torrent uploaded to Deluge but failed to add: {j['error'] if 'error' in j and j['error'] else 'Unknown error'}"
                    )
            except requests.ReadTimeout:
                self.logger.error("Failed to add torrent to Deluge (does it already exist?)")
        else:
            self.logger.error("Failed to upload torrent to Deluge")

    def recheck(self, infohash: str):
        body = {"method": "core.force_recheck", "params": [[infohash]], "id": 1}
        requests.post(self.url, json=body, cookies=self.cookies, timeout=5)
