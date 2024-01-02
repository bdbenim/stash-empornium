[![Docker Image Version](https://img.shields.io/docker/v/bdbenim/stash-empornium?logo=docker)
](https://hub.docker.com/repository/docker/bdbenim/stash-empornium) [![GitHub release](https://img.shields.io/github/v/release/bdbenim/stash-empornium?logo=github)
](https://github.com/bdbenim/stash-empornium/releases) ![PyPI - Python Version](https://img.shields.io/pypi/pyversions/stash-empornium) ![GitHub](https://img.shields.io/github/license/bdbenim/stash-empornium)

![logo](static/images/logo.svg)

# stash-empornium

This fork of a script by user humbaba allows torrent files and associated presentations to be created for empornium 
based on scenes from a local [stash][1] instance.

[1]: https://github.com/stashapp/stash

## Installation

The backend can be installed by cloning this repository or by running the Docker image [`bdbenim/stash-empornium`](https://hub.docker.com/r/bdbenim/stash-empornium).

For detailed instructions on installing the backend server, refer to the [Installation](https://github.com/bdbenim/stash-empornium/wiki/Installation) page on the wiki.

### Userscript

#### Dependencies

- [Tampermonkey](https://www.tampermonkey.net)

Currently, the script does not work with other userscript managers, though this may change in the future.

The userscript can be installed [here][2].

[2]: https://github.com/bdbenim/stash-empornium/raw/main/emp_stash_fill.user.js

## Configuration

1. Visit `upload.php` and open the Tampermonkey menu. Set the backend URL, stash URL, and API key (if you use
   authentication).

2. Update config file located at `config/config.ini`:

```toml
[backend]
## name of a file in templates/ dir
default_template = "fakestash-v2"
## List of directories where torrents are placed
## Multiple directories can be specified in this format:
## torrent_directories = ["/torrents", "/downloads"]
torrent_directories = ["/torrents"]
## port that the backend listens on
port = 9932

[stash]
## url of your stash instance
url = "http://localhost:9999"
## only needed if you set up authentication for stash
#api_key = 123abc.xyz
```

The port above corresponds to the backend URL in step 1, so if you change one you must change the other.

### Redis

The backend server can be configured to connect to an optional [redis][3] server. This is not required for any of the
functionality of the script, but it allows image URLs to be cached even when restarting the backend, speeding up the
upload process whenever an image is reused (e.g. performer images, studio logos). If redis is not used, these URLs will
still be cached in memory for as long as the server is running.

Connection settings can be specified in the `[redis]` configuration section:

```toml
[redis]
host = "localhost"
port = 6379
username = "stash-empornium"
password = "stash-empornium"
ssl = false
```

Any unused options can simply be omitted.

[3]: https://redis.io/

### Torrent Clients

The backend server can be configured to communicate with any of several different torrent clients, allowing
generated `.torrent` files to be automatically added to the client. Path mappings can also be used to ensure the torrent
points at the correct location of files on disk, allowing them to be started with minimal settings. Additionally, some
clients support applying labels to torrents for more granular control.

Torrent client integrations are optional and are not required for the backend to work.

#### rTorrent

This software has been tested with rTorrent `v0.9.6` with ruTorrent `v3.10`.

Example configuration:

```toml
[rtorrent]
# Hostname or IP address
host = "localhost"
# Port number
port = 8080
# Set to true for https
ssl = false
# API path, typically "XMLRPC" or "RPC2"
path = "RPC2"
# Username for XMLRPC if applicable (may be different from webui)
username = "user"
# Password for XMLRPC if applicable (may be different from webui)
password = "password"
label = "stash-empornium"

[rtorrent.pathmaps]
"/stash-empornium/path" = "/rtorrent/path"
```

> [!NOTE]
> The path mappings for the torrent client are with respect to the paths on the **backend server**, not stash. If your
> client is reporting errors that files are missing, make sure you check this setting carefully. For example, if your
> files are stored in `/media` on your stash server, and that directory is mapped to `/data` on your backend
> and `/downloads` in your torrent client, then you will need something like this in your config:
>
> ```toml
> ["file.maps"]
> "/media" = "/data"
> ...
> [rtorrent.pathmaps]
> "/data" = "/downloads"
> ```

### Deluge

This software has been tested with Deluge `v2.1.1`. The same configuration options are supported as with rTorrent, with
two exceptions:

- Labels are not supported
- No username is required for authentication

### qBittorrent

This software has been tested with qBittorrent `v4.6.0`. The same configuration options are supported as with rTorrent.

Currently there is one limitation with the qBittorrent API integration which prevents the backend from triggering a
recheck of downloaded files when adding a `.torrent`. This is planned for a future release.

## Usage

1. Run `emp_stash_fill.py`
2. Get scene ID (it's in the url, e.g. for `http://localhost:9999/scenes/4123` the scene id is `4123`)
3. Go to `upload.php` and enter the scene ID in the "Fill from stash" box
4. Select the file you want if you have multiple files attached to that scene, tick/untick the generate screens box,
   pick template if you have defined others
5. Click "fill from" and wait as the tedious parts of the upload process are done for you. Status messages should appear
   and instructions for final steps. Performer tags like `pamela.anderson` will be generated for you, along with
   resolution tags and url tags of the studio, e.g. `1080p` and `brazzers.com`
6. You still need to load the torrent file (the location on your filesystem will be given to you) into the form, set a
   category, optionally check for dupes if you didn't do so manually. Also load the torrent file into your client (you
   can configure the torrent output directory to be a watch dir for your torrent client) and make sure the media file is
   visible to your torrent client
7. When you're satisfied everything is ready, upload

### Within Stash

As of `v0.17.0`, a new button has been added to the scene page within Stash:

![Screenshot of Stash upload button](https://github.com/bdbenim/stash-empornium/assets/97994155/12ee111a-e358-4d99-abf3-95910b5fe289)

Clicking this button will launch `upload.php` and automatically fill in the form with the current scene. This feature is
still somewhat experimental, including the following issues:

- The script needs to save your tracker announce URL before this feature can work, which is done simply by navigating
  to `upload.php` with the script enabled.
- Clicking this button occasionally fails to fill in the form. If this happens, simply go back and try a second time.
    - This seems to happen more frequently when starting multiple uploads in quick succession from different tabs
- Currently this only works with the default settings of generating screenshots and excluding associated galleries. In
  the future, these options will be configurable.
- There may be other issues not mentioned above

### Including Galleries

Uploads can optionally include a gallery associated with a scene by checking the box labeled "Include Gallery?" on the
upload page. In order to generate a torrent with multiple files, they must be saved in a directory together, which
requires some additional configuration options:

```toml
[backend]
## Where to save media for torrents with more than one file:
media_directory = "/torrents"
## How to move files to media_directory. Must be 'copy', 'hardlink', or 'symlink'
move_method = 'copy'
```

The `media_directory` option specifies the parent directory where media files will be saved. Each torrent will get an
associated subdirectory here, based on the title of the scene.

`move_method` specifies how media files will be added to this new directory. The default is `copy` because it is the
most likely to work across different setups, but the downside is that this will create a duplicate of your media. To
avoid this, the `hardlink` or `symlink` options can be selected, but these have limitations. Symlinks point to the path
of the original file, which means that if your torrent client sees a different path structure than your backend server
then it won't be able to follow symlinks created by the backend. Hardlinks do not have this issue, but they can only be
created on the same file system as the original file. If you're using Docker, locations from the same file system added
via separate mount points will be treated as separate file systems and will not allow hardlinks between them. There are
additional pros and cons that are beyond the scope of this readme.

### Command Line Arguments

The script can be run with optional command line arguments, most of which override a corresponding configuration file
option. These can be used to quickly change a setting without needing to modify the config file, such as for temporarily
listening on a different port or saving torrent files in a different directory. Not all configuration options can
currently be set via the command line. The available options are described in the script's help text below:

```text
usage: emp_stash_fill.py [-h] [--configdir CONFIGDIR] [--version] [-q | -v | -l LEVEL] [--flush] [--no-cache | --overwrite]

backend server for EMP Stash upload helper userscript

options:
  -h, --help            show this help message and exit
  --configdir CONFIGDIR
                        specify the directory containing configuration files
  --version             show program's version number and exit

Output:
  options for setting the log level

  -q, --quiet           output less
  -v, --verbose, --debug
                        output more
  -l LEVEL, --log LEVEL
                        log level: [DEBUG | INFO | WARNING | ERROR | CRITICAL]

redis:
  options for connecting to a redis server

  --flush               flush redis cache
  --no-cache            do not retrieve cached values
  --overwrite           overwrite cached values
  ```

## Templates

This repository includes default templates which can be used to fill in the presentation based on data from stash.
Currently there are two, however more may be added in the future.

### Adding Templates

To add a new template, save it in the `templates` directory alongside your `config.ini` file. Then add it to your
configuration with the following format:

```toml
[templates]
filename = "description"
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
- gallery_contact
- image_count
- media_info (if `mediainfo` is installed)
- performers
    - name
    - details
        - image_remote_url
        - tag
- resolution
- screens
- sex_acts
- studio
- studio_logo
- title
- video_codec

Refer to the default templates for examples of how they are used.

### Custom Lists

In addition to the template variables described above, additional tag lists may be added to the `empornium` config
section by following the format of the `sex_acts` variable. These will automatically be parsed and made available to any
custom templates as comma-separated lists. For instance, you may wish to add a section called `performer_attributes` to
describe characteristics of performers in the scene.

## Titles

Similarly to templates, the title has a few options for formatting. This uses python's builtin string formatter, so
variable names are enclosed in braces (`{}`) within the string. The default title format is:

```python
[{studio}]
{performers} - {title}({date})[{resolution}]
```

This would result in something like this:

> [Blender Institute] Big Buck Bunny, Frank, Rinky, Gimera - Big Buck Bunny \(2008-05-10)[1080p]

The available variables that can be used are:

- codec
- date
- duration
- framerate
- performers
- resolution
- studio
- title

### Title Templates

Beginning with `v0.7.0`, the `title_template` config option has been added, which extends the title formatting
capability using jinja templates. With this system, the equivalent to the earlier example is:

```python
{ % if studio %}[{{studio}}]
{ % endif %}{{performers | join(', ')}}
{ % if performers %} - { % endif %}{{title}}
{ % if date %}({{date}})
{ % endif %}[{{resolution}}]
```

This system has the added advantage of builtin `if` statements, `for` loops, and many other features. The above example
uses these to ensure that there are no empty square brackets if the scene's studio is not set, nor empty parentheses
around a missing date. Since the resolution is determined by the script, this will always be available. The same
variables are available to this setting as the `title_default` option, with some minor differences:

- `performers` will be provided as a list rather than a single comma-separated string. This allows more control over how
  the list will be formatted, but the above example shows how to keep the same comma-separated list formatting.
- `framerate` does not include "fps" in the string, again for more flexibility in the template

For more information on using jinja templates, refer to the [documentation](https://jinja.palletsprojects.com/en/3.1.x/)
