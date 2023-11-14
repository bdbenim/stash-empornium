#!/usr/bin/env python3
"""A mini service that generates upload material for EMP

Generate and upload screenshots and contact sheet, generate torrent
details from a template, generate torrent file, etc. to easily fill
the EMP upload form.

Required external utilities:
ffmpeg
mktorrent

Required Python modules:
bootstrap-Flask
cairosvg
configupdater
Flask
Flask-WTF
Pillow
requests
tomlkit
vcsi

Optional external utilities:
mediainfo
redis

Optional Python modules:
redis
waitress
"""

__author__ = "An EMP user"
__license__ = "unlicense"
__version__ = "0.15.1"

# external
import requests
from flask import (
    Flask,
    Response,
    request,
    stream_with_context,
    render_template,
    render_template_string,
    redirect,
    url_for,
)
from cairosvg import svg2png

from flask_bootstrap import Bootstrap5
from flask_wtf import CSRFProtect

# built-in
import base64
import datetime
import json
import logging
import math
import multiprocessing as mp
from multiprocessing.connection import Connection
import os
import shutil
import string
import subprocess
import tempfile
import urllib.parse
import time

# included
from utils import taghandler, imagehandler, db
from utils.packs import link, readGallery
from utils.paths import mapPath
from utils.confighandler import ConfigHandler, stash_query, stash_headers
from webui.webui import settings_page


#############
# CONSTANTS #
#############

FILENAME_VALID_CHARS = "-_.() %s%s" % (string.ascii_letters, string.digits)
ODBL_NOTICE = "Contains information from https://github.com/mledoze/countries which is made available here under the Open Database License (ODbL), available at https://github.com/mledoze/countries/blob/master/LICENSE"

config = ConfigHandler()
logger = logging.getLogger(__name__)
logger.info(f"stash-empornium version {__version__}.")
logger.info(f"Release notes: https://github.com/bdbenim/stash-empornium/releases/tag/v{__version__}")
logger.info(ODBL_NOTICE)

MEDIA_INFO = shutil.which("mediainfo")


def error(message: str, altMessage: str | None = None) -> str:
    logger.error(message)
    return json.dumps({"status": "error", "message": altMessage if altMessage else message})


def warning(message: str, altMessage: str | None = None) -> str:
    logger.warning(message)
    return json.dumps({"status": "error", "message": altMessage if altMessage else message})


def info(message: str, altMessage: str | None = None) -> str:
    logger.info(message)
    return json.dumps({"status": "success", "data": {"message": altMessage if altMessage else message}})


def mapPaths(f: dict) -> dict:
    # Apply remote path mappings
    logger.debug(f"Got path {f['path']} from stash")
    for remote in config.items("file.maps"):
        local = config.get("file.maps", remote)
        assert isinstance(local, str)
        if not f["path"].startswith(remote):
            continue
        if remote[-1] != "/":
            remote += "/"
        if local[-1] != "/":
            local += "/"
        f["path"] = local + f["path"].removeprefix(remote)
        break
    return f


app = Flask(__name__, template_folder=config.template_dir)
app.secret_key = "secret"
app.config["BOOTSTRAP_BOOTSWATCH_THEME"] = "cyborg"
db_path = os.path.abspath(os.path.join(config.config_dir, "db.sqlite3"))
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
db.db.init_app(app)
with app.app_context():
    db.db.create_all()
taghandler.setup(app)
bootstrap = Bootstrap5(app)
csrf = CSRFProtect(app)


@stream_with_context
def generate():
    j = request.get_json()
    scene_id = j["scene_id"]
    file_id = j["file_id"]
    announce_url = j["announce_url"]
    gen_screens = j["screens"]
    include_gallery = j["gallery"]

    logger.info(
        f"Generating submission for scene ID {j['scene_id']} {'in' if gen_screens else 'ex'}cluding screens{'and including gallery' if include_gallery else ''}."
    )

    template = (
        j["template"]
        if "template" in j and j["template"] in os.listdir(app.template_folder)
        else config.default_template
    )
    assert template is not None

    performers = {}
    screens_urls = []
    studio_tag = ""

    tags = taghandler.TagHandler()

    #################
    # STASH REQUEST #
    #################

    logger.info("Querying stash")
    stash_request_body = {"query": "{" + stash_query.format(scene_id) + "}"}
    stash_response = requests.post(
        urllib.parse.urljoin(config.stash_url, "/graphql"),
        json=stash_request_body,
        headers=stash_headers,
    )

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

    new_dir = None
    image_dir = None
    image_temp = False
    gallery_contact = None
    gallery_proc = None
    image_count = 0
    if include_gallery:
        try:
            new_dir, image_dir, image_temp = readGallery(scene)  # type: ignore
            gallery_contact = tempfile.mkstemp("-gallery_contact.jpg")[1]
            files = [os.path.join(image_dir, file) for file in os.listdir(image_dir)]
            image_count = len(files)
            gallery_proc = mp.Process(target=imagehandler.createContactSheet, args=(files, 800, 200, gallery_contact))
            gallery_proc.start()
        except ValueError as ve:
            return error(str(ve))
        except TypeError:
            logger.warning("Unable to include gallery in torrent")
        except Exception as e:
            logger.debug(e)
            return error("An unexpected error occurred while processing the gallery")

    stash_file = None
    for f in scene["files"]:
        logger.debug(f"Checking path {f['path']}")
        if f["id"] == file_id:
            stash_file = f
            # stash_file = mapPaths(stash_file)
            stash_file["path"] = mapPath(stash_file["path"], config.items("file.maps"))
            break

    if stash_file is None:
        tmp_file = scene["files"][0]
        if tmp_file is None:
            return error("No file exists")
        # stash_file = mapPaths(tmp_file)
        stash_file = tmp_file
        stash_file["path"] = mapPath(stash_file["path"], config.items("file.maps"))
        logger.debug(f"No exact file match, using {stash_file['path']}")
    elif not os.path.isfile(stash_file["path"]):
        return error(f"Couldn't find file {stash_file['path']}")

    if new_dir:
        link(stash_file["path"], new_dir)

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

    if resolution is not None and config.tag_resolution:
        tags.add(resolution)

    ###########
    # TORRENT #
    ###########

    yield info("Making torrent")
    receive_pipe, send_pipe = mp.Pipe(False)
    torrent_proc = mp.Process(target=genTorrent, args=(send_pipe, stash_file, announce_url, new_dir))
    torrent_proc.start()

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
        # cover_gen_proc = subprocess.Popen(CMD, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        logger.debug(f"ffmpeg output:\n{proc.stdout}")
    else:
        with open(cover_file[1], "wb") as fp:
            fp.write(cover_response.content)

    yield info("Uploading images")
    images = None
    try:
        images = imagehandler.ImageHandler()
    except Exception as e:
        return error("Failed to initialize image handler")
    if config.args.flush:
        images.clear()

    cover_remote_url = images.getURL(cover_file[1], cover_mime_type, cover_ext)[0]
    if cover_remote_url is None:
        return error("Failed to upload cover")
    cover_resized_url = images.getURL(cover_file[1], cover_mime_type, cover_ext, width=800)[0]
    os.remove(cover_file[1])

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
                time.sleep(0.1)
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
    contact_sheet_remote_url = images.generate_contact_sheet(stash_file)
    if contact_sheet_remote_url is None:
        return error("Failed to generate contact sheet")

    ###########
    # SCREENS #
    ###########

    if gen_screens:
        screens_urls = images.generate_screens(stash_file=stash_file)  # TODO customize number of screens from config
        if screens_urls is None or None in screens_urls:
            return error("Failed to generate screens")

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
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        audio_bitrate = f"{int(proc.stdout)//1000} kbps"

    except:
        logger.warning("Unable to determine audio bitrate")
        audio_bitrate = "UNK"

    #############
    # MEDIAINFO #
    #############

    mediainfo = ""
    info_proc = None
    info_recv = None
    if MEDIA_INFO:
        info_recv, info_send = mp.Pipe(False)
        info_proc = mp.Process(target=genMediaInfo, args=(info_send, stash_file["path"]))
        info_proc.start()
        logger.debug(mediainfo)

    #########
    # TITLE #
    #########

    title = render_template_string(
        config.title_template,
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

    if config.tag_codec and stash_file["video_codec"] is not None:
        tags.add(stash_file["video_codec"])

    if config.tag_codec and scene["date"] is not None and len(scene["date"]) > 0:
        year, month, day = scene["date"].split("-")
        tags.add(year)
        tags.add(f"{year}.{month}")
        tags.add(f"{year}.{month}.{day}")

    if config.tag_framerate:
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

    logger.info("Uploading performer images")
    for performer_name in performers:
        performers[performer_name]["image_remote_url"] = images.getURL(
            performers[performer_name]["image_path"],
            performers[performer_name]["image_mime_type"],
            performers[performer_name]["image_ext"],
            default=imagehandler.PERFORMER_DEFAULT_IMAGE,
        )[0]
        os.remove(performers[performer_name]["image_path"])
        if performers[performer_name]["image_remote_url"] is None:
            performers[performer_name]["image_remote_url"] = imagehandler.PERFORMER_DEFAULT_IMAGE
            logger.warning(f"Unable to upload image for performer {performer_name}")

    logo_url = imagehandler.STUDIO_DEFAULT_LOGO
    if studio_img_file is not None and studio_img_ext != "":
        logger.info("Uploading studio logo")
        logo_url = images.getURL(
            studio_img_file[1],
            sudio_img_mime_type,
            studio_img_ext,
        )[0]
        if logo_url is None:
            logo_url = imagehandler.STUDIO_DEFAULT_LOGO
            logger.warning("Unable to upload studio image")

    if image_temp:
        shutil.rmtree(image_dir)  # type: ignore
        logger.debug(f"Deleted {image_dir}")

    gallery_contact_url = None
    if gallery_proc:
        gallery_proc.join()
        gallery_contact_url = images.getURL(gallery_contact, "image/jpeg", "jpg")[0]  # type: ignore
        os.remove(gallery_contact)  # type: ignore

    ############
    # TEMPLATE #
    ############

    tmpTagLists = tags.sortTagLists()

    # Prevent error in case date is missing
    date = scene["date"]
    if date != None and len(date) > 1:
        date = datetime.datetime.fromisoformat(date).strftime(config.date_format)

    yield info("Rendering template")

    if info_proc is not None:
        info_proc.join()
        mediainfo = info_recv.recv()  # type: ignore

    time.sleep(0.1)
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
        "image_count": image_count,
        "gallery_contact": gallery_contact_url,
        "media_info": mediainfo,
    }

    for key in tmpTagLists:
        template_context[key] = ", ".join(tmpTagLists[key])

    description = render_template(template, **template_context)

    tag_suggestions = tags.tag_suggestions

    # if include_gallery:
    #     gal_proc.join()
    #     gal = gal_recv.recv()
    # TODO

    logger.info("Waiting for torrent generation to complete")
    torrent_proc.join()
    torrent_paths = receive_pipe.recv()

    result = {
        "status": "success",
        "data": {
            "message": "Done",
            "fill": {
                "title": title,
                "cover": cover_remote_url,
                "tags": " ".join(tags.tags),
                "description": description,
                "torrent_path": torrent_paths[0],
                "file_path": stash_file["path"],
                "anon": config.anon,
            },
        },
    }

    with open(torrent_paths[0], "rb") as f:
        result["data"]["file"] = {
            "name": os.path.basename(f.name),
            "content": str(base64.b64encode(f.read()).decode("ascii")),
        }

    logger.debug(f"Sending {len(tag_suggestions)} suggestions")
    if len(tag_suggestions) > 0:
        result["data"]["suggestions"] = dict(tag_suggestions)

    yield json.dumps(result)

    for client in config.torrent_clients:
        try:
            path = new_dir if new_dir else stash_file["path"]
            client.add(torrent_paths[0], path)
        except Exception as e:
            logger.error(f"Error attempting to add torrent to {client.name}")
            logger.debug(e)

    logger.info("Done")
    time.sleep(1)


def genTorrent(
    pipe: Connection, stash_file: dict, announce_url: str, directory: str | None = None
) -> list[str] | None:
    piece_size = int(math.log(stash_file["size"] / 2**10, 2))
    tempdir = tempfile.TemporaryDirectory()
    basename = "".join(c for c in stash_file["basename"] if c in FILENAME_VALID_CHARS)

    target = directory if directory else stash_file["path"]

    temppath = os.path.join(tempdir.name, basename + ".torrent")
    torrent_paths = [os.path.join(dir, stash_file["basename"] + ".torrent") for dir in config.torrent_dirs]
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
        target,
    ]
    process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    logger.debug(f"mktorrent output:\n{process.stdout}")
    if process.returncode != 0:
        tempdir.cleanup()
        logger.error("mktorrent failed, command: " + " ".join(cmd), "Couldn't generate torrent")
        return None
    for path in torrent_paths:
        shutil.copy(temppath, path)
    tempdir.cleanup()
    logger.debug(f"Moved torrent to {torrent_paths}")
    pipe.send(torrent_paths)
    # return torrent_paths


def genMediaInfo(pipe: Connection, path: str) -> None:
    cmd = [MEDIA_INFO, path]
    pipe.send(subprocess.check_output(cmd, text=True))


@app.route("/submit", methods=["POST"])
@csrf.exempt
def submit():
    j = request.get_json()
    logger.debug(f"Torrent submitted: {j}")
    for client in config.torrent_clients:
        try:
            client.start(j["torrent_path"])
        except Exception as e:
            logger.error(f"Error attempting to start torrent in {client.name}")
            logger.debug(e)
    return json.dumps({"status": "success"})


@app.route("/suggestions", methods=["POST"])
@csrf.exempt
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
    success = taghandler.acceptSuggestions(acceptedTags)
    success = success and taghandler.rejectSuggestions(ignoredTags)
    return json.dumps({"status": "success", "data": {"message": "Tags saved"}})


@app.route("/fill", methods=["POST"])
@csrf.exempt
def fill():
    return Response(generate(), mimetype="application/json")  # type: ignore


@app.route("/templates")
@csrf.exempt
def templates():
    return json.dumps(config.template_names)


@app.route("/favicon.ico")
def favicon():
    return redirect(url_for("static", filename="favicon.ico"))


if __name__ == "__main__":
    app.register_blueprint(settings_page)
    try:
        from waitress import serve

        serve(app, host="0.0.0.0", port=config.port)
        # app.run(host="0.0.0.0", port=config.port, debug=True)
    except:
        logger.info("Waitress not installed, using builtin server")
        app.run(host="0.0.0.0", port=config.port, debug=True)
