from email import header
from venv import logger
from utils.torrent.torrentclient import TorrentClient
from utils.paths import mapPath
import os
import requests

class Qbittorrent(TorrentClient):
    url: str
    username: str
    password: str
    cookies = None
    host: str = ""
    torrent_dir: str
    logged_in: bool = False

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
        data = {
            "username": self.username,
            "password": self.password
        }
        r = requests.post(self.url+path, cookies=self.cookies, data=data)
        self.cookies = r.cookies
        self.logged_in = r.content.decode() == "Ok."
        if not self.logged_in:
            logger.error("Failed to login to qBittorrent")
    
    def add(self, torrent_path: str, file_path: str) -> None:
        if not self.logged_in:
            return
        file_path = mapPath(file_path, self.pathmaps)
        dir = os.path.split(file_path)[0]
        torrent_name = os.path.basename(torrent_path)
        path = "/torrents/add"
        options = {
            "paused": "true",
            "savepath": dir
        }
        if len(self.label) > 0:
            options["category"] = self.label
        with open(torrent_path, "rb") as f:
            r = requests.post(self.url+path, data=options, files={"torrents":(torrent_name, f, 'application/x-bittorrent')}, cookies=self.cookies, timeout=30)
        if r.ok and r.content.decode() != "Fails.":
            self.logger.info("Torrent added to qBittorrent")
        else:
            self.logger.error("Failed to add torrent to qBittorrent")
    
    def recheck(self, infohash: str):
        if not self.logged_in:
            return
        path = "/torrents/recheck"
        requests.get(self.url, params={"hashes": infohash}, cookies=self.cookies, timeout=5)
