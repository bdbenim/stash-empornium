import hashlib
from hmac import digest
import logging
from multiprocessing import process
import os
import re
import requests
import subprocess
import tempfile
import time
from token import OP
from typing import Any, Optional
import uuid

from PIL import Image, ImageSequence

logger = logging.getLogger(__name__)
use_redis = False
try:
    import redis

    use_redis = True
except:
    logger.info("Redis module not found, using local caching only")

CHUNK_SIZE = 5000
PERFORMER_DEFAULT_IMAGE = "https://jerking.empornium.ph/images/2023/10/10/image.png"
STUDIO_DEFAULT_LOGO = "https://jerking.empornium.ph/images/2022/02/21/stash41c25080a3611b50.png"
PREFIX = "stash-empornium"
HASH_PREFIX = f"{PREFIX}-file"

class ImageHandler:
    urls: dict = {}
    digests: dict[str, dict[str,list[str]]] = {}
    redis = None
    no_cache: bool = False
    overwrite: bool = False

    cookies = None
    img_host_token: str

    def __init__(
        self,
        redisHost: str | None = None,
        redisPort: int = 6379,
        user: str | None = None,
        password: str | None = None,
        use_ssl: bool = False,
        no_cache: bool = False,
        overwrite: bool = False,
    ) -> None:
        self.overwrite = overwrite
        if not no_cache and redisHost is not None and use_redis:
            self.redis = redis.Redis(
                redisHost, redisPort, username=user, password=password, ssl=use_ssl, decode_responses=True
            )
            try:
                self.redis.exists("connectioncheck")
                logger.info(
                    f"Successfully connected to redis at {redisHost}:{redisPort}{' using ssl' if use_ssl else ''}"
                )
            except Exception as e:
                logger.error(f"Failed to connect to redis: {e}")
                self.redis = None
        else:
            logger.debug("Not connecting to redis")
        self.no_cache = no_cache
        self.__connectionInit()

    def __connectionInit(self):
        img_host_request = requests.get("https://jerking.empornium.ph/json")
        m = re.search(r"config\.auth_token\s*=\s*[\"'](\w+)[\"']", img_host_request.text)
        try:
            assert m is not None
        except:
            logger.critical("Unable to get auth token for image host.")
            raise
        self.img_host_token = m.group(1)
        self.cookies = img_host_request.cookies
        self.cookies.set("AGREE_CONSENT", "1", domain="jerking.empornium.ph", path="/")
        self.cookies.set("CHV_COOKIE_LAW_DISPLAY", "0", domain="jerking.empornium.ph", path="/")

    def img_host_upload(
        self,
        img_path: str,
        img_mime_type: str,
        image_ext: str,
        width: int = 0,
        default: str = STUDIO_DEFAULT_LOGO,
    ) -> tuple[str|None,str|None]:
        """Upload an image and return the URL, or None if there is an error. Optionally takes
        a width, and scales the image down to that width if it is larger."""
        logger.debug(f"Uploading image from {img_path}")

        # Return default image if unknown
        if image_ext == "unk":
            return default,None

        # Return cached url if available
        digest = ""
        if width == 0:
            with open(img_path, "rb") as f:
                digest = hashlib.file_digest(f, hashlib.md5).hexdigest()
            url = self.get(digest)
            if url is not None:
                logger.debug(f"Found url {url} in cache")
                return url,digest

        # Convert animated webp to gif
        if img_mime_type == "image/webp":
            if self.isWebpAnimated(img_path):
                with Image.open(img_path) as img:
                    img_path = img_path.strip(image_ext) + "gif"
                    img.save(img_path, save_all=True)
                img_mime_type = "image/gif"
                image_ext = "gif"
            else:
                with Image.open(img_path) as img:
                    img_path = img_path.strip(image_ext) + "png"
                    img.save(img_path)
                img_mime_type = "image/png"
                image_ext = "png"
            logger.debug(f"Saved image as {img_path}")

        if width > 0:
            with Image.open(img_path) as img:
                img.thumbnail((width, img.height))
                img.save(img_path)
                logger.debug(f"Resized image to {img.width}x{img.height}")
            with open(img_path, "rb") as f:
                digest = hashlib.file_digest(f, hashlib.md5).hexdigest()
            url = self.get(digest)
            if url is not None:
                logger.debug(f"Found url {url} in cache")
                return url,digest

        # Quick and dirty resize for images above max filesize
        if os.path.getsize(img_path) > 5000000:
            CMD = ["ffmpeg", "-i", img_path, "-vf", "scale=iw:ih", "-y", img_path]
            proc = subprocess.run(CMD, stderr=subprocess.PIPE, stdout=subprocess.STDOUT, text=True)
            logger.debug(f"ffmpeg output:\n{proc.stdout}")
            while os.path.getsize(img_path) > 5000000:
                with Image.open(img_path) as img:
                    img.thumbnail((int(img.width * 0.95), int(img.height * 0.95)), Image.LANCZOS)
                    img.save(img_path)
            logger.debug(f"Resized {img_path}")

        files = {
            "source": (
                str(uuid.uuid4()) + "." + image_ext,
                open(img_path, "rb"),
                img_mime_type,
            )
        }
        request_body = {
            "thumb_width": 160,
            "thumb_height": 160,
            "thumb_crop": False,
            "medium_width": 800,
            "medium_crop": "false",
            "type": "file",
            "action": "upload",
            "timestamp": int(time.time() * 1e3),  # Time in milliseconds
            "auth_token": self.img_host_token,
            "nsfw": 0,
        }
        headers = {
            "accept": "application/json",
            "origin": "https://jerking.empornium.ph",
            "referer": "https://jerking.empornium.ph/",
        }
        url = "https://jerking.empornium.ph/json"
        response = requests.post(url, files=files, data=request_body, cookies=self.cookies, headers=headers)
        if "error" in response.json():
            logger.error(f"Error uploading image: {response.json()['error']['message']}")
            return default,None
        # Cache and return url
        url = response.json()["image"]["image"]["url"]
        self.add(digest, url)
        logger.debug(f"Added {url} to cache for {img_path}")
        return url,digest
    
    @staticmethod
    def isWebpAnimated(path: str):
        with Image.open(path) as img:
            count = 0
            for frame in ImageSequence.Iterator(img):
                count += 1
            return count > 1

    def exists(self, key: str) -> bool:
        if key in self.urls:
            return True
        return self.redis is not None and self.redis.exists(f"{PREFIX}:{key}") != 0

    def get(self, key: str) -> Optional[str]:
        if self.no_cache or self.overwrite:
            return None
        if key in self.urls:
            return self.urls[key]
        elif self.redis is not None:
            value = self.redis.get(f"{PREFIX}:{key}")
            if value is not None:
                self.urls[key] = str(value)
                return str(value)
        return None

    def get_images(self, id: str, key: str) -> list[Optional[str]]:
        if self.no_cache or self.overwrite:
            logger.debug("Skipping cache check")
            return [None]
        if id in self.digests and key in self.digests[id]:
            urls = [self.get(digest) for digest in self.digests[id][key]]
            logger.debug(f"Got {len(urls)} urls of type {key} for file {id} from local cache")
            return urls
        if self.redis is not None:
            digests = self.redis.hget(f"{HASH_PREFIX}:{id}", key)
            if digests is not None:
                if id not in self.digests:
                    self.digests[id] = {}
                self.digests[id][key] = str(digests).split(":")
                urls = [self.get(digest) for digest in str(digests).split(":")]
                logger.debug(f"Got {len(urls)} urls of type {key} for file {id} from remote cache")
                return urls
        logger.debug(f"No images found in cache for file {id}")
        return [None]
            
    def generate_contact_sheet(self, stash_file: dict[str,Any]) -> Optional[str]:
        contact_sheet_file = tempfile.mkstemp(suffix="-contact.jpg")
        cmd = ["vcsi", stash_file["path"], "-g", "3x10", "-o", contact_sheet_file[1]]
        logger.info("Generating contact sheet")
        contact_sheet_remote_url = self.get_images(stash_file["id"], "contact")[0]
        if contact_sheet_remote_url is None:
            process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            logger.debug(f"vcsi output:\n{process.stdout}")
            if process.returncode != 0:
                logger.error("Couldn't generate contact sheet")
                return None
            
            logger.info("Uploading contact sheet")
            contact_sheet_remote_url,digest = self.img_host_upload(contact_sheet_file[1], "image/jpeg", "jpg")
            if contact_sheet_remote_url is None:
                logger.error("Failed to upload contact sheet")
                return None
            os.remove(contact_sheet_file[1])
            if digest is not None:
                self.set_images(stash_file["id"], "contact", [digest])
        return contact_sheet_remote_url

    def generate_screens(self, stash_file: dict[str,Any], num_frames: int = 10) -> list[Optional[str]]:
        screens = self.get_images(stash_file["id"], "screens")
        if len(screens) > 0 and None not in screens:
            return screens
        logger.info(f"Generating screens for {stash_file['path']}")
        screens = []

        digests = []
        for seek in map(
            lambda i: stash_file["duration"] * (0.05 + i / (num_frames - 1) * 0.9),
            range(num_frames),
        ):
            screen_file = tempfile.mkstemp(suffix="-screen.jpg")
            cmd = [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-ss",
                str(seek),
                "-i",
                stash_file["path"],
                "-frames:v",
                "1",
                "-vf",
                "scale=960:-2",
                screen_file[1],
            ]
            process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            url, digest = self.img_host_upload(screen_file[1], "image/jpeg", "jpg")
            screens.append(url)
            if digest is not None:
                digests.append(digest)
            if len(process.stdout) > 0:
                logger.debug(f"ffmpeg output:\n{process.stdout}")
        if len(digests) > 0:
            self.set_images(stash_file["id"], "screens", digests)
        logger.debug(f"Screens: {screens}")
        return screens

    def set_images(self,id:str, key:str, digests:list[str]) -> None:
        if self.no_cache:
            return
        if id not in self.digests:
            self.digests[id] = {}
        self.digests[id][key] = digests
        logger.debug(f"Added {len(digests)} image digests of type {key} to local cache")
        if self.redis is not None:
            self.redis.hset(f"{HASH_PREFIX}:{id}", key, ":".join(digests))
            logger.debug(f"Added {len(digests)} image digests of type {key} to remote cache")

    def add(self, key, value) -> None:
        if self.no_cache:
            return None
        self.urls[key] = value
        if self.redis is not None:
            self.redis.set(f"{PREFIX}:{key}", value)

    def clear(self) -> None:
        lcount = len(self.urls)
        self.urls.clear()
        if self.redis is not None:
            cursor = 0
            ns_keys = f"{PREFIX}:*"
            count = 0
            while True:
                cursor, keys = self.redis.scan(cursor=cursor, match=ns_keys, count=CHUNK_SIZE)  # type: ignore
                if keys:
                    count += len(keys)
                    self.redis.delete(*keys)
                if cursor == 0:
                    break
            logger.debug(f"Cleared {lcount} local cache entries and {count} remote entries")
