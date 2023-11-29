import tomlkit
import argparse
import os
import logging
import shutil
from utils.customtypes import CaseInsensitiveDict, Singleton
from utils.torrentclients import TorrentClient, Deluge, Qbittorrent, RTorrent
from __main__ import __version__

stash_headers = {
    "Content-type": "application/json",
}

stash_query = """
findScene(id: "{}") {{
    title
    details
    director
    date
    galleries {{
        folder {{
            path
        }}
        files {{
            path
        }}
    }}
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
        eye_color
        fake_tits
        gender
        hair_color
        height_cm
        measurements
        piercings
        image_path
        tags {{
            name
        }}
        tattoos
    }}
    paths {{
        screenshot
        preview
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


class ConfigHandler(Singleton):
    initialized = False
    logger: logging.Logger
    log_level: int
    args: argparse.Namespace
    conf: tomlkit.TOMLDocument
    tagconf: tomlkit.TOMLDocument
    port: int
    username: str
    password: str
    torrent_dirs: list[str]
    template_dir: str
    template_names: dict[str, str]
    config_file: str
    tag_config_file: str
    torrent_clients: list[TorrentClient] = []

    def __init__(self):
        if not (self.initialized):
            self.parse_args()
            self.logging_init()
            self.configure()
            self.initialized = True

    def logging_init(self) -> None:
        self.log_level = getattr(logging, self.args.log) if self.args.log else min(10 * self.args.level, 50)
        logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=self.log_level)
        self.logger = logging.getLogger(__name__)

    def parse_args(self) -> None:
        parser = argparse.ArgumentParser(description="backend server for EMP Stash upload helper userscript")
        parser.add_argument(
            "--configdir",
            default=[os.path.join(os.getcwd(), "config")],
            help="specify the directory containing configuration files",
            nargs=1,
        )
        parser.add_argument("--version", action="version", version=f"stash-empornium {__version__}")
        mutex = parser.add_argument_group("Output", "options for setting the log level").add_mutually_exclusive_group()
        mutex.add_argument("-q", "--quiet", dest="level", action="count", default=2, help="output less")
        mutex.add_argument(
            "-v", "--verbose", "--debug", dest="level", action="store_const", const=1, help="output more"
        )
        mutex.add_argument(
            "-l",
            "--log",
            choices=["DEBUG", "INFO", "WARN", "WARNING", "ERROR", "CRITICAL", "FATAL"],
            metavar="LEVEL",
            help="log level: [DEBUG | INFO | WARNING | ERROR | CRITICAL]",
            type=str.upper,
        )

        redisgroup = parser.add_argument_group("redis", "options for connecting to a redis server")
        redisgroup.add_argument("--flush", help="flush redis cache", action="store_true")
        cache = redisgroup.add_mutually_exclusive_group()
        cache.add_argument("--no-cache", help="do not retrieve cached values", action="store_true")
        cache.add_argument("--overwrite", help="overwrite cached values", action="store_true")

        self.args = parser.parse_args()

    def renameKey(self, section: str, oldkey: str, newkey: str, conf: tomlkit.TOMLDocument) -> None:
        if oldkey in conf[section]:  # type: ignore
            conf[section][newkey] = self.conf[section][oldkey]  # type: ignore
            del conf[section][oldkey]  # type: ignore
            self.update_file()
            self.logger.info(f"Key '{oldkey}' renamed to '{newkey}'")

    def update_file(self) -> None:
        with open(self.config_file, "w") as f:
            tomlkit.dump(self.conf, f)
        with open(self.tag_config_file, "w") as f:
            tomlkit.dump(self.tagconf, f)

    def backup_config(self) -> None:
        conf_bak = self.config_file + ".bak"
        tags_bak = self.tag_config_file + ".bak"
        if os.path.isfile(self.config_file):
            shutil.copy(self.config_file, conf_bak)
        if os.path.isfile(self.tag_config_file):
            shutil.copy(self.tag_config_file, tags_bak)

    def configure(self) -> None:
        self.config_dir = self.args.configdir[0]

        self.template_dir = os.path.join(self.config_dir, "templates")
        self.config_file = os.path.join(self.config_dir, "config.toml")
        self.tag_config_file = os.path.join(self.config_dir, "tags.toml")

        # Ensure config file is present
        if not os.path.isfile(self.config_file):
            self.logger.info(f"Config file not found at {self.config_file}, creating")
            if not os.path.exists(self.config_dir):
                os.makedirs(self.config_dir)
            with open("default.toml") as f:
                self.conf = tomlkit.load(f)
        else:
            self.logger.info(f"Reading config from {self.config_file}")
            try:
                with open(self.config_file) as f:
                    self.conf = tomlkit.load(f)
            except Exception as e:
                self.logger.critical(f"Failed to read config file: {e}")
                exit(1)
        with open("default.toml") as f:
            default_conf = tomlkit.load(f)
        for section in default_conf:
            if section not in self.conf:
                s = tomlkit.table(True)
                s.add(tomlkit.comment("Section added from default.toml"))
                self.conf.append(section, s)
            for option in default_conf[section]:  # type: ignore
                if option not in self.conf[section]:
                    self.conf[section].add(tomlkit.comment("Option imported automatically:"))  # type: ignore
                    value = default_conf[section][option]  # type: ignore
                    self.conf[section][option] = value  # type: ignore
                    self.logger.info(
                        f"Automatically added option '{option}' to section [{section}] with value '{value}'"
                    )
        try:
            if os.path.isfile(self.tag_config_file):
                self.logger.debug(f"Found tag config at {self.tag_config_file}")
                with open(self.tag_config_file) as f:
                    self.tagconf = tomlkit.load(f)
            else:
                self.logger.info(f"Config file not found at {self.tag_config_file}, creating")
                self.tagconf = tomlkit.document()
                if "empornium" in self.conf:
                    emp = self.conf["empornium"]
                    self.tagconf.append("empornium", emp)  # type: ignore
                    del self.conf["empornium"]
                if "empornium.tags" in self.conf:
                    emptags = self.conf["empornium.tags"]
                    if "empornium" not in self.tagconf:
                        self.tagconf.append("empornium", tomlkit.table(True))
                    self.tagconf["empornium"].append("tags", emptags)  # type: ignore
                    del self.conf["empornium.tags"]
                else:
                    with open("default-tags.toml") as f:
                        self.tagconf = tomlkit.load(f)
            with open("default-tags.toml") as f:
                default_tags = tomlkit.load(f)
            if "empornium" not in self.tagconf:
                emp = tomlkit.table(True)
                emp.append("tags", tomlkit.table(False))
                self.tagconf.append("empornium", emp)
            for option in default_tags["empornium"]:  # type: ignore
                if option not in self.tagconf["empornium"]:
                    self.tagconf["empornium"].add(tomlkit.comment("Option imported automatically"))  # type: ignore
                    value = default_tags["empornium"][option]  # type: ignore
                    self.tagconf["empornium"][option] = value  # type: ignore
            for tag in default_tags["empornium"]["tags"]:  # type: ignore
                if tag not in self.tagconf["empornium"]["ignored_tags"] and tag not in self.tagconf["empornium"]["tags"]:  # type: ignore
                    value = default_tags["empornium"]["tags"][tag]  # type: ignore
                    self.tagconf["empornium"]["tags"][tag] = value  # type: ignore
        except Exception as e:
            self.logger.error(f"Failed to read tag config file: {e}")
        try:
            self.backup_config()
            self.update_file()
        except:
            self.logger.error("Unable to save updated config")

        if not os.path.exists(self.template_dir):
            shutil.copytree("default-templates", self.template_dir, copy_function=shutil.copyfile)
        self.installed_templates = os.listdir(self.template_dir)
        for filename in os.listdir("default-templates"):
            src = os.path.join("default-templates", filename)
            if os.path.isfile(src):
                dst = os.path.join(self.template_dir, filename)
                if os.path.isfile(dst):
                    try:
                        with open(src) as srcFile, open(dst) as dstFile:
                            srcVer = int("".join(filter(str.isdigit, "0" + srcFile.readline())))
                            dstVer = int("".join(filter(str.isdigit, "0" + dstFile.readline())))
                            if srcVer > dstVer:
                                self.logger.info(
                                    f'Template "{filename}" has a new version available in the default-templates directory'
                                )
                    except:
                        self.logger.error(f"Couldn't compare version of {src} and {dst}")
                else:
                    shutil.copyfile(src, dst)
                    self.logger.info(
                        f"Template {filename} has a been added. To use it, add it to config.ini under [templates]"
                    )
                    if filename not in self.conf["templates"]:  # type: ignore
                        with open("default.toml") as f:
                            tmpConf = tomlkit.load(f)
                        conf["templates"][filename] = tmpConf["templates"][filename]  # type: ignore

        self.torrent_dirs = list(self.conf["backend"]["torrent_directories"])  # type: ignore
        assert self.torrent_dirs is not None and len(self.torrent_dirs) > 0
        for dir in self.torrent_dirs:
            if not os.path.isdir(dir):
                if os.path.isfile(dir):
                    self.logger.error(f"Cannot use {dir} for torrents, path is a file")
                    self.torrent_dirs.remove(dir)
                    exit(1)
                self.logger.info(f"Creating directory {dir}")
                os.makedirs(dir)
        self.logger.debug(f"Torrent directories: {self.torrent_dirs}")
        if len(self.torrent_dirs) == 0:
            self.logger.critical("No valid output directories found")
            exit(1)

        self.template_names = {}
        template_files = os.listdir(self.template_dir)
        for k in self.items("templates"):
            if k in template_files:
                self.template_names[k] = str(self.get("templates", k))
            else:
                self.logger.warning(f"Template {k} from config.toml is not present in {self.template_dir}")

        if "api_key" in self.conf["stash"]:  # type: ignore
            api_key = self.get("stash", "api_key")
            assert api_key is not None
            stash_headers["apiKey"] = str(api_key)

        self.configureTorrents()

    def configureTorrents(self) -> None:
        self.torrent_clients.clear()
        clients = {"rtorrent": RTorrent, "deluge": Deluge, "qbittorrent": Qbittorrent}
        for client, clientType in clients.items():
            assert issubclass(clientType, TorrentClient)
            try:
                if client in self.conf and not self.get(client, "disable", False):
                    settings = dict(self.conf[client])  # type: ignore
                    tc = clientType(settings)
                    if tc.connected():
                        self.torrent_clients.append(tc)
                    else:
                        self.logger.error(f"Could not connect to {client}")
            except:
                pass
        self.logger.debug(f"Configured {len(self.torrent_clients)} torrent client(s)")

    def get(self, section: str, key: str, default=None):
        if section in self.conf:
            if key in self.conf[section]:  # type: ignore
                return self.conf[section][key]  # type: ignore
        if section in self.tagconf and key in self.tagconf[section]:  # type: ignore
            return self.tagconf[section][key]  # type: ignore
        return default

    def set(self, section: str, key: str, value) -> None:
        if section not in self.conf:
            if section in self.tagconf:
                self.tagconf[section][key] = value  # type: ignore
                return
            self.conf[section] = {}
        self.conf[section][key] = value  # type: ignore

    def delete(self, section: str, key: str | None = None) -> None:
        if section in self.conf:
            if key:
                if key in self.conf[section]:  # type: ignore
                    del self.conf[section][key]  # type: ignore
            else:
                del self.conf[section]
        elif section in self.tagconf:
            if key:
                if key in self.tagconf[section]:  # type: ignore
                    del self.tagconf[section][key]  # type: ignore
            else:
                del self.tagconf[section]

    def items(self, section: str) -> dict:
        if section in self.conf:
            return CaseInsensitiveDict(self.conf[section])  # type: ignore
        if section in self.tagconf:
            return CaseInsensitiveDict(self.tagconf[section])  # type: ignore
        return {}

    def __iter__(self):
        for section in self.conf:
            yield section

    def __contains__(self, __key: object) -> bool:
        return self.conf.__contains__(__key) or self.tagconf.__contains__(__key)

    def __getitem__(self, key: str):
        return self.conf.__getitem__(key) if self.conf.__contains__(key) else self.tagconf.__getitem__(key)
