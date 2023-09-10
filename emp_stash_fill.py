#!/usr/bin/env python3
"""A mini service that generates upload material for EMP

Generate and upload screenshots and contact sheet, generate torrent
details from a template, generate torrent file, etc. to easily fill
the EMP upload form.

Required external utilities:
ffmpeg
vcsi
mktorrent

Required Python modules:
Flask
requests
"""

__author__    = "An EMP user"
__license__   = "unlicense"
__version__   = "0.1.0"

# external
import requests
from flask import Flask, Response, jsonify, request, stream_with_context, render_template

# built-in
import configparser
import datetime
import json
import logging
import math
import os
import pathlib
import re
import subprocess
import tempfile
import urllib.parse
import time
import uuid

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

conf = configparser.ConfigParser()
conf.read("config")

STASH_URL = conf["stash"].get("url", "http://localhost:9999")
PORT = int(conf["backend"].get("port", 9932))
DEFAULT_TEMPLATE = conf["backend"].get("default_template", "fakestash-v2")
TORRENT_DIR = conf["backend"].get("torrent_directory", str(pathlib.Path.home()))
TAGS_SEX_ACTS = list(map(lambda x: x.strip(), conf["empornium"]["sex_acts"].split(",")))
TAGS_MAP = conf["empornium.tags"]

with open("templates.json") as fp:
    template_names = json.load(fp)

stash_headers = {
    "Content-type": "application/json",
}

if conf["stash"].get("api_key"):
    stash_headers["apiKey"] = conf["stash"].get("api_key")

stash_query = '''
findScene(id: "{}") {{
  title details date studio {{ name url parent_studio {{ url }} }} tags {{ name }} performers {{ name image_path tags {{ name }} }} paths {{ screenshot }}
  files {{ id path basename width height format duration video_codec audio_codec frame_rate bit_rate size }}
}}
'''

app = Flask(__name__)

def img_host_upload(token, cookies, img_path, img_mime_type, image_ext):
    files = { "source": (str(uuid.uuid4()) + "." + image_ext, open(img_path, 'rb'), img_mime_type) }
    request_body = {
        "thumb_width": 160,
        "thumb_height": 160,
        "thumb_crop": False,
        "medium_width": 500,
        "medium_crop": "false",
        "type": "file",
        "action": "upload",
        "timestamp": int(time.time() * 1e3), # ??
        "auth_token": token,
        "nsfw": 0
    }
    headers = {
        "accept": "application/json",
        "origin": "https://jerking.empornium.ph",
        "referer": "https://jerking.empornium.ph/",
    }
    url = "https://jerking.empornium.ph/json"
    response = requests.post(url, files=files, data=request_body, cookies=cookies, headers=headers)
    return response.json()["image"]["image"]["url"]

@stream_with_context
def generate():
    j = request.json
    scene_id = j["scene_id"]
    file_id  = j["file_id"]
    announce_url = j["announce_url"]
    gen_screens = j["screens"]

    template = j["template"] if "template" in j and j["template"] in os.listdir(app.template_folder) else DEFAULT_TEMPLATE

    tags = set()
    sex_acts = []
    performers = {}
    screens = []


    #################
    # STASH REQUEST #
    #################

    stash_request_body = { "query": "{" + stash_query.format(scene_id) + "}" }
    stash_response = requests.post(urllib.parse.urljoin(STASH_URL, "/graphql"), json=stash_request_body, headers=stash_headers)

    # if not stash_response.status_code == 200:
    #     return jsonify({ "status": "error" })

    stash_response_body = stash_response.json()
    scene = stash_response_body["data"]["findScene"]

    stash_file = None
    for f in scene["files"]:
        if f["id"] == file_id:
            stash_file = f
            break

    if stash_file is None:
        yield json.dumps({
            "status": "error",
            "message": "Couldn't find file"
        })
        return

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
    elif ht >= 1920 and ht < 2160:
        resolution = "1920p"
    elif ht >= 2160 and ht < 2880:
        resolution = "2160p"
    elif ht >= 2880 and ht < 3384:
        resolution = "2880p"
    # elif ht >= 3384 and ht < 4320:
    #     resolution = "6K"
    # elif ht >= 4320 and ht < 8639:
    #     resolution = "8K"

    if resolution is not None:
        tags.add(resolution)


    #########
    # COVER #
    #########

    cover_response = requests.get(scene["paths"]["screenshot"], headers=stash_headers)
    cover_mime_type = cover_response.headers["Content-Type"]
    cover_ext = ""
    if cover_mime_type == "image/jpeg":
        cover_ext = "jpg"
    elif cover_mime_type == "image/png":
        cover_ext = "png"
    cover_file = tempfile.mkstemp(suffix="." + cover_ext)
    cover_file_resized = tempfile.mkstemp(suffix="." + cover_ext)
    with open(cover_file[1], "wb") as fp:
        fp.write(cover_response.content)
    with open(cover_file_resized[1], "wb") as fp:
        fp.write(cover_response.content)
    cmd = ["convert","-resize","800x",cover_file_resized[1],cover_file_resized[1]]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    process.wait()


    ##############
    # PERFORMERS #
    ##############

    for performer in scene["performers"]:
        # tag
        performer_tag = re.sub("[^\w\s]", "", performer["name"]).lower()
        performer_tag = re.sub("\s+", ".", performer_tag)
        tags.add(performer_tag)
        # also include alias tags?
        
        for tag in performer["tags"]:
            emp_tag = TAGS_MAP.get(tag["name"])
            if emp_tag is not None:
                tags.add(emp_tag)

        # image
        performer_image_response = requests.get(performer["image_path"], headers=stash_headers)
        performer_image_mime_type = cover_response.headers["Content-Type"]
        performer_image_ext = ""
        if performer_image_mime_type == "image/jpeg":
            performer_image_ext = "jpg"
        elif performer_image_mime_type == "image/png":
            performer_image_ext = "png"
        performer_image_file = tempfile.mkstemp(suffix=performer_image_ext)
        with open(performer_image_file[1], "wb") as fp:
            fp.write(performer_image_response.content)

        # store data
        performers[performer["name"]] = {
            "image_path": performer_image_file[1],
            "image_mime_type": performer_image_mime_type,
            "image_ext": performer_image_ext,
            "image_remote_url": None,
            "tag": performer_tag
        }


    #################
    # CONTACT SHEET #
    #################

    # upload images and paste in description
    contact_sheet_file = tempfile.mkstemp(suffix=".jpg")
    print(stash_file["path"])
    cmd = ["vcsi", stash_file["path"], "-g", "3x10", "-o", contact_sheet_file[1]]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    yield json.dumps({
        "status": "success",
        "data": { "message": "Generating contact sheet" }
    })
    process.wait()
    if (process.returncode != 0):
        logging.error("vcsi failed")
        yield json.dumps({
            "status": "error",
            "message": "Couldn't generate contact sheet"
        })
        return


    ###########
    # SCREENS #
    ###########

    num_frames = 10
    if (gen_screens):
        logging.info(f"Generating screens for {stash_file['path']}")
        yield json.dumps({
            "status": "success",
            "data": { "message": "Generating screenshots" }
        })

        for seek in map(lambda i: stash_file["duration"]*(0.05 + i/(num_frames-1)*0.9), range(num_frames)):
            screen_file = tempfile.mkstemp(suffix=".jpg")
            screens.append(screen_file[1])
            cmd = ["ffmpeg","-v","error","-y","-ss",str(seek),"-i",stash_file["path"],"-frames:v","1","-vf","scale=960:-2",screen_file[1]]
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            process.wait()


    ###########
    # TORRENT #
    ###########

    yield json.dumps({
        "status": "success",
        "data": { "message": "Making torrent" }
    })
    piece_size = int(math.log(stash_file["size"]/2**10,2))
    torrent_path = os.path.join(TORRENT_DIR, stash_file["basename"] + ".torrent")
    cmd = ["mktorrent", "-l", str(piece_size), "-a", announce_url, "-p", "-v", "-o", torrent_path, stash_file["path"]]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    process.wait()
    if (process.returncode != 0):
        logging.error("mktorrent failed, command: " + " ".join(cmd))
        yield json.dumps({
            "status": "error",
            "message": "Couldn't generate torrent (does it already exist?)"
        })
        return


    #########
    # TITLE #
    #########

    title = "[{studio}] {performers} - {title} ({date}){resolution}".format(
        studio = scene["studio"]["name"],
        performers = ", ".join([p["name"] for p in scene["performers"]]),
        title = scene["title"],
        date = scene["date"],
        resolution = f" [{resolution}]" if resolution is not None else ""
    )


    ########
    # TAGS #
    ########

    for tag in scene["tags"]:
        if tag["name"] in TAGS_SEX_ACTS:
            sex_acts.append(tag["name"])
        emp_tag = TAGS_MAP.get(tag["name"])
        if emp_tag is not None:
            tags.add(emp_tag)

    if scene["studio"]["url"] is not None:
        tags.add(urllib.parse.urlparse(scene["studio"]["url"]).netloc.removeprefix("www."))
    if scene["studio"]["parent_studio"] is not None and scene["studio"]["parent_studio"]["url"] is not None:
        tags.add(urllib.parse.urlparse(scene["studio"]["parent_studio"]["url"]).netloc.removeprefix("www."))


    ##########
    # UPLOAD #
    ##########

    yield json.dumps({
        "status": "success",
        "data": { "message": "Uploading images" }
    })

    img_host_request = requests.get("https://jerking.empornium.ph/json")
    m = re.search("config\.auth_token\s*=\s*[\"'](\w+)[\"']", img_host_request.text)
    img_host_token = m.group(1)
    cookies = img_host_request.cookies
    cookies.set("AGREE_CONSENT", "1", domain="jerking.empornium.ph", path="/")
    cookies.set("CHV_COOKIE_LAW_DISPLAY", "0", domain="jerking.empornium.ph", path="/")

    logging.info("Uploading cover")
    cover_remote_url = img_host_upload(img_host_token, cookies, cover_file[1], cover_mime_type, cover_ext)
    os.remove(cover_file[1])
    logging.info("Uploading resized cover")
    cover_resized_url = img_host_upload(img_host_token, cookies, cover_file_resized[1], cover_mime_type, cover_ext)
    os.remove(cover_file_resized[1])
    logging.info("Uploading contact sheet")
    contact_sheet_remote_url = img_host_upload(img_host_token, cookies, contact_sheet_file[1], "image/jpeg", "jpg")
    os.remove(contact_sheet_file[1])
    logging.info("Uploading performer images")
    for performer_name in performers:
        performers[performer_name]["image_remote_url"] = img_host_upload(img_host_token,
                                                                         cookies,
                                                                         performers[performer_name]["image_path"],
                                                                         performers[performer_name]["image_mime_type"],
                                                                         performers[performer_name]["image_ext"])
        os.remove(performers[performer_name]["image_path"])

    logging.info("Uploading screens")
    screens_urls = []
    for screen in screens:
        screens_urls.append(img_host_upload(img_host_token, cookies, screen, "image/jpeg", "jpg"))
        os.remove(screen)

    # cover_remote_url = "https://jerking.empornium.ph/images/2023/03/15/7f3b4ff47bc5b7e213a_c.jpg"

    ############
    # TEMPLATE #
    ############

    # also delete local files
    template_context = {
        "title":         scene["title"],
        "date":          datetime.datetime.fromisoformat(scene["date"]).strftime("%B %-d, %Y"),
        "details":       scene["details"] if scene["details"] != "" else None,
        "sex_acts":      ", ".join(sex_acts),
        "duration":      str(datetime.timedelta(seconds=int(stash_file["duration"]))).removeprefix("0:"),
        "container":     stash_file["format"],
        "codec":         "{}/{}".format(stash_file["video_codec"], stash_file["audio_codec"]),
        "resolution":    "{}×{}".format(stash_file["width"], stash_file["height"]),
        "bitrate":       "{:.2f} Mb/s".format(stash_file["bit_rate"] / 2**20),
        "framerate":     "{} fps".format(stash_file["frame_rate"]),
        "screens":       screens_urls if len(screens_urls) else None,
        "contact_sheet": contact_sheet_remote_url,
        "performers":    performers,
        "cover":         cover_resized_url
    }
    description = render_template(template, **template_context)

    yield json.dumps({
        "status": "success",
        "data": {
            "message": "Done",
            "fill": {
                "title": title,
                "cover": cover_remote_url,
                "tags": " ".join(tags),
                "description": description,
                "torrent_path": torrent_path,
                "file_path": stash_file["path"]
            }
        }
    })

@app.route('/fill', methods=["POST"])
def fill():
    return Response(generate(), mimetype="application/json")

@app.route('/templates')
def templates():
    return template_names

if __name__ == "__main__":
    app.run(port=PORT)

