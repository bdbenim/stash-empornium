# stash-empornium
This script by user humbaba allows torrent files and associated presentations to be created for empornium based on scenes from a local [stash](https://github.com/stashapp/stash) instance.

## Installation

### Using Docker

To run the backend as a docker container, copy and paste the following commands:
```bash
docker pull bdbenim/stash-empornium:latest
docker run -d \
--name stash-empornium \
-p 9932:9932 \
--mount type=bind,src=/path/to/config,target=/config
--mount type=bind,src=/path/to/save/torrents,target=/config/torrents \
--mount type=bind,src=/media,target=/media \
bdbenim/stash-empornium:latest
```

Make sure that the target for your `/media` mount matches what stash sees. You may have to change the target, not just the source, to achieve this.

### Without Using Docker

#### Dependencies
- Python3
  - flask
  - requests
  - vcsi
  - waitress (optional)
- ffmpeg
- mktorrent
- [Tampermonkey](https://www.tampermonkey.net)

Run the following commands to install the backend and dependencies:
```bash
git clone https://github.com/bdbenim/stash-empornium.git
cd stash-empornium
pip install -r requirements.txt
sudo apt-get install -y ffmpeg mktorrent
```

You can optionally install waitress as a production WSGI server:
```bash
pip install waitress
```

The userscript can be installed [here](https://github.com/bdbenim/stash-empornium/raw/main/emp_stash_fill.user.js). Place the other files on the same machine as your stash server and ensure dependencies are installed.

## Configuration
1. Visit `upload.php` and open the Tampermonkey menu. Set the backend URL, stash URL, and API key (if you use authentication).

2. Update config file located at `config/config.ini`:
```ini
[backend]
## name of a file in templates/ dir
default_template = fakestash-v2
## where torrents are placed
torrent_directory = /home/foobar/torrents
## port that the backend listens on
port = 9932

[stash]
## url of your stash instance
url = http://localhost:9999
## only needed if you set up authentication for stash
# api_key = 123abc.xyz
```
The port above corresponds to the backend URL in step 1, so if you change one you must change the other.

## Usage
1. Run `emp_stash_fill.py`
2. Get scene ID (it's in the url, e.g. for `http://localhost:9999/scenes/4123` the scene id is `4123`)
3. Go to `upload.php` and enter the scene ID in the "Fill from stash" box
4. Select the file you want if you have multiple files attached to that scene, tick/untick the generate screens box, pick template if you have defined others
5. Click "fill from" and wait as the tedious parts of the upload process are done for you. Status messages should appear and instructions for final steps. Performer tags like `pamela.anderson` will be generated for you, along with resolution tags and url tags of the studio, e.g. `1080p` and `brazzers.com`
6. You still need to load the torrent file (the location on your filesystem will be given to you) into the form, set a category, optionally check for dupes if you didn't do so manually. Also load the torrent file into your client (you can configure the torrent output directory to be a watch dir for your torrent client) and make sure the media file is visible to your torrent client
7. When you're satisfied everything is ready, upload

## Adding Templates
To add a new template, save it in the `templates` directory alongside your `config.ini` file. Then add it to your configuration with the following format:
```ini
[templates]
filename = description
```

Templates are written using Jinja syntax. The available variables are:
- audio_bitrate
- audio_codec
- bitrate
- contact_sheet
- container
- cover
- date
- details
- duration
- framerate
- image_count
- performers
  - name
  - details
    - image_remote_url
    - tag
- resolution
- screens
- sex_acts
- studio
- title
- video_codec

Refer to the default templates for examples of how they are used.

## Disclaimer
This tool is provided as-is. You must ensure that you have the proper rights for any files you share with other users, and always comply with applicable laws in your jurisdiction.
