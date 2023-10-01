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
import configupdater
import datetime
import json
import logging
import math
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import time
import uuid

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

##########
# CONFIG #
##########

template_dir = "/config/templates"

conf = configupdater.ConfigUpdater()
if not os.path.isfile("/config/config.ini"):
    logging.info("Config file not found, creating")
    if not os.path.exists("/config"):
        os.makedirs("/config")
    shutil.copyfile("default.ini", "/config/config.ini")
else:
    conf.read("/config/config.ini")

if not os.path.exists(template_dir):
    shutil.copytree("default-templates",template_dir,copy_function=shutil.copyfile)
installed_templates = os.listdir(template_dir)
for filename in os.listdir("default-templates"):
    src = os.path.join("default-templates", filename)
    if os.path.isfile(src):
        dst = os.path.join(template_dir, filename)
        if os.path.isfile(dst):
            try:
                with open(src) as srcFile, open(dst) as dstFile:
                    srcVer = int("".join(filter(str.isdigit,"0"+srcFile.readline())))
                    dstVer = int("".join(filter(str.isdigit,"0"+dstFile.readline())))
                    if srcVer > dstVer:
                        logging.info(f"Template \"{filename}\" has a new version available in the default-templates directory")
            except:
                logging.error(f"Couldn't compare version of {src} and {dst}")
        else:
            shutil.copyfile(src, dst)
            logging.info(f"Template {filename} has a been added. To use it, add it to config.ini under [templates]")
            if not conf["templates"].has_option(filename):
                tmpConf = configupdater.ConfigUpdater()
                tmpConf.read("default.ini")
                conf["templates"].set(filename, tmpConf["templates"][filename].value)

#TODO: better handling of unexpected values
STASH_URL = conf["stash"].get("url", "http://localhost:9999").value # type: ignore
assert STASH_URL is not None
PORT = int(conf["backend"].get("port", "9932").value) # type: ignore
DEFAULT_TEMPLATE = conf["backend"].get("default_template", "fakestash-v2").value # type: ignore
TORRENT_DIR = conf["backend"].get("torrent_directory", str(pathlib.Path.home())).value # type: ignore
assert TORRENT_DIR is not None
TAG_LISTS = {}
TAG_SETS = {}
for key in conf["empornium"]:
    TAG_LISTS[key] = list(map(lambda x: x.strip(), conf["empornium"][key].value.split(","))) # type: ignore
    TAG_SETS[key] = set()
assert "sex_acts" in TAG_LISTS # This is the only non-optional key because it is used by the default templates
TAGS_MAP = conf["empornium.tags"].to_dict()

template_names = conf["templates"].to_dict()

stash_headers = {
    "Content-type": "application/json",
}

if conf["stash"].has_option("api_key"):
    api_key = conf["stash"].get("api_key")
    assert api_key is not None
    api_key = api_key.value
    assert api_key is not None
    stash_headers["apiKey"] = api_key

stash_query = '''
findScene(id: "{}") {{
  title details director date studio {{ name url image_path parent_studio {{ url }} }} tags {{ name parents {{ name }} }} performers {{ name image_path tags {{ name }} }} paths {{ screenshot }}
  files {{ id path basename width height format duration video_codec audio_codec frame_rate bit_rate size }}
}}
'''

app = Flask(__name__, template_folder=template_dir)

def img_host_upload(token, cookies, img_path, img_mime_type, image_ext):
    # Quick and dirty resize for images above max filesize
    if os.path.getsize(img_path) > 5000000:
        CMD = ['ffmpeg','-i',img_path,'-vf','scale=iw:ih','-y',img_path]
        process = subprocess.run(CMD, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        while os.path.getsize(img_path) > 5000000:
            CMD = ['ffmpeg','-i',img_path,'-vf','scale="-1:ih*0.95"','-y',img_path]
            process = subprocess.run(CMD, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        logging.info(f"Resized {img_path}")

    files = { "source": (str(uuid.uuid4()) + "." + image_ext, open(img_path, 'rb'), img_mime_type) }
    request_body = {
        "thumb_width": 160,
        "thumb_height": 160,
        "thumb_crop": False,
        "medium_width": 800,
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
    if "error" in response.json():
        logging.error(f"Error uploading image: {response.json()['error']['message']}")
        return None
    return response.json()["image"]["image"]["url"]

@stream_with_context
def generate():
    j = request.get_json()
    scene_id = j["scene_id"]
    file_id  = j["file_id"]
    announce_url = j["announce_url"]
    gen_screens = j["screens"]

    template = j["template"] if "template" in j and j["template"] in os.listdir(app.template_folder) else DEFAULT_TEMPLATE
    assert template is not None

    tags = set()
    sex_acts = set()
    performers = {}
    screens = []
    studio_tag = ""


    #################
    # STASH REQUEST #
    #################

    stash_request_body = { "query": "{" + stash_query.format(scene_id) + "}" }
    stash_response = requests.post(urllib.parse.urljoin(STASH_URL, "/graphql"), json=stash_request_body, headers=stash_headers)

    # if not stash_response.status_code == 200:
    #     return jsonify({ "status": "error" })

    stash_response_body = stash_response.json()
    scene = stash_response_body["data"]["findScene"]

    # Ensure that all expected string keys are present
    str_keys = ["title", "details", "date"]
    for key in str_keys:
        if key not in scene:
            scene[key] = ""
        elif scene[key] == None:
            scene[key] = ""

    stash_file = None
    for f in scene["files"]:
        if f["id"] == file_id:
            # Apply remote path mappings
            logging.debug(f"Got path {f['path']} from stash")
            for remote,localopt in conf.items("file.maps"):
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
        yield json.dumps({
            "status": "error",
            "message": "Couldn't find file"
        })
        logging.error("No file exists")
        return
    elif not os.path.isfile(stash_file["path"]):
        yield json.dumps({
            "status": "error",
            "message": "Couldn't find file"
        })
        logging.error(f"Couldn't find file {stash_file['path']}")
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
    elif ht >= 3384 and ht < 4320:
        resolution = "6K"
    elif ht >= 4320 and ht < 8639:
        resolution = "8K"

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
    with open(cover_file[1], "wb") as fp:
        fp.write(cover_response.content)

    ###############
    # STUDIO LOGO #
    ###############

    studio_img_ext = ""
    sudio_img_mime_type = ""
    studio_img_file = None
    if "default=true" not in scene["studio"]["image_path"]:
        studio_img_response = requests.get(scene["studio"]["image_path"], headers=stash_headers)
        sudio_img_mime_type = studio_img_response.headers["Content-Type"]
        match sudio_img_mime_type:
            case "image/jpeg":
                studio_img_ext = "jpg"
            case "image/png":
                studio_img_ext = "png"
            case "image/svg+xml":
                studio_img_ext = "svg"
                # TODO: convert to png for upload
            case _:
                logging.error(f"Unknown studio logo file type: {sudio_img_mime_type}")
        studio_img_file = tempfile.mkstemp(suffix="." + studio_img_ext)
        with open(studio_img_file[1], "wb") as fp:
            fp.write(studio_img_response.content)
        if studio_img_ext == "svg" and shutil.which("rsvg-convert") is not None:
            png_file = tempfile.mkstemp(suffix=".png")
            CMD = ['rsvg-convert','-w','200',studio_img_file[1],'-o',png_file[1]]
            subprocess.run(CMD)
            os.remove(studio_img_file[1])
            studio_img_file = png_file
            sudio_img_mime_type = "image/png"
            studio_img_ext = "png"

    ##############
    # PERFORMERS #
    ##############

    for performer in scene["performers"]:
        # tag
        performer_tag = re.sub(r"[^\w\s]", "", performer["name"]).lower()
        performer_tag = re.sub(r"\s+", ".", performer_tag)
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

    audio_bitrate = ""
    cmd = ["ffprobe", "-v", "0", "-select_streams", "a:0", "-show_entries", "stream=bit_rate", "-of", "compact=p=0:nk=1", stash_file["path"]]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        audio_bitrate = f"{int(proc.stdout)//1000} kbps"
        
    except:
        logging.error("Unable to determine audio bitrate")
        audio_bitrate = "UNK"

    ###########
    # TORRENT #
    ###########

    yield json.dumps({
        "status": "success",
        "data": { "message": "Making torrent" }
    })
    piece_size = int(math.log(stash_file["size"]/2**10,2))
    tempdir = tempfile.TemporaryDirectory()
    temppath = os.path.join(tempdir.name, stash_file["basename"] + ".torrent")
    torrent_path = os.path.join(TORRENT_DIR, stash_file["basename"] + ".torrent")
    logging.info(f"Saving torrent to {temppath}")
    cmd = ["mktorrent", "-l", str(piece_size), "-s", "Emp", "-a", announce_url, "-p", "-v", "-o", temppath, stash_file["path"]]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    process.wait()
    if (process.returncode != 0):
        logging.error("mktorrent failed, command: " + " ".join(cmd))
        yield json.dumps({
            "status": "error",
            "message": "Couldn't generate torrent (does it already exist?)"
        })
        tempdir.cleanup()
        return
    shutil.move(temppath, torrent_path)
    tempdir.cleanup()
    logging.info(f"Moved torrent to {torrent_path}")


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
        for key in TAG_LISTS:
            if tag["name"] in TAG_LISTS[key]:
                TAG_SETS[key].add(tag["name"])
        emp_tag = TAGS_MAP.get(tag["name"])
        if emp_tag is not None:
            tags.add(emp_tag)
        for parent in tag["parents"]:
            for key in TAG_LISTS:
                if parent["name"] in TAG_LISTS[key]:
                    TAG_SETS[key].add(parent["name"])
            emp_tag = TAGS_MAP.get(parent["name"])
            if emp_tag is not None:
                tags.add(emp_tag)

    if scene["studio"]["url"] is not None:
        studio_tag = urllib.parse.urlparse(scene["studio"]["url"]).netloc.removeprefix("www.")
        tags.add(studio_tag)
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
    m = re.search(r"config\.auth_token\s*=\s*[\"'](\w+)[\"']", img_host_request.text)
    if m is None:
        yield json.dumps({
            "status": "success",
            "data": { "message": "Uploading images" }
        })
        logging.error("Unable to get auth token for image host.")
        return
    img_host_token = m.group(1)
    cookies = img_host_request.cookies
    cookies.set("AGREE_CONSENT", "1", domain="jerking.empornium.ph", path="/")
    cookies.set("CHV_COOKIE_LAW_DISPLAY", "0", domain="jerking.empornium.ph", path="/")

    logging.info("Uploading cover")
    cover_remote_url = img_host_upload(img_host_token, cookies, cover_file[1], cover_mime_type, cover_ext)
    if cover_remote_url is None:
        yield json.dumps({
            "status": "error",
            "data": { "message": "Failed to upload cover" }
        })
        return
    os.remove(cover_file[1])
    cover_url_parts = cover_remote_url.split(".")
    cover_resized_url = ".".join(cover_url_parts[:-1])+".md."+cover_url_parts[-1]
    logging.info("Uploading contact sheet")
    contact_sheet_remote_url = img_host_upload(img_host_token, cookies, contact_sheet_file[1], "image/jpeg", "jpg")
    if contact_sheet_remote_url is None:
        yield json.dumps({
            "status": "error",
            "data": { "message": "Failed to upload contact sheet" }
        })
        return
    os.remove(contact_sheet_file[1])
    logging.info("Uploading performer images")
    for performer_name in performers:
        performers[performer_name]["image_remote_url"] = img_host_upload(img_host_token,
                                                                         cookies,
                                                                         performers[performer_name]["image_path"],
                                                                         performers[performer_name]["image_mime_type"],
                                                                         performers[performer_name]["image_ext"])
        os.remove(performers[performer_name]["image_path"])
        if performers[performer_name]["image_remote_url"] is None:
            yield json.dumps({
                "status": "error",
                "data": { "message": f"Failed to upload image of {performer_name}" }
            })
            return

    logo_url = "https://jerking.empornium.ph/images/2022/02/21/stash41c25080a3611b50.png"
    if studio_img_file is not None and studio_img_ext != "" and sudio_img_mime_type != "image/svg+xml":
        logging.info("Uploading studio logo")
        logo_url = img_host_upload(img_host_token, cookies, studio_img_file[1], sudio_img_mime_type, studio_img_ext)
        if logo_url is None:
            yield json.dumps({
                "status": "error",
                "data": { "message": "Failed to upload studio logo" }
            })
            return

    logging.info("Uploading screens")
    screens_urls = []
    a = 1
    b = len(screens)
    for screen in screens:
        logging.info(f"Uploading screens ({a} of {b})")
        a += 1
        scrn_url = img_host_upload(img_host_token, cookies, screen, "image/jpeg", "jpg")
        if scrn_url is None:
            yield json.dumps({
                "status": "error",
                "data": { "message": "Failed to upload screens" }
            })
            return
        screens_urls.append(scrn_url)
        os.remove(screen)

    ############
    # TEMPLATE #
    ############

    # Sort tag sets into lists
    for key in TAG_SETS:
        TAG_SETS[key] = list(TAG_SETS[key])
        TAG_SETS[key].sort()

    # Prevent error in case date is missing
    date = scene["date"]
    if date != None and len(date) > 1:
        date = datetime.datetime.fromisoformat(date).strftime("%B %-d, %Y")

    logging.info("Rendering template")
    template_context = {
        "studio":        scene["studio"]["name"],
        "studio_logo":   logo_url,
        "studiotag":     studio_tag,
        "director":      scene["director"],
        "title":         scene["title"],
        "date":          date,
        "details":       scene["details"] if scene["details"] != "" else None,
        "duration":      str(datetime.timedelta(seconds=int(stash_file["duration"]))).removeprefix("0:"),
        "container":     stash_file["format"],
        "video_codec":   stash_file["video_codec"], 
        "audio_codec":   stash_file["audio_codec"],
        "audio_bitrate": audio_bitrate,
        "resolution":    "{}×{}".format(stash_file["width"], stash_file["height"]),
        "bitrate":       "{:.2f} Mb/s".format(stash_file["bit_rate"] / 2**20),
        "framerate":     "{} fps".format(stash_file["frame_rate"]),
        "screens":       screens_urls if len(screens_urls) else None,
        "contact_sheet": contact_sheet_remote_url,
        "performers":    performers,
        "cover":         cover_resized_url,
        "image_count":   0 #TODO
    }

    for key in TAG_SETS:
        template_context[key] = ", ".join(TAG_SETS[key])

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
    logging.info("Done")

@app.route('/fill', methods=["POST"])
def fill():
    return Response(generate(), mimetype="application/json") # type: ignore

@app.route('/templates')
def templates():
    return json.dumps(template_names)

if __name__ == "__main__":
    try:
        from waitress import serve
        serve(app, host='0.0.0.0', port=PORT)
    except:
        logging.info("Waitress not installed, using builtin server")
        app.run(host='0.0.0.0',port=PORT)

