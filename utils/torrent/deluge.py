from unittest import result
from utils.torrent.torrentclient import TorrentClient
from utils.paths import mapPath
import os
import requests

class Deluge(TorrentClient):
    url: str
    password: str
    cookies = None
    host: str = ""
    torrent_dir: str

    def __init__(self, settings: dict) -> None:
        super().__init__(settings)
        ssl = settings["ssl"] if "ssl" in settings else False
        if "port" in settings:
            port = settings["port"]
        else:
            port = 443 if ssl else 8112
        self.url = f"http{'s' if ssl else ''}://{settings['host']}:{port}/json"
        self.password = settings["password"] if "password" in settings else ""
        if "torrent_directory" not in settings:
            self.logger.error("Deluge requires a directory to check for torrent files")
            raise ValueError()
        self.torrent_dir = settings["torrent_directory"]
        self.__connect()
    
    def __connect(self):
        self.__login()
        result = requests.post(self.url, json={"method": "web.get_host_status", "params": [self.host], "id": 1}, cookies=self.cookies, timeout=5)
        j = result.json()
        if "result" in j:
            connected = j["result"] is not None and j["result"][1] == "Connected"
            if not connected:
                requests.post(self.url, json={"method": "web.connect", "params": [self.host], "id": 1}, cookies=self.cookies, timeout=5)

    def __login(self):
        if not self.connected():
            body = {
                "method": "auth.login",
                "params": [self.password],
                "id": 1
            }
            r = requests.post(self.url, json=body, cookies=self.cookies)
            self.cookies = r.cookies
    
    def connected(self) -> bool:
        result = requests.post(self.url, json={"method": "web.connected", "params": [], "id": 1}, cookies=self.cookies, timeout=5)
        j = result.json()
        if "result" in j and j["result"]:
            if len(self.host) == 0:
                result = requests.post(self.url, json={"method": "web.get_hosts", "params": [], "id": 1}, cookies=self.cookies, timeout=5)
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
            r = requests.post(self.url.replace("/json", "/upload"), files={"file":(torrent_name, f, 'application/x-bittorrent')}, cookies=self.cookies, timeout=30)
        j = r.json()
        self.logger.debug(f"Deluge response: {j}")
        if "success" in j and j["success"]:
            torrent_path = j["files"][0]
            body = {
                "method": "web.add_torrents",
                "params": [
                    [{
                        "path": torrent_path,
                        "options": {
                            "download_location": dir,
                            "add_paused": True
                        }
                    }]
                ],
                "id": 1
            }
            try:
                result = requests.post(self.url, json=body, cookies=self.cookies, timeout=10)
                j = result.json()
                self.logger.debug(f"Deluge response: {j}")
                if "result" in j and j["result"][0][0]:
                    self.logger.info("Torrent added to deluge")
                else:
                    self.logger.error(f"Torrent uploaded to Deluge but failed to start: {j['error'] if 'error' in j and j['error'] else 'Unknown error'}")
            except requests.ReadTimeout:
                self.logger.error("Failed to start Deluge torrent (does it already exist?)")
        else:
            self.logger.error("Failed to upload torrent to Deluge")