import asyncio
import hashlib
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from multiprocessing import Pool
from multiprocessing.connection import Connection
from typing import Any, Optional, Sequence

import pyimgbox
import requests
from PIL import Image, ImageSequence

from utils.confighandler import ConfigHandler, stash_headers
from utils.packs import prep_dir

logger = logging.getLogger(__name__)
use_redis = False
try:
    import redis

    use_redis = True
except ImportError:
    logger.info("Redis module not found, using local caching only")

CHUNK_SIZE = 5000
PERFORMER_DEFAULT_IMAGE = "https://jerking.empornium.ph/images/2023/10/10/image.png"
STUDIO_DEFAULT_LOGO = "https://jerking.empornium.ph/images/2022/02/21/stash41c25080a3611b50.png"
PREFIX = "stash-empornium"
HASH_PREFIX = f"{PREFIX}-file"

conf = ConfigHandler()


class ImageHandler:
    digests: dict[str, dict[str, list[str]]] = {}
    redis = None
    no_cache: bool = False
    overwrite: bool = False

    def __init__(self) -> None:
        self.urls: dict[str, dict[str, str]] = {"jerking": {}, "imgbox": {}}
        self.configure_cache()
        self.img_host_token, self.cookies = connection_init()

    def configure_cache(self) -> None:
        redis_host: str = conf.get("redis", "host", "")  # type: ignore
        redis_port: int = conf.get("redis", "port", 6379)  # type: ignore
        user = conf.get("redis", "username", "")
        password = conf.get("redis", "password", "")
        use_ssl: bool = conf.get("redis", "ssl", False)  # type: ignore
        no_cache = conf.args.no_cache
        overwrite = conf.args.overwrite
        flush = conf.args.flush

        enable = use_redis and not conf.get("redis", "disable", False)
        self.overwrite = overwrite
        self.no_cache = no_cache
        if not no_cache and redis_host is not None and enable and self.redis is None:
            try:
                self.redis = redis.Redis(
                    redis_host, redis_port, username=user, password=password, ssl=use_ssl, decode_responses=True
                )
                # It doesn't matter if this exists or not. An exception will be raised if not connected,
                # so we can "check" for any arbitrary value to see if connected
                self.redis.exists("connection_check")
                logger.debug(
                    f"Successfully connected to redis at {redis_host}:{redis_port}{' using ssl' if use_ssl else ''}"
                )
                if flush:
                    self.clear()
                    logger.debug("Cleared cache")
            except redis.exceptions.AuthenticationError as e:
                logger.error(f"Failed to authenticate with redis: {e} Check the username and password.")
                self.redis = None
            except redis.exceptions.ConnectionError as e:
                logger.error(f"Failed to connect to redis: {e} Check that the host and port are correct.")
                self.redis = None
        else:
            logger.debug("Not connecting to redis")

    def exists(self, key: str, host: str) -> bool:
        if key in self.urls[host]:
            return True
        return self.redis is not None and self.redis.exists(f"{PREFIX}:{host}:{key}") != 0

    def get(self, key: str, host: str) -> Optional[str]:
        if self.no_cache or self.overwrite:
            return None
        print(self.urls)
        if key in self.urls[host]:
            return self.urls[host][key]
        elif self.redis is not None:
            value = self.redis.get(f"{PREFIX}:{host}:{key}")
            if value is not None:
                self.urls[key] = str(value)
                return str(value)
            elif host == "jerking":
                value = self.redis.get(f"{PREFIX}:{key}")
                if value is not None:
                    self.urls[key] = str(value)
                    self.redis.rename(f"{PREFIX}:{key}", f"{PREFIX}:jerking:{key}")
                    return str(value)
        return None

    def get_images(self, scene_id: str, key: str, host: str) -> list[Optional[str]]:
        """
        Get all URLs of a given image type for a scene.
        :param scene_id: The ID of the scene to look up
        :param key: The type of image: `contact`, `screens`, `preview`, or `cover`
        :param host: The image host: `jerking` or `imgbox`
        :return: A list of strings representing the URLs if found
        """
        if self.no_cache or self.overwrite:
            logger.debug("Skipping cache check")
            return [None]
        if scene_id in self.digests and key in self.digests[scene_id]:
            urls = [self.get(digest, host) for digest in self.digests[scene_id][key]]
            logger.debug(f"Got {len(urls)} urls of type {key} for file {scene_id} from local cache")
            return urls
        if self.redis is not None:
            digests = self.redis.hget(f"{HASH_PREFIX}:{scene_id}", key)
            if digests is not None:
                if scene_id not in self.digests:
                    self.digests[scene_id] = {}
                self.digests[scene_id][key] = str(digests).split(":")
                urls = [self.get(digest, host) for digest in str(digests).split(":")]
                logger.debug(f"Got {len(urls)} urls of type {key} for file {scene_id} from remote cache")
                return urls
        logger.debug(f"No images found in cache for file {scene_id}")
        return [None]

    def process_preview(self, pipe: Connection, scene: dict[str, Any], host: str) -> Optional[str]:
        logger.info("Getting scene preview")
        preview_url = self.get_images(scene["files"][0]["id"], "preview", host)[0]
        if preview_url:
            pipe.send(preview_url)
            return

        preview = requests.get(scene["paths"]["preview"], headers=stash_headers) if scene["paths"]["preview"] else None
        if preview:
            with tempfile.TemporaryDirectory() as tempdir:
                temppath = os.path.join(tempdir, "preview.mp4")
                output = os.path.join(tempdir, "preview.gif")
                with open(temppath, "wb") as temp:
                    temp.write(preview.content)
                CMD = ["ffmpeg", "-i", temppath, "-vf",
                       "fps=10,scale=320:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse",
                       output, "-y"]
                proc = subprocess.run(CMD, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                logger.debug(f"ffmpeg output:\n{proc.stdout}")
                if proc.returncode:
                    logger.error("Error generating preview GIF")
                    pipe.send(None)
                    return
                width = 310
                while os.path.getsize(output) > 5000000:
                    CMD[4] = f"fps=10,scale={width}:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"
                    proc = subprocess.run(CMD, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                    logger.debug(f"ffmpeg output:\n{proc.stdout}")
                    if proc.returncode:
                        logger.error("Error generating preview GIF")
                        pipe.send(None)
                        return
                    width -= 10
                preview_url, digest = self.get_url(output, "image/gif", "gif", host, default=None)
                if digest:
                    for file in scene["files"]:
                        self.set_images(file["id"], "preview", [digest], host)
        else:
            logger.error(f"No preview found for scene {scene['id']}")
        pipe.send(preview_url)

    def generate_contact_sheet(self, stash_file: dict[str, Any], host: str, screens_dir: str | None = None) -> Optional[
        str]:
        """
        Generates a contact sheet for a stash video file, uploads it, and returns the URL. If caching is enabled
        and the image has been uploaded before, the existing URL will be returned without re-uploading the image.
        If `screens_dir` is provided, then the image will be copied to that directory with the filename
        contact_sheet.jpg.
        :param host: The image host: ``jerking`` or ``imgbox``
        :param stash_file: The file from which to generate the contact sheet
        :type stash_file: dict
        :param screens_dir: Where to save images for inclusion in the torrent
        :type screens_dir: str
        :return: The URL of the uploaded image, or ``None`` if uploading fails
        :rtype: str
        """
        contact_sheet_file = tempfile.mkstemp(suffix="-contact.jpg")
        os.chmod(contact_sheet_file[1], 0o666)  # Ensures torrent client can read the file
        cmd = ["vcsi", stash_file["path"], "-g", "3x10", "-o", contact_sheet_file[1]]
        logger.info("Generating contact sheet")
        contact_sheet_remote_url = self.get_images(stash_file["id"], "contact", host)[0]
        if contact_sheet_remote_url is None or screens_dir:
            process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            logger.debug(f"vcsi output:\n{process.stdout}")
            if process.returncode != 0:
                logger.error("Couldn't generate contact sheet")
                return None

            if screens_dir:
                prep_dir(screens_dir)  # Ensure directory exists
                shutil.copy(contact_sheet_file[1], os.path.join(screens_dir, 'contact_sheet.jpg'))

            logger.info("Uploading contact sheet")
            if contact_sheet_remote_url is None:
                contact_sheet_remote_url, digest = self.get_url(contact_sheet_file[1], "image/jpeg", "jpg", host)
                if contact_sheet_remote_url is None:
                    logger.error("Failed to upload contact sheet")
                    return None
                os.remove(contact_sheet_file[1])
                if digest is not None:
                    self.set_images(stash_file["id"], "contact", [digest], host)
        return contact_sheet_remote_url

    def generate_screens(self, stash_file: dict[str, Any], host: str, num_frames: int = 10) -> Sequence[Optional[str]]:
        screens = self.get_images(stash_file["id"], "screens", host)
        if len(screens) > 0 and None not in screens:
            return screens
        logger.info(f"Generating screens for {stash_file['path']}")
        screens = []
        digests = []

        cmds: list[tuple] = []

        for seek in map(
                lambda i: stash_file["duration"] * (0.05 + i / (num_frames - 1) * 0.9),
                range(num_frames),
        ):
            cmds.append((stash_file["path"], str(seek)))
        with Pool() as p:
            paths = p.starmap(generate_screen, cmds)
        logger.debug(paths)
        cmds.clear()
        for path in paths:
            digests.append(getDigest(path))
            cmds.append((path, "image/jpeg", "jpg", self.img_host_token, self.cookies, "jerking", 5_000_000))
        logger.debug(f"Digests: {digests}")
        with Pool() as p:
            screens = p.starmap(img_host_upload, cmds)
        for url, digest in zip(screens, digests):
            if url:
                self.add(digest, host, url)
            else:
                digests.remove(digest)
        if len(digests) > 0:
            self.set_images(stash_file["id"], "screens", digests, host)
        logger.debug(f"Screens: {screens}")
        return screens

    def get_url(
            self,
            img_path: str,
            img_mime_type: str,
            image_ext: str,
            host: str,
            width: int = 0,
            default: str | None = STUDIO_DEFAULT_LOGO,
    ) -> tuple[str | None, str | None]:
        # Return cached url if available
        digest = None
        if width > 0:
            with Image.open(img_path) as img:
                img.thumbnail((width, img.height))
                img.save(img_path)
                logger.debug(f"Resized image to {img.width}x{img.height}")
        digest = getDigest(img_path)
        url = self.get(digest, host)
        if url is not None:
            logger.debug(f"Found url {url} in cache")
            return url, digest
        url = img_host_upload(img_path, img_mime_type, image_ext, self.img_host_token, self.cookies, host, 5_000_000)
        if url:
            self.add(digest, host, url)
            return url, digest
        return default, digest

    def set_images(self, scene_id: str, key: str, digests: list[str], host: str) -> None:
        if self.no_cache:
            return
        if scene_id not in self.digests:
            self.digests[scene_id] = {}
        self.digests[scene_id][key] = digests
        logger.debug(f"Added {len(digests)} image digests of type {key} to local cache")
        if self.redis is not None:
            self.redis.hset(f"{HASH_PREFIX}:{scene_id}", key, ":".join(digests))
            logger.debug(f"Added {len(digests)} image digests of type {key} to remote cache")

    def add(self, key, host, value) -> None:
        if self.no_cache:
            return None
        self.urls[host][key] = value
        if self.redis is not None:
            self.redis.set(f"{PREFIX}:{host}:{key}", value)

    def clear(self) -> None:
        url_count = len(self.urls)
        self.urls = {'jerking': {}, 'imgbox': {}}
        if self.redis is not None:
            cursor = 0
            ns_keys = f"{PREFIX}*"
            count = 0
            while True:
                cursor, keys = self.redis.scan(cursor=cursor, match=ns_keys, count=CHUNK_SIZE)  # type: ignore
                if keys:
                    count += len(keys)
                    self.redis.delete(*keys)
                if cursor == 0:
                    break
            logger.debug(f"Cleared {url_count} local cache entries and {count} remote entries")


def connection_init():
    img_host_request = requests.get("https://jerking.empornium.ph/json")
    m = re.search(r"config\.auth_token\s*=\s*[\"'](\w+)[\"']", img_host_request.text)
    try:
        assert m is not None
    except:
        logger.critical("Unable to get auth token for image host.")
        raise
    img_host_token = m.group(1)
    cookies = img_host_request.cookies
    cookies.set("AGREE_CONSENT", "1", domain="jerking.empornium.ph", path="/")
    cookies.set("CHV_COOKIE_LAW_DISPLAY", "0", domain="jerking.empornium.ph", path="/")
    return img_host_token, cookies


def is_webp_animated(path: str):
    with Image.open(path) as img:
        count = 0
        for frame in ImageSequence.Iterator(img):
            count += 1
        return count > 1


def img_host_upload(
        img_path: str,
        img_mime_type: str,
        image_ext: str,
        img_host_token: str,
        cookies,
        host: str,
        max_size: int = 5_000_000
) -> str | None:
    """Upload an image and return the URL, or None if there is an error. Optionally takes
    a width, and scales the image down to that width if it is larger."""
    logger.debug(f"Uploading image from {img_path}")

    # Return default image if unknown
    if image_ext == "unk":
        return None

    # Convert animated webp to gif
    if img_mime_type == "image/webp":
        if is_webp_animated(img_path):
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

    # Quick and dirty resize for images above max filesize
    if os.path.getsize(img_path) > max_size:
        CMD = ["ffmpeg", "-i", img_path, "-vf", "scale=iw:ih", "-y", img_path]
        proc = subprocess.run(CMD, stderr=subprocess.PIPE, stdout=subprocess.STDOUT, text=True)
        logger.debug(f"ffmpeg output:\n{proc.stdout}")
        while os.path.getsize(img_path) > max_size:
            with Image.open(img_path) as img:
                img.thumbnail((int(img.width * 0.95), int(img.height * 0.95)), Image.LANCZOS)
                img.save(img_path)
        logger.debug(f"Resized {img_path}")

    match host:
        case "jerking":
            return jerking_upload(img_path, img_mime_type, image_ext, img_host_token, cookies)
        case "imgbox":
            return imgbox_upload(img_path, img_mime_type, image_ext)


def jerking_upload(
        img_path: str,
        img_mime_type: str,
        image_ext: str,
        img_host_token: str,
        cookies,
) -> str | None:
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
        "auth_token": img_host_token,
        "nsfw": 0,
    }
    headers = {
        "accept": "application/json",
        "origin": "https://jerking.empornium.ph",
        "referer": "https://jerking.empornium.ph/",
    }
    url = "https://jerking.empornium.ph/json"
    response = requests.post(url, files=files, data=request_body, cookies=cookies, headers=headers)
    j = None
    try:
        j = response.json()
        assert "error" not in j
    except AssertionError:
        logger.debug("Error uploading image, retrying connection")
        connection_init()
        response = requests.post(url, files=files, data=request_body, cookies=cookies, headers=headers)
        if j and "error" in j:
            logger.error(f"Error uploading image: {response.json()['error']['message']}")
            return None
    url: str = response.json()["image"]["image"]["url"]
    return url


def imgbox_upload(
        img_path: str,
        img_mime_type: str,
        image_ext: str):
    async def upload(path: str):
        async with pyimgbox.Gallery(adult=True) as gallery:
            submission: pyimgbox.Submission = await gallery.upload(path)
            logger.debug(f"imgbox submission: {submission}")
            return submission["image_url"]

    return asyncio.run(upload(img_path))


def generate_screen(path: str, seek: str) -> str:
    screen_file = tempfile.mkstemp(suffix="-screen.jpg")
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-ss",
        seek,
        "-i",
        path,
        "-frames:v",
        "1",
        "-vf",
        "scale=960:-2",
        screen_file[1],
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    # url, digest = self.jerking_upload(screen_file[1], "image/jpeg", "jpg")
    # return jerking_upload(screen_file[1], "image/jpeg", "jpg", img_host_token, cookies)
    return screen_file[1]


def getDigest(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.file_digest(f, hashlib.md5).hexdigest()


def createContactSheet(files: list[str], target_width: int, row_height: int, output: str) -> str | None:
    """
    Creates a gallery contact sheet from a list of file names.
    """
    row_files: list[str] = []
    rows: list[Image.Image] = []
    row_width = 0
    total_height = 0

    for file in files:
        img = None
        try:
            with Image.open(file) as img:
                w = img.width
                if img.height > row_height:
                    w = int((row_height / img.height) * img.width)
                if (row_width + w) > target_width:
                    delta = target_width / row_width
                    h = int(row_height * delta)
                    row = Image.new(img.mode, (target_width, h))
                    left = 0
                    for wfile in row_files:
                        with Image.open(wfile) as wimg:
                            wimg.thumbnail((wimg.width, h), Image.LANCZOS)
                            row.paste(wimg, (left, 0))
                            left += wimg.width

                    rows.append(row)
                    total_height += row.height

                    row_files.clear()
                    row_files.append(file)
                    row_width = w
                else:
                    row_files.append(file)
                    row_width += w
        except:
            pass

    sheet = Image.new("RGB", (target_width, total_height))
    top = 0
    for row in rows:
        bbox = (0, top)
        sheet.paste(row, bbox)
        top += row.height
        row.close()
    sheet.save(output)
    # sheet.show()
    sheet.close()
    return output
