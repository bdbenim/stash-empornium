import base64
import datetime
import json
import logging
import math
import multiprocessing as mp
import os
import shutil
import string
import subprocess
import tempfile
import urllib.parse
from collections.abc import Generator
from concurrent.futures import Future, ThreadPoolExecutor
from multiprocessing.connection import Connection

import requests
from cairosvg import svg2png
from flask import render_template, render_template_string

from utils import imagehandler, taghandler
from utils.confighandler import ConfigHandler, stash_headers, stash_query
from utils.packs import link, read_gallery, get_torrent_directory
from utils.paths import mapPath

MEDIA_INFO = shutil.which("mediainfo")
FILENAME_VALID_CHARS = "-_.() %s%s" % (string.ascii_letters, string.digits)
config = ConfigHandler()

jobs: list[Future] = []
job_pool = ThreadPoolExecutor(max_workers=4)
jobs_lock = mp.Lock()


def add_job(j: dict) -> int:
    future = job_pool.submit(generate, j)
    with jobs_lock:
        job_id = len(jobs)
        jobs.append(future)
    return job_id


def error(message: str, alt_message: str | None = None) -> str:
    logging.getLogger(__name__).error(message)
    return json.dumps({"status": "error", "message": alt_message if alt_message else message})


def warning(message: str, alt_message: str | None = None) -> str:
    logging.getLogger(__name__).warning(message)
    return json.dumps({"status": "error", "message": alt_message if alt_message else message})


def info(message: str, alt_message: str | None = None) -> str:
    logging.getLogger(__name__).info(message)
    return json.dumps({"status": "success", "data": {"message": alt_message if alt_message else message}})


def generate(j: dict) -> Generator[str, None, str | None]:
    logger = logging.getLogger(__name__)

    scene_id = j["scene_id"]
    file_id = j["file_id"]
    announce_url = j["announce_url"]
    gen_screens = j["screens"]
    include_gallery = j["gallery"]
    tracker = j["tracker"]  # 'EMP', 'PB', 'FC', 'HF' or 'ENT'
    include_screens = tracker == 'FC'  # TODO user customization
    img_host = "imgbox" if tracker == 'HF' else "jerking"

    yield info("Starting generation")

    logger.info(
        f"Generating submission for scene ID {j['scene_id']} {'in' if gen_screens else 'ex'}cluding screens{
        ' and including gallery' if include_gallery else ''}."
    )

    template = (
        j["template"]
        if "template" in j and j["template"] in config.template_names
        else config.get("backend", "default_template")
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
        urllib.parse.urljoin(config.get("stash", "url", "http://localhost:9999"), "/graphql"),  # type: ignore
        json=stash_request_body,
        headers=stash_headers,
    )

    stash_response_body = stash_response.json()
    scene = stash_response_body["data"]["findScene"]
    if scene is None:
        yield error(f"Scene {scene_id} does not exist")
        return

    # Ensure that all expected string keys are present
    str_keys = ["title", "details", "date"]
    for key in str_keys:
        if key not in scene:
            scene[key] = ""
        elif scene[key] is None:
            scene[key] = ""

    new_dir = get_torrent_directory(scene) if include_screens else None
    image_dir = None
    image_temp = False
    gallery_contact = None
    gallery_proc = None
    image_count = 0
    if include_gallery:
        try:
            new_dir, image_dir, image_temp = read_gallery(scene)  # type: ignore
            gallery_contact = tempfile.mkstemp("-gallery_contact.jpg")[1]
            files = [os.path.join(image_dir, file) for file in os.listdir(image_dir)]
            image_count = len(files)
            gallery_proc = mp.Process(target=imagehandler.createContactSheet, args=(files, 800, 200, gallery_contact))
            gallery_proc.start()
        except ValueError as ve:
            yield error(str(ve))
            return
        except TypeError:
            logger.warning("Unable to include gallery in torrent")
        except Exception as e:
            logger.debug(e)
            yield error("An unexpected error occurred while processing the gallery")
            return

    stash_file = None
    for f in scene["files"]:
        logger.debug(f"Checking path {f['path']}")
        if f["id"] == file_id:
            stash_file = f
            maps = config.items("file.maps")
            if not maps:
                maps = config.get("file", "maps", {})
            stash_file["path"] = mapPath(stash_file["path"], maps)  # type: ignore
            break

    if stash_file is None:
        tmp_file = scene["files"][0]
        if tmp_file is None:
            yield error("No file exists")
            return
        stash_file = tmp_file
        maps = config.items("file.maps")
        if not maps:
            maps = config.get("file", "maps", {})
        stash_file["path"] = mapPath(stash_file["path"], maps)  # type: ignore
        logger.debug(f"No exact file match, using {stash_file['path']}")
    elif not os.path.isfile(stash_file["path"]):
        yield error(f"Couldn't find file {stash_file['path']}")
        return

    if new_dir:
        link(stash_file["path"], new_dir)

    if len(scene["title"]) == 0:
        scene["title"] = stash_file["basename"]

    ht = stash_file["height"]
    resolution = None
    # these are stash's heuristics, see pkg/models/resolution.go
    if 144 <= ht < 240:
        resolution = "144p"
    elif 240 <= ht < 360:
        resolution = "240p"
    elif 360 <= ht < 480:
        resolution = "360p"
    elif 480 <= ht < 540:
        resolution = "480p"
    elif 540 <= ht < 720:
        resolution = "540p"
    elif 720 <= ht < 1080:
        resolution = "720p"
    elif 1080 <= ht < 1440:
        resolution = "1080p"
    elif 1440 <= ht < 1920:
        resolution = "1440p"
    elif 1920 <= ht < 2560:
        resolution = "2160p"
    elif 2560 <= ht < 3000:
        resolution = "5K"
    elif 3000 <= ht < 3584:
        resolution = "6K"
    elif 3584 <= ht < 3840:
        resolution = "7K"
    elif 3840 <= ht < 6143:
        resolution = "8K"
    elif ht >= 6143:
        resolution = "8K+"

    if resolution is not None and config.get("metadata", "tag_resolution"):
        tags.add(resolution)

    yield info("Uploading images")
    try:
        images = imagehandler.ImageHandler()
    except KeyboardInterrupt:
        raise
    except Exception:
        yield error("Failed to initialize image handler")
        return
    if config.args.flush:
        images.clear()

    #################
    # CONTACT SHEET #
    #################

    # Generate contact sheet and include it in the torrent directory if include_screens is True
    screens_dir = os.path.join(get_torrent_directory(scene), 'screens') if include_screens else None
    contact_sheet_remote_url = images.generate_contact_sheet(stash_file, img_host, screens_dir)
    if contact_sheet_remote_url is None:
        yield error("Failed to generate contact sheet")
        return

    #########
    # COVER #
    #########
    # TODO Move this into image handler
    cover_response = requests.get(scene["paths"]["screenshot"], headers=stash_headers)
    cover_mime_type = cover_response.headers["Content-Type"]
    logger.debug(f'Downloaded cover from {scene["paths"]["screenshot"]} with mime type {cover_mime_type}')
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
        cmd = [
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
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        logger.debug(f"ffmpeg output:\n{proc.stdout}")
    else:
        with open(cover_file[1], "wb") as fp:
            fp.write(cover_response.content)
    if screens_dir:
        os.chmod(cover_file[1], 0o666)  # Ensures torrent client can read the file
        shutil.copy(cover_file[1], os.path.join(screens_dir, f"cover.{cover_ext}"))

    ###########
    # TORRENT #
    ###########

    yield info("Making torrent")
    receive_pipe: Connection
    send_pipe: Connection
    receive_pipe, send_pipe = mp.Pipe(False)
    torrent_proc = mp.Process(target=gen_torrent, args=(send_pipe, stash_file, announce_url, new_dir))
    torrent_proc.start()

    cover_remote_url = images.get_url(cover_file[1], cover_mime_type, cover_ext, img_host)[0]
    if cover_remote_url is None:
        yield error("Failed to upload cover")
        return
    cover_resized_url = images.get_url(cover_file[1], cover_mime_type, cover_ext, img_host, width=800)[0]
    os.remove(cover_file[1])

    ###########
    # PREVIEW #
    ###########
    preview_recv: Connection
    preview_send: Connection
    preview_recv, preview_send = mp.Pipe(False)
    preview_proc = mp.Process(target=images.process_preview, args=(preview_send, scene, img_host))
    if config.get("backend", "use_preview", False):
        preview_proc.start()
    # del preview_send  # Ensures connection can be automatically closed if garbage collected

    ###############
    # STUDIO LOGO #
    ###############

    studio_img_ext = ""
    studio_img_mime_type = ""
    studio_img_file = None
    if scene["studio"] is not None and "default=true" not in scene["studio"]["image_path"]:
        logger.debug(f'Downloading studio image from {scene["studio"]["image_path"]}')
        studio_img_response = requests.get(scene["studio"]["image_path"], headers=stash_headers)
        studio_img_mime_type = studio_img_response.headers["Content-Type"]
        match studio_img_mime_type:
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
                yield (warning(
                    f"Unknown studio logo file type: {studio_img_mime_type}", "Unrecognized studio image file type"
                ))
        studio_img_file = tempfile.mkstemp(suffix="-studio." + studio_img_ext)
        with open(studio_img_file[1], "wb") as fp:
            fp.write(studio_img_response.content)
        if studio_img_ext == "svg":
            png_file = tempfile.mkstemp(suffix="-studio.png")
            svg2png(url=studio_img_file[1], write_to=png_file[1])
            os.remove(studio_img_file[1])
            studio_img_file = png_file
            studio_img_mime_type = "image/png"
            studio_img_ext = "png"

    ##############
    # PERFORMERS #
    ##############

    for performer in scene["performers"]:
        performer_tag = tags.process_performer(performer, tracker)

        # image
        logger.debug(f'Downloading performer image from {performer["image_path"]}')
        performer_image_response = requests.get(performer["image_path"], headers=stash_headers)
        performer_image_mime_type = performer_image_response.headers["Content-Type"]
        logger.debug(f"Got image with mime type {performer_image_mime_type}")
        match performer_image_mime_type:
            case "image/jpeg":
                performer_image_ext = "jpg"
            case "image/png":
                performer_image_ext = "png"
            case "image/webp":
                performer_image_ext = "webp"
            case _:
                yield (error(
                    f"Unrecognized performer image mime type: {performer_image_mime_type}",
                    "Unrecognized performer image format",
                ))
                return
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

    ###########
    # SCREENS #
    ###########

    if gen_screens:
        screens_urls = images.generate_screens(stash_file=stash_file,
                                               host=img_host)  # TODO customize number of screens from config
        if screens_urls is None or None in screens_urls:
            yield error("Failed to generate screens")
            return

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
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=True)
        audio_bitrate = f"{int(proc.stdout) // 1000} kbps"

    except subprocess.CalledProcessError:
        logger.warning("Unable to determine audio bitrate")
        audio_bitrate = "UNK"

    #############
    # MEDIAINFO #
    #############

    mediainfo = ""
    info_proc = None
    info_recv: Connection
    info_send: Connection
    if MEDIA_INFO:
        info_recv, info_send = mp.Pipe(False)
        info_proc = mp.Process(target=gen_media_info, args=(info_send, stash_file["path"]))
        info_proc.start()
        # del info_send  # Ensures connection can be automatically closed if garbage collected

    #########
    # TITLE #
    #########

    title = render_template_string(
        config.get("backend", "title_template", ""),  # type: ignore
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
        tags.process_tag(tag["name"], tracker)
        for parent in tag["parents"]:
            tags.process_tag(parent["name"], tracker)

    if config.get("metadata", "tag_codec") and stash_file["video_codec"] is not None:
        tags.add(stash_file["video_codec"])

    if config.get("metadata", "tag_date") and scene["date"] is not None and len(scene["date"]) > 0:
        year, month, day = scene["date"].split("-")
        tags.add(year)
        tags.add(f"{year}.{month}")
        tags.add(f"{year}.{month}.{day}")

    if config.get("metadata", "tag_framerate"):
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
        performers[performer_name]["image_remote_url"] = images.get_url(
            performers[performer_name]["image_path"],
            performers[performer_name]["image_mime_type"],
            performers[performer_name]["image_ext"],
            img_host,
            default=imagehandler.DEFAULT_IMAGES["performer"][img_host],
        )[0]
        os.remove(performers[performer_name]["image_path"])
        if performers[performer_name]["image_remote_url"] is None:
            performers[performer_name]["image_remote_url"] = imagehandler.DEFAULT_IMAGES["performer"][img_host]
            logger.warning(f"Unable to upload image for performer {performer_name}")

    logo_url = imagehandler.DEFAULT_IMAGES["studio"][img_host]
    if studio_img_file is not None and studio_img_ext != "":
        logger.info("Uploading studio logo")
        logo_url = images.get_url(
            studio_img_file[1],
            studio_img_mime_type,
            studio_img_ext,
            img_host,
        )[0]
        if logo_url is None:
            logo_url = imagehandler.DEFAULT_IMAGES["studio"][img_host]
            logger.warning("Unable to upload studio image")

    if image_temp:
        shutil.rmtree(image_dir)  # type: ignore
        logger.debug(f"Deleted {image_dir}")

    gallery_contact_url = None
    if gallery_proc:
        gallery_proc.join(timeout=60)
        gallery_contact_url = images.get_url(gallery_contact, "image/jpeg", "jpg", img_host)[0]  # type: ignore
        os.remove(gallery_contact)  # type: ignore

    ############
    # TEMPLATE #
    ############

    tmp_tag_lists = tags.sort_tag_lists()

    # Prevent error in case date is missing
    date = scene["date"]
    if date is not None and len(date) > 1:
        date = datetime.datetime.fromisoformat(date).strftime(
            config.get("backend", "date_format", "%B %-d, %Y"))  # type: ignore

    yield info("Rendering template")

    if info_proc is not None:
        info_proc.join(timeout=60)
        info_proc.close()
        try:
            info_send.close()
            mediainfo = info_recv.recv()  # type: ignore
        except EOFError:
            error("Failed to generate media info")

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
        "bitrate": "{:.2f} Mb/s".format(stash_file["bit_rate"] / 2 ** 20),
        "framerate": "{} fps".format(stash_file["frame_rate"]),
        "screens": screens_urls if len(screens_urls) else None,
        "contact_sheet": contact_sheet_remote_url,
        "performers": performers,
        "cover": cover_resized_url,
        "image_count": image_count,
        "gallery_contact": gallery_contact_url,
        "media_info": mediainfo,
        "pad":  imagehandler.DEFAULT_IMAGES["pad"][img_host],
    }

    preview_url = None
    if config.get("backend", "use_preview", False):
        preview_proc.join(timeout=60)
        try:
            preview_proc.close()
            preview_send.close()
            preview_url = preview_recv.recv()
        except EOFError:
            error("Unable to upload preview GIF")
        except ValueError:
            error("Unable to generate preview GIF (too long)")
        template_context["preview"] = preview_url

    for key in tmp_tag_lists:
        template_context[key] = ", ".join(tmp_tag_lists[key])

    description = render_template(template, **template_context)  # type: ignore

    tag_suggestions = tags.tag_suggestions

    yield info("Waiting for torrent generation to complete")
    torrent_proc.join(timeout=60)
    send_pipe.close()
    try:
        torrent_paths = receive_pipe.recv()
    except EOFError:
        yield error("Failed to save torrent")
        return

    result = {
        "status": "success",
        "data": {
            "message": "Done",
            "fill": {
                "title": title,
                "cover": preview_url
                if preview_url and config.get("backend", "animated_cover", False)
                else cover_remote_url,
                "tags": " ".join(tags.tags),
                "description": description,
                "torrent_path": torrent_paths[0],
                "file_path": stash_file["path"],
                "anon": config.get("backend", "anon", False),
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


def gen_torrent(
        pipe: Connection, stash_file: dict, announce_url: str, directory: str | None = None
) -> list[str] | None:
    logger = logging.getLogger(__name__)
    piece_size = int(math.log(stash_file["size"] / 2 ** 10, 2))
    tempdir = tempfile.TemporaryDirectory()
    basename = "".join(c for c in stash_file["basename"] if c in FILENAME_VALID_CHARS)

    target = directory if directory else stash_file["path"]

    temp_path = os.path.join(tempdir.name, basename + ".torrent")
    torrent_paths = [os.path.join(d, stash_file["basename"] + ".torrent") for d in config.torrent_dirs]
    logger.debug(f"Saving torrent to {temp_path}")
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
        temp_path,
        target,
    ]
    process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    logger.debug(f"mktorrent output:\n{process.stdout}")
    if process.returncode != 0:
        tempdir.cleanup()
        logger.error("mktorrent failed, command: " + " ".join(cmd), "Couldn't generate torrent")
        return
    for path in torrent_paths:
        shutil.copy(temp_path, path)
    tempdir.cleanup()
    logger.debug(f"Moved torrent to {torrent_paths}")
    pipe.send(torrent_paths)


def gen_media_info(pipe: Connection, path: str) -> None:
    cmd = [MEDIA_INFO, path]
    pipe.send(subprocess.check_output(cmd, text=True))
