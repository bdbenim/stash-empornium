#!/usr/bin/env python3
"""A mini service that generates upload material for EMP

Generate and upload screenshots and contact sheet, generate torrent
details from a template, generate torrent file, etc. to easily fill
the EMP upload form.

Required external utilities:
ffmpeg
mktorrent

Required Python modules:
configupdater
Flask
Pillow
requests
vcsi

Optional external utilities:
mediainfo

Optional Python modules:
redis
waitress
"""

__author__ = "An EMP user"
__license__ = "unlicense"
__version__ = "0.8.2"

# external
import requests
from flask import Flask, Response, request, stream_with_context, render_template, render_template_string
from PIL import Image, ImageSequence
import configupdater
from cairosvg import svg2png
from utils import cache

# built-in
import argparse
import datetime
import hashlib
import json
import logging
import math
import os
import pathlib
import re
import shutil
import string
import subprocess
import tempfile
import urllib.parse
import time
import uuid
from utils import taghandler

#############
# CONSTANTS #
#############

PERFORMER_DEFAULT_IMAGE = "https://jerking.empornium.ph/images/2023/10/10/image.png"
STUDIO_DEFAULT_LOGO = "https://jerking.empornium.ph/images/2022/02/21/stash41c25080a3611b50.png"
FILENAME_VALID_CHARS = "-_.() %s%s" % (string.ascii_letters, string.digits)

ODBL_NOTICE = "Contains information from https://github.com/mledoze/countries which is made available here under the Open Database License (ODbL), available at https://github.com/mledoze/countries/blob/master/LICENSE"

#############
# ARGUMENTS #
#############

parser = argparse.ArgumentParser(description="backend server for EMP Stash upload helper userscript")
parser.add_argument(
    "--configdir",
    default=[os.path.join(os.getcwd(), "config")],
    help="specify the directory containing configuration files",
    nargs=1,
)
parser.add_argument(
    "-t",
    "--torrentdir",
    help="specify the directory where .torrent files should be saved",
    nargs=1,
)
parser.add_argument("-p", "--port", nargs=1, help="port to listen on (default: 9932)", type=int)
flags = parser.add_argument_group("Tags", "optional tag settings")
flags.add_argument("-c", action="store_true", help="include codec as tag")
flags.add_argument("-d", action="store_true", help="include date as tag")
flags.add_argument("-f", action="store_true", help="include framerate as tag")
flags.add_argument("-r", action="store_true", help="include resolution as tag")
parser.add_argument("--version", action="version", version=f"stash-empornium {__version__}")
mutex = parser.add_argument_group("Output", "options for setting the log level").add_mutually_exclusive_group()
mutex.add_argument("-q", "--quiet", dest="level", action="count", default=2, help="output less")
mutex.add_argument("-v", "--verbose", "--debug", dest="level", action="store_const", const=1, help="output more")
mutex.add_argument(
    "-l",
    "--log",
    choices=["DEBUG", "INFO", "WARN", "WARNING", "ERROR", "CRITICAL", "FATAL"],
    metavar="LEVEL",
    help="log level: [DEBUG | INFO | WARNING | ERROR | CRITICAL]",
    type=str.upper,
)

redisgroup = parser.add_argument_group("redis", "options for connecting to a redis server")
redisgroup.add_argument("--rhost", "--redis--host", "--rh", help="host redis server is listening on")
redisgroup.add_argument(
    "--rport", "--redis-port", "--rp", help="port redis server is listening on (default: 6379)", type=int
)
redisgroup.add_argument("--username", "--redis-user", help="redis username")
redisgroup.add_argument("--password", "--redis-pass", help="redis password")
redisgroup.add_argument("--use-ssl", "-s", action="store_true", help="use SSL to connect to redis")
redisgroup.add_argument("--flush", help="flush redis cache", action="store_true")

args = parser.parse_args()

log_level = getattr(logging, args.log) if args.log else min(10 * args.level, 50)
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=log_level)
logger = logging.getLogger(__name__)
logger.info(f"stash-empornium version {__version__}")
logger.info(ODBL_NOTICE)

##########
# CONFIG #
##########

conf = configupdater.ConfigUpdater()
default_conf = configupdater.ConfigUpdater()

config_dir = args.configdir[0]

template_dir = os.path.join(config_dir, "templates")
config_file = os.path.join(config_dir, "config.ini")

# Ensure config file is present
if not os.path.isfile(config_file):
    logger.info(f"Config file not found at {config_file}, creating")
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)
    shutil.copyfile("default.ini", config_file)

# Ensure config file properly ends with a '\n' character
fstr = ""
with open(config_file, "r") as f:
    fstr = f.read()
if fstr[-1] != '\n':
    with open(config_file, "w") as f:
        f.write(fstr+'\n')
del fstr

logger.info(f"Reading config from {config_file}")
conf.read(config_file)
if conf["backend"].has_option("date_default"):
    conf["backend"]["date_default"].key = "date_format"
    conf.update_file()
    logger.info("Key 'date_default' renamed to 'date_format'")
default_conf.read("default.ini")
skip_sections = ["empornium", "empornium.tags"]
for section in default_conf.sections():
    if not conf.has_section(section):
        conf.add_section(section)
        conf[section].add_space('\n')
    if section not in skip_sections:
        for option in default_conf[section].options():
            if not conf[section].has_option(option):
                value = default_conf[section][option].value
                if len(conf[section].option_blocks()) > 0:
                    conf[section].option_blocks()[-1].add_after.comment("Value imported automatically:").option(option, value)
                else:
                    opt = configupdater.Option(option, value)
                    conf[section].add_option(opt)
                    opt.add_before.comment("Value imported automatically:")
                logger.info(f"Automatically added option '{option}' to section [{section}] with value '{value}'")
try:
    conf.update_file()
except:
    logger.error("Unable to save updated config")

if not os.path.exists(template_dir):
    shutil.copytree("default-templates", template_dir, copy_function=shutil.copyfile)
installed_templates = os.listdir(template_dir)
for filename in os.listdir("default-templates"):
    src = os.path.join("default-templates", filename)
    if os.path.isfile(src):
        dst = os.path.join(template_dir, filename)
        if os.path.isfile(dst):
            try:
                with open(src) as srcFile, open(dst) as dstFile:
                    srcVer = int("".join(filter(str.isdigit, "0" + srcFile.readline())))
                    dstVer = int("".join(filter(str.isdigit, "0" + dstFile.readline())))
                    if srcVer > dstVer:
                        logger.info(
                            f'Template "{filename}" has a new version available in the default-templates directory'
                        )
            except:
                logger.error(f"Couldn't compare version of {src} and {dst}")
        else:
            shutil.copyfile(src, dst)
            logger.info(f"Template {filename} has a been added. To use it, add it to config.ini under [templates]")
            if not conf["templates"].has_option(filename):
                tmpConf = configupdater.ConfigUpdater()
                tmpConf.read("default.ini")
                conf["templates"].set(filename, tmpConf["templates"][filename].value)


def error(message: str, altMessage: str | None = None) -> str:
    logger.error(message)
    return json.dumps({"status": "error", "message": altMessage if altMessage else message})


def warning(message: str, altMessage: str | None = None) -> str:
    logger.warning(message)
    return json.dumps({"status": "error", "message": altMessage if altMessage else message})


def info(message: str, altMessage: str | None = None) -> str:
    logger.info(message)
    return json.dumps({"status": "success", "data": {"message": altMessage if altMessage else message}})


def getConfigOption(config: configupdater.ConfigUpdater, section: str, option: str, default: str = "") -> str:
    value = config[section][option].value if config[section].has_option(option) else default
    return value if value else ""


# TODO: better handling of unexpected values
STASH_URL = getConfigOption(conf, "stash", "url", "http://localhost:9999")
assert STASH_URL is not None
PORT = args.port[0] if args.port else int(getConfigOption(conf, "backend", "port", "9932"))  # type: ignore
DEFAULT_TEMPLATE = getConfigOption(conf, "backend", "default_template", "fakestash-v2")
TORRENT_DIR = (
    args.torrentdir[0]
    if args.torrentdir
    else getConfigOption(conf, "backend", "torrent_directory", str(pathlib.Path.home()))
)
assert TORRENT_DIR is not None
if not os.path.isdir(TORRENT_DIR):
    if os.path.isfile(TORRENT_DIR):
        logger.critical(f"Cannot use {TORRENT_DIR} for torrents, path is a file")
        exit(1)
    logger.info(f"Creating directory {TORRENT_DIR}")
    os.makedirs(TORRENT_DIR)
TITLE_FORMAT = None
TITLE_TEMPLATE = None
if conf["backend"].has_option("title_default"):
    logger.warning(
        "Config option 'title_default' is deprecated and will be removed in v1. Please switch to 'title_template'\nSee https://github.com/bdbenim/stash-empornium#title-templates for details."
    )
    TITLE_FORMAT = getConfigOption(
        conf,
        "backend",
        "title_default",
        "[{studio}] {performers} - {title} ({date})[{resolution}]",
    )
TITLE_TEMPLATE = getConfigOption(
    conf,
    "backend",
    "title_template",
    "{% if studio %}[{{studio}}]{% endif %} {{performers|join(', ')}} - {{title}} {% if date %}({{date}}){% endif %}[{{resolution}}]",
)
DATE_FORMAT = getConfigOption(conf, "backend", "date_format", "%B %-d, %Y")
TAG_CODEC = args.c or getConfigOption(conf, "metadata", "tag_codec", "false").lower() == "true"
TAG_DATE = args.d or getConfigOption(conf, "metadata", "tag_date", "false").lower() == "true"
TAG_FRAMERATE = args.f or (getConfigOption(conf, "metadata", "tag_framerate", "false").lower() == "true")
TAG_RESOLUTION = args.r or (getConfigOption(conf, "metadata", "tag_resolution", "false").lower() == "true")
tags = taghandler.TagHandler(conf)

template_names = {}
template_files = os.listdir(template_dir)
for k in conf["templates"].to_dict():
    if k in template_files:
        template_names[k] = conf["templates"][k].value
    else:
        logger.warning(f"Template {k} from config.ini is not present in {template_dir}")

stash_headers = {
    "Content-type": "application/json",
}

if conf["stash"].has_option("api_key"):
    api_key = conf["stash"].get("api_key")
    assert api_key is not None
    api_key = api_key.value
    assert api_key is not None
    stash_headers["apiKey"] = api_key

stash_query = """
findScene(id: "{}") {{
    title
    details
    director
    date
    studio {{
        name
        url
        image_path
        parent_studio {{
            url
        }}
    }}
    tags {{
        name
        parents {{
            name
        }}
    }}
    performers {{
        name
        circumcised
        country
        gender
        image_path
        tags {{
            name
        }}
    }}
    paths {{
        screenshot
        preview
        webp
    }}
    files {{
        id
        path
        basename
        width
        height
        format
        duration
        video_codec
        audio_codec
        frame_rate
        bit_rate
        size
    }}
}}
"""

host = args.rhost if args.rhost else getConfigOption(conf, "redis", "host")
host = host if len(host) > 0 else None
port = args.rport if args.rport else int(getConfigOption(conf, "redis", "port", "6379"))
ssl = args.use_ssl or getConfigOption(conf, "redis", "ssl", "false").lower() == "true"
username = args.username if args.username else getConfigOption(conf, "redis", "username", "")
password = args.password if args.password else getConfigOption(conf, "redis", "password", "")

imgCache = cache.Cache(host, port, username, password, ssl)
if args.flush:
    imgCache.clear()

app = Flask(__name__, template_folder=template_dir)


def isWebpAnimated(path: str):
    with Image.open(path) as img:
        count = 0
        for frame in ImageSequence.Iterator(img):
            count += 1
        return count > 1


def img_host_upload(
    token: str,
    cookies,
    img_path: str,
    img_mime_type: str,
    image_ext: str,
    width: int = 0,
    default: str = STUDIO_DEFAULT_LOGO,
) -> str | None:
    """Upload an image and return the URL, or None if there is an error. Optionally takes
    a width, and scales the image down to that width if it is larger."""
    logger.debug(f"Uploading image from {img_path}")

    # Return default image if unknown
    if image_ext == "unk":
        return default

    # Return cached url if available
    digest = ""
    with open(img_path, "rb") as f:
        digest = hashlib.file_digest(f, hashlib.md5).hexdigest()
    if imgCache.exists(digest):
        url = imgCache.get(digest)
        logger.debug(f"Found url {url} in cache")
        return url

    # Convert animated webp to gif
    if img_mime_type == "image/webp":
        if isWebpAnimated(img_path):
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
        "auth_token": token,
        "nsfw": 0,
    }
    headers = {
        "accept": "application/json",
        "origin": "https://jerking.empornium.ph",
        "referer": "https://jerking.empornium.ph/",
    }
    url = "https://jerking.empornium.ph/json"
    response = requests.post(url, files=files, data=request_body, cookies=cookies, headers=headers)
    if "error" in response.json():
        logger.error(f"Error uploading image: {response.json()['error']['message']}")
        return default
    # Cache and return url
    url = response.json()["image"]["image"]["url"]
    imgCache.add(digest, url)
    logger.debug(f"Added {url} to cache for {img_path}")
    return url


@stream_with_context
def generate():
    j = request.get_json()
    scene_id = j["scene_id"]
    file_id = j["file_id"]
    announce_url = j["announce_url"]
    gen_screens = j["screens"]

    logger.info(f"Generating submission for scene ID {j['scene_id']} {'in' if gen_screens else 'ex'}cluding screens.")

    template = (
        j["template"] if "template" in j and j["template"] in os.listdir(app.template_folder) else DEFAULT_TEMPLATE
    )
    assert template is not None

    performers = {}
    screens = []
    studio_tag = ""

    tags.clear()

    #################
    # STASH REQUEST #
    #################

    stash_request_body = {"query": "{" + stash_query.format(scene_id) + "}"}
    stash_response = requests.post(
        urllib.parse.urljoin(STASH_URL, "/graphql"),
        json=stash_request_body,
        headers=stash_headers,
    )

    # if not stash_response.status_code == 200:
    #     return jsonify({ "status": "error" })

    stash_response_body = stash_response.json()
    scene = stash_response_body["data"]["findScene"]
    if scene is None:
        return error(f"Scene {scene_id} does not exist")

    # Ensure that all expected string keys are present
    str_keys = ["title", "details", "date"]
    for key in str_keys:
        if key not in scene:
            scene[key] = ""
        elif scene[key] == None:
            scene[key] = ""

    stash_file = None
    for f in scene["files"]:
        logger.debug(f"Checking path {f['path']}")
        if f["id"] == file_id:
            # Apply remote path mappings
            logger.debug(f"Got path {f['path']} from stash")
            for remote, localopt in conf.items("file.maps"):
                local = localopt.value
                assert local is not None
                if not f["path"].startswith(remote):
                    continue
                if remote[-1] != "/":
                    remote += "/"
                if local[-1] != "/":
                    local += "/"
                f["path"] = local + f["path"].removeprefix(remote)
                break
            stash_file = f
            break

    if stash_file is None:
        return error("No file exists")
    elif not os.path.isfile(stash_file["path"]):
        return error(f"Couldn't find file {stash_file['path']}")

    if len(scene["title"]) == 0:
        scene["title"] = stash_file["basename"]

    ht = stash_file["height"]
    resolution = None
    # these are stash's heuristics, see pkg/models/resolution.go
    if ht >= 144 and ht < 240:
        resolution = "144p"
    elif ht >= 240 and ht < 360:
        resolution = "240p"
    elif ht >= 360 and ht < 480:
        resolution = "360p"
    elif ht >= 480 and ht < 540:
        resolution = "480p"
    elif ht >= 540 and ht < 720:
        resolution = "540p"
    elif ht >= 720 and ht < 1080:
        resolution = "720p"
    elif ht >= 1080 and ht < 1440:
        resolution = "1080p"
    elif ht >= 1440 and ht < 1920:
        resolution = "1440p"
    elif ht >= 1920 and ht < 2560:
        resolution = "2160p"
    elif ht >= 2560 and ht < 3000:
        resolution = "5K"
    elif ht >= 3000 and ht < 3584:
        resolution = "6K"
    elif ht >= 3584 and ht < 3840:
        resolution = "7K"
    elif ht >= 3840 and ht < 6143:
        resolution = "8K"
    elif ht >= 6143:
        resolution = "8K+"

    if resolution is not None and TAG_RESOLUTION:
        tags.add(resolution)

    #########
    # COVER #
    #########

    cover_response = requests.get(scene["paths"]["screenshot"], headers=stash_headers)
    cover_mime_type = cover_response.headers["Content-Type"]
    logger.debug(f'Downloaded cover from {scene["paths"]["screenshot"]} with mime type {cover_mime_type}')
    cover_ext = ""
    cover_gen = False
    match cover_mime_type:
        case "image/jpeg":
            cover_ext = "jpg"
        case "image/png":
            cover_ext = "png"
        case "image/webp":
            cover_ext = "webp"
        case _:
            cover_gen = True
            cover_ext = "png"
            cover_mime_type = "image/png"
            logger.warning(f"Unrecognized cover format")  # TODO return warnings to client
    cover_file = tempfile.mkstemp(suffix="-cover." + cover_ext)
    if cover_gen:
        CMD = [
            "ffmpeg",
            "-ss",
            "30",
            "-i",
            stash_file["path"],
            "-vf",
            "thumbnail=300",
            "-frames:v",
            "1",
            cover_file[1],
            "-y",
        ]
        proc = subprocess.run(CMD, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        logger.debug(f"ffmpeg output:\n{proc.stdout}")
    else:
        with open(cover_file[1], "wb") as fp:
            fp.write(cover_response.content)

    ###############
    # STUDIO LOGO #
    ###############

    studio_img_ext = ""
    sudio_img_mime_type = ""
    studio_img_file = None
    if scene["studio"] is not None and "default=true" not in scene["studio"]["image_path"]:
        logger.debug(f'Downloading studio image from {scene["studio"]["image_path"]}')
        studio_img_response = requests.get(scene["studio"]["image_path"], headers=stash_headers)
        sudio_img_mime_type = studio_img_response.headers["Content-Type"]
        match sudio_img_mime_type:
            case "image/jpeg":
                studio_img_ext = "jpg"
            case "image/png":
                studio_img_ext = "png"
            case "image/svg+xml":
                studio_img_ext = "svg"
            case "image/webp":
                studio_img_ext = "webp"
            case _:
                studio_img_ext = "unk"
                yield warning(
                    f"Unknown studio logo file type: {sudio_img_mime_type}", "Unrecognized studio image file type"
                )
        studio_img_file = tempfile.mkstemp(suffix="-studio." + studio_img_ext)
        with open(studio_img_file[1], "wb") as fp:
            fp.write(studio_img_response.content)
        if studio_img_ext == "svg":
            png_file = tempfile.mkstemp(suffix="-studio.png")
            svg2png(url=studio_img_file[1], write_to=png_file[1])
            os.remove(studio_img_file[1])
            studio_img_file = png_file
            sudio_img_mime_type = "image/png"
            studio_img_ext = "png"

    ##############
    # PERFORMERS #
    ##############

    for performer in scene["performers"]:
        performer_tag = tags.processPerformer(performer)

        # image
        logger.debug(f'Downloading performer image from {performer["image_path"]}')
        performer_image_response = requests.get(performer["image_path"], headers=stash_headers)
        performer_image_mime_type = performer_image_response.headers["Content-Type"]
        logger.debug(f"Got image with mime type {performer_image_mime_type}")
        performer_image_ext = ""
        match performer_image_mime_type:
            case "image/jpeg":
                performer_image_ext = "jpg"
            case "image/png":
                performer_image_ext = "png"
            case "image/webp":
                performer_image_ext = "webp"
            case _:
                return error(
                    f"Unrecognized performer image mime type: {performer_image_mime_type}",
                    "Unrecognized performer image format",
                )
        performer_image_file = tempfile.mkstemp(suffix="-performer." + performer_image_ext)
        with open(performer_image_file[1], "wb") as fp:
            fp.write(performer_image_response.content)

        # store data
        performers[performer["name"]] = {
            "image_path": performer_image_file[1],
            "image_mime_type": performer_image_mime_type,
            "image_ext": performer_image_ext,
            "image_remote_url": None,
            "tag": performer_tag,
        }

    #################
    # CONTACT SHEET #
    #################

    # upload images and paste in description
    contact_sheet_file = tempfile.mkstemp(suffix="-contact.jpg")
    cmd = ["vcsi", stash_file["path"], "-g", "3x10", "-o", contact_sheet_file[1]]
    yield info("Generating contact sheet")
    process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    logger.debug(f"vcsi output:\n{process.stdout}")
    if process.returncode != 0:
        return error("vcsi failed", "Couldn't generate contact sheet")

    ###########
    # SCREENS #
    ###########

    num_frames = 10
    if gen_screens:
        yield info(f"Generating screens for {stash_file['path']}", "Generating screenshots")

        for seek in map(
            lambda i: stash_file["duration"] * (0.05 + i / (num_frames - 1) * 0.9),
            range(num_frames),
        ):
            screen_file = tempfile.mkstemp(suffix="-screen.jpg")
            screens.append(screen_file[1])
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
            logger.debug(f"ffmpeg output:\n{process.stdout}")

    audio_bitrate = ""
    cmd = [
        "ffprobe",
        "-v",
        "0",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=bit_rate",
        "-of",
        "compact=p=0:nk=1",
        stash_file["path"],
    ]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        logger.debug(f"ffprobe output:\n{proc.stdout}")
        audio_bitrate = f"{int(proc.stdout)//1000} kbps"

    except:
        logger.warning("Unable to determine audio bitrate")
        audio_bitrate = "UNK"

    ###########
    # TORRENT #
    ###########

    yield info("Making torrent")
    piece_size = int(math.log(stash_file["size"] / 2**10, 2))
    tempdir = tempfile.TemporaryDirectory()
    basename = "".join(c for c in stash_file["basename"] if c in FILENAME_VALID_CHARS)
    # logger.debug(f"Sanitized filename: {basename}")
    # basename = stash_file["basename"]
    temppath = os.path.join(tempdir.name, basename + ".torrent")
    torrent_path = os.path.join(TORRENT_DIR, stash_file["basename"] + ".torrent")
    logger.debug(f"Saving torrent to {temppath}")
    cmd = [
        "mktorrent",
        "-l",
        str(piece_size),
        "-s",
        "Emp",
        "-a",
        announce_url,
        "-p",
        "-v",
        "-o",
        temppath,
        stash_file["path"],
    ]
    process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    logger.debug(f"mktorrent output:\n{process.stdout}")
    if process.returncode != 0:
        tempdir.cleanup()
        return error("mktorrent failed, command: " + " ".join(cmd), "Couldn't generate torrent")
    shutil.move(temppath, torrent_path)
    tempdir.cleanup()
    logger.debug(f"Moved torrent to {torrent_path}")

    #############
    # MEDIAINFO #
    #############

    mediainfo = ""
    if shutil.which("mediainfo"):
        yield info("Generating media info")
        CMD = ["mediainfo", stash_file["path"]]
        try:
            mediainfo = subprocess.check_output(CMD, text=True)
        except subprocess.CalledProcessError as e:
            yield error(f"mediainfo exited with code {e.returncode}", "Error generating mediainfo")
            mediainfo = ""
            logger.debug(f"mediainfo output:\n{e.output}")

    #########
    # TITLE #
    #########

    title = ""
    if TITLE_FORMAT is not None:
        title = TITLE_FORMAT.format(
            studio=scene["studio"]["name"] if scene["studio"] else "",
            performers=", ".join([p["name"] for p in scene["performers"]]),
            title=scene["title"],
            date=scene["date"],
            resolution=resolution if resolution is not None else "",
            codec=stash_file["video_codec"],
            duration=str(datetime.timedelta(seconds=int(stash_file["duration"]))).removeprefix("0:"),
            framerate="{} fps".format(stash_file["frame_rate"]),
        )
    else:
        title = render_template_string(
            TITLE_TEMPLATE,
            **{
                "studio": scene["studio"]["name"] if scene["studio"] else "",
                "performers": [p["name"] for p in scene["performers"]],
                "title": scene["title"],
                "date": scene["date"],
                "resolution": resolution if resolution is not None else "",
                "codec": stash_file["video_codec"],
                "duration": str(datetime.timedelta(seconds=int(stash_file["duration"]))).removeprefix("0:"),
                "framerate": stash_file["frame_rate"],
            },
        )

    ########
    # TAGS #
    ########

    for tag in scene["tags"]:
        tags.processTag(tag["name"])
        for parent in tag["parents"]:
            tags.processTag(parent["name"])

    if TAG_CODEC and stash_file["video_codec"] is not None:
        tags.add(stash_file["video_codec"])

    if TAG_DATE and scene["date"] is not None and len(scene["date"]) > 0:
        year, month, day = scene["date"].split("-")
        tags.add(year)
        tags.add(f"{year}.{month}")
        tags.add(f"{year}.{month}.{day}")

    if TAG_FRAMERATE:
        tags.add(str(round(stash_file["frame_rate"])) + ".fps")

    if scene["studio"] and scene["studio"]["url"] is not None:
        studio_tag = urllib.parse.urlparse(scene["studio"]["url"]).netloc.removeprefix("www.")
        tags.add(studio_tag)
    if (
        scene["studio"] is not None
        and scene["studio"]["parent_studio"] is not None
        and scene["studio"]["parent_studio"]["url"] is not None
    ):
        tags.add(urllib.parse.urlparse(scene["studio"]["parent_studio"]["url"]).netloc.removeprefix("www."))

    ##########
    # UPLOAD #
    ##########

    yield json.dumps({"status": "success", "data": {"message": "Uploading images"}})

    img_host_request = requests.get("https://jerking.empornium.ph/json")
    m = re.search(r"config\.auth_token\s*=\s*[\"'](\w+)[\"']", img_host_request.text)
    if m is None:
        return error("Unable to get auth token for image host.")
    img_host_token = m.group(1)
    cookies = img_host_request.cookies
    cookies.set("AGREE_CONSENT", "1", domain="jerking.empornium.ph", path="/")
    cookies.set("CHV_COOKIE_LAW_DISPLAY", "0", domain="jerking.empornium.ph", path="/")

    yield info("Uploading cover")
    cover_remote_url = img_host_upload(img_host_token, cookies, cover_file[1], cover_mime_type, cover_ext)
    if cover_remote_url is None:
        return error("Failed to upload cover")
    cover_resized_url = img_host_upload(img_host_token, cookies, cover_file[1], cover_mime_type, cover_ext, width=800)
    os.remove(cover_file[1])
    yield info("Uploading contact sheet")
    contact_sheet_remote_url = img_host_upload(img_host_token, cookies, contact_sheet_file[1], "image/jpeg", "jpg")
    if contact_sheet_remote_url is None:
        return error("Failed to upload contact sheet")
    os.remove(contact_sheet_file[1])
    yield info("Uploading performer images")
    for performer_name in performers:
        performers[performer_name]["image_remote_url"] = img_host_upload(
            img_host_token,
            cookies,
            performers[performer_name]["image_path"],
            performers[performer_name]["image_mime_type"],
            performers[performer_name]["image_ext"],
            default=PERFORMER_DEFAULT_IMAGE,
        )
        os.remove(performers[performer_name]["image_path"])
        if performers[performer_name]["image_remote_url"] is None:
            performers[performer_name]["image_remote_url"] = PERFORMER_DEFAULT_IMAGE
            logger.warning(f"Unable to upload image for performer {performer_name}")

    logo_url = STUDIO_DEFAULT_LOGO
    if studio_img_file is not None and studio_img_ext != "":
        yield info("Uploading studio logo")
        logo_url = img_host_upload(
            img_host_token,
            cookies,
            studio_img_file[1],
            sudio_img_mime_type,
            studio_img_ext,
        )
        if logo_url is None:
            logo_url = STUDIO_DEFAULT_LOGO
            logger.warning("Unable to upload studio image")

    screens_urls = []
    a = 1
    b = len(screens)
    if b > 0:
        yield info("Uploading screens")
    for screen in screens:
        logger.debug(f"Uploading screens ({a} of {b})")
        a += 1
        scrn_url = img_host_upload(img_host_token, cookies, screen, "image/jpeg", "jpg")
        if scrn_url is None:
            return error("Failed to upload screens")
        screens_urls.append(scrn_url)
        os.remove(screen)

    ############
    # TEMPLATE #
    ############

    tmpTagLists = tags.sortTagLists()

    # Prevent error in case date is missing
    date = scene["date"]
    if date != None and len(date) > 1:
        date = datetime.datetime.fromisoformat(date).strftime(DATE_FORMAT)

    yield info("Rendering template")
    time.sleep(0.5)
    template_context = {
        "studio": scene["studio"]["name"] if scene["studio"] else "",
        "studio_logo": logo_url,
        "studiotag": studio_tag,
        "director": scene["director"],
        "title": scene["title"],
        "date": date,
        "details": scene["details"] if scene["details"] != "" else None,
        "duration": str(datetime.timedelta(seconds=int(stash_file["duration"]))).removeprefix("0:"),
        "container": stash_file["format"],
        "video_codec": stash_file["video_codec"],
        "audio_codec": stash_file["audio_codec"],
        "audio_bitrate": audio_bitrate,
        "resolution": "{}×{}".format(stash_file["width"], stash_file["height"]),
        "bitrate": "{:.2f} Mb/s".format(stash_file["bit_rate"] / 2**20),
        "framerate": "{} fps".format(stash_file["frame_rate"]),
        "screens": screens_urls if len(screens_urls) else None,
        "contact_sheet": contact_sheet_remote_url,
        "performers": performers,
        "cover": cover_resized_url,
        "image_count": 0,  # TODO
        "media_info": mediainfo,
    }

    for key in tmpTagLists:
        template_context[key] = ", ".join(tmpTagLists[key])

    description = render_template(template, **template_context)

    logger.info("Done")

    tag_suggestions = tags.tag_suggestions

    result = {
        "status": "success",
        "data": {
            "message": "Done",
            "fill": {
                "title": title,
                "cover": cover_remote_url,
                "tags": " ".join(tags.tags),
                "description": description,
                "torrent_path": torrent_path,
                "file_path": stash_file["path"],
            },
        },
    }

    logger.debug(f"Sending {len(tag_suggestions)} suggestions")
    if len(tag_suggestions) > 0:
        result["data"]["suggestions"] = tag_suggestions

    yield json.dumps(result)

    time.sleep(1)


@app.route("/suggestions", methods=["POST"])
def processSuggestions():
    j = request.get_json()
    logger.debug(f"Got json {j}")
    acceptedTags = {}
    if "accept" in j:
        logger.info(f"Accepting {len(j['accept'])} tag suggestions")
        for tag in j["accept"]:
            if "name" in tag:
                acceptedTags[tag["name"]] = tag["emp"]
    ignoredTags = []
    if "ignore" in j:
        logger.info(f"Ignoring {len(j['ignore'])} tags")
        for tag in j["ignore"]:
            ignoredTags.append(tag)
    success = tags.acceptSuggestions(acceptedTags)
    success = success and tags.rejectSuggestions(ignoredTags)
    if success:
        return json.dumps({"status": "success", "data": {"message": "Tags saved"}})
    else:
        return json.dumps({"status": "error", "data": {"message": "Failed to save tags"}})


@app.route("/fill", methods=["POST"])
def fill():
    return Response(generate(), mimetype="application/json")  # type: ignore


@app.route("/suggestions", methods=["POST"])
def suggestions():
    return Response(processSuggestions(), mimetype="application/json")


@app.route("/templates")
def templates():
    return json.dumps(template_names)


if __name__ == "__main__":
    try:
        from waitress import serve

        serve(app, host="0.0.0.0", port=PORT)
    except:
        logging.getLogger(__name__).info("Waitress not installed, using builtin server")
        app.run(host="0.0.0.0", port=PORT)
