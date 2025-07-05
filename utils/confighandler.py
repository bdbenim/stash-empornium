import argparse
import sys

from loguru import logger
import os
import shutil

import tomlkit
from pydantic import ValidationError

from utils.models import Config
from utils.customtypes import CaseInsensitiveDict, Singleton
from utils.torrentclients import TorrentClient, Deluge, Qbittorrent, RTorrent, Transmission

LOG_MESSAGE_FORMAT = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{module}</cyan> - <level>{message}</level>"
DEBUG_MESSAGE_FORMAT = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{module}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"

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


def logging_init(log: str, level: int = 0) -> None:
    def level_filter(level_name):
        def is_level(record):
            return record["level"].name == level_name

        return is_level

    logger.remove(1)

    match log.upper():
        case "DEBUG":
            print("Debug mode")
            logger.add(sys.stderr, filter=level_filter("DEBUG"),
                       format=DEBUG_MESSAGE_FORMAT)
            logger.add(sys.stderr, level="INFO",
                       format=LOG_MESSAGE_FORMAT)
        case "INFO":
            logger.add(sys.stderr, level="INFO", format=LOG_MESSAGE_FORMAT)
        case "WARNING":
            logger.add(sys.stderr, level="WARNING", format=LOG_MESSAGE_FORMAT)
        case "ERROR":
            logger.add(sys.stderr, level="ERROR", format=LOG_MESSAGE_FORMAT)
        case "CRITICAL":
            logger.add(sys.stderr, level="CRITICAL", format=LOG_MESSAGE_FORMAT)
        case _:
            match level:
                case 1:
                    logger.add(sys.stderr, filter=level_filter("DEBUG"),
                               format=DEBUG_MESSAGE_FORMAT)
                    logger.add(sys.stderr, level="INFO",
                               format=LOG_MESSAGE_FORMAT)
                case 3:
                    logger.add(sys.stderr, level="WARNING", format=LOG_MESSAGE_FORMAT)
                case 4:
                    logger.add(sys.stderr, level="ERROR", format=LOG_MESSAGE_FORMAT)
                case 5:
                    logger.add(sys.stderr, level="CRITICAL", format=LOG_MESSAGE_FORMAT)
                case _:
                    logger.add(sys.stderr, level="INFO", format=LOG_MESSAGE_FORMAT)


class ConfigHandler(Singleton):
    initialized = False
    log_level: int
    args: argparse.Namespace
    conf: tomlkit.TOMLDocument
    tag_conf: tomlkit.TOMLDocument
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
        if not self.initialized:
            # Default to INFO
            logger.remove(0)
            logger.add(sys.stderr, level="INFO", format=LOG_MESSAGE_FORMAT)

            self.parse_args()
            if self.args.log != "NOTSET" or self.args.level != 2:
                logging_init(self.args.log, self.args.level)
            self.configure()
            self.initialized = True

    def parse_args(self) -> None:
        parser = argparse.ArgumentParser(description="backend server for EMP Stash upload helper userscript")
        parser.add_argument(
            "--configdir",
            default=[os.path.join(os.getcwd(), "config")],
            help="specify the directory containing configuration files",
            nargs=1,
        )
        mutex = parser.add_argument_group("Output", "options for setting the log level").add_mutually_exclusive_group()
        mutex.add_argument("-q", "--quiet", dest="level", action="count", default=2, help="output less")
        mutex.add_argument(
            "-v", "--verbose", "--debug", dest="level", action="store_const", const=1, help="output more"
        )
        mutex.add_argument(
            "-l",
            "--log",
            choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            metavar="LEVEL",
            help="log level: [DEBUG | INFO | WARNING | ERROR | CRITICAL]",
            type=str.upper,
            default="NOTSET",
        )

        redis_group = parser.add_argument_group("redis", "options for connecting to a redis server")
        redis_group.add_argument("--flush", help="flush redis cache", action="store_true")
        cache = redis_group.add_mutually_exclusive_group()
        cache.add_argument("--no-cache", help="do not retrieve cached values", action="store_true")
        cache.add_argument("--overwrite", help="overwrite cached values", action="store_true")

        self.args = parser.parse_args()

    def rename_key(self, section: str, old_key: str, new_key: str, conf: tomlkit.TOMLDocument) -> None:
        if old_key in conf[section]:  # type: ignore
            conf[section][new_key] = self.conf[section][old_key]  # type: ignore
            del conf[section][old_key]  # type: ignore
            self.update_file()
            logger.info(f"Key '{old_key}' renamed to '{new_key}'")

    def update_file(self) -> None:
        with open(self.config_file, "w") as f:
            tomlkit.dump(self.conf, f)
        with open(self.tag_config_file, "w") as f:
            tomlkit.dump(self.tag_conf, f)

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
            logger.info(f"Config file not found at {self.config_file}, creating")
            if not os.path.exists(self.config_dir):
                os.makedirs(self.config_dir)
            with open("default.toml") as f:
                self.conf = tomlkit.load(f)
        else:
            logger.debug(f"Reading config from {self.config_file}")
            try:
                with open(self.config_file) as f:
                    self.conf = tomlkit.load(f)
                    self.migrate()
            except Exception as e:
                logger.critical(f"Failed to read config file: {e}")
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
                    logger.info(
                        f"Automatically added option '{option}' to section [{section}] with value '{value}'"
                    )
        try:
            if os.path.isfile(self.tag_config_file):
                logger.debug(f"Found tag config at {self.tag_config_file}")
                with open(self.tag_config_file) as f:
                    self.tag_conf = tomlkit.load(f)
            else:
                logger.info(f"Config file not found at {self.tag_config_file}, creating")
                self.tag_conf = tomlkit.document()
                if "empornium" in self.conf:
                    emp = self.conf["empornium"]
                    self.tag_conf.append("empornium", emp)  # type: ignore
                    del self.conf["empornium"]
                if "empornium.tags" in self.conf:
                    emptags = self.conf["empornium.tags"]
                    if "empornium" not in self.tag_conf:
                        self.tag_conf.append("empornium", tomlkit.table(True))
                    self.tag_conf["empornium"].append("tags", emptags)  # type: ignore
                    del self.conf["empornium.tags"]
                else:
                    with open("default-tags.toml") as f:
                        self.tag_conf = tomlkit.load(f)
            with open("default-tags.toml") as f:
                default_tags = tomlkit.load(f)
            if "empornium" not in self.tag_conf:
                emp = tomlkit.table(True)
                emp.append("tags", tomlkit.table(False))
                self.tag_conf.append("empornium", emp)
            for option in default_tags["empornium"]:  # type: ignore
                if option not in self.tag_conf["empornium"]:
                    self.tag_conf["empornium"].add(tomlkit.comment("Option imported automatically"))  # type: ignore
                    value = default_tags["empornium"][option]  # type: ignore
                    self.tag_conf["empornium"][option] = value  # type: ignore
            for tag in default_tags["empornium"]["tags"]:  # type: ignore
                if tag not in self.tag_conf["empornium"]["ignored_tags"] and tag not in self.tag_conf["empornium"][
                    "tags"]:  # type: ignore
                    value = default_tags["empornium"]["tags"][tag]  # type: ignore
                    self.tag_conf["empornium"]["tags"][tag] = value  # type: ignore
        except Exception as e:
            logger.error(f"Failed to read tag config file: {e}")
        try:
            # TODO warn about extra settings
            Config.model_validate(self.conf)
            self.backup_config()
            self.update_file()
        except ValidationError as e:
            logger.critical(f"Config file error: {e}")
            exit(1)
        except Exception as e:
            logger.error(f"Unable to save updated config: {e}")

        # Set log level from config if it wasn't passed as an argument
        if self.args.log == "NOTSET" and self.args.level == 2:
            level = "INFO"
            try:
                level = self.conf["backend"]["log_level"].upper()
                assert level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
            except KeyError:
                pass
            except AssertionError:
                logger.warning(f"Invalid log level \"{self.conf["backend"]["log_level"]}\". Should be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL. Defaulting to INFO")
            logging_init(level)

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
                                logger.info(
                                    f'Template "{filename}" has a new version available in the default-templates directory'
                                )
                    except:
                        logger.error(f"Couldn't compare version of {src} and {dst}")
                else:
                    shutil.copyfile(src, dst)
                    logger.info(
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
                    logger.error(f"Cannot use {dir} for torrents, path is a file")
                    self.torrent_dirs.remove(dir)
                    exit(1)
                logger.info(f"Creating directory {dir}")
                os.makedirs(dir)
        logger.debug(f"Torrent directories: {self.torrent_dirs}")
        if len(self.torrent_dirs) == 0:
            logger.critical("No valid output directories found")
            exit(1)

        self.template_names = {}
        template_files = os.listdir(self.template_dir)
        for k in self.items("templates"):
            if k in template_files:
                self.template_names[k] = str(self.get("templates", k))
            else:
                logger.warning(f"Template {k} from config.toml is not present in {self.template_dir}")

        if "api_key" in self.conf["stash"]:  # type: ignore
            api_key = self.get("stash", "api_key")
            assert api_key is not None
            stash_headers["apiKey"] = str(api_key)

        self.configure_torrents()

    def configure_torrents(self) -> None:
        self.torrent_clients.clear()
        clients = {"rtorrent": RTorrent, "deluge": Deluge, "qbittorrent": Qbittorrent, "transmission": Transmission}
        for client, clientType in clients.items():
            assert issubclass(clientType, TorrentClient)
            try:
                if client in self.conf and not self.get(client, "disable", False):
                    settings = dict(self.conf[client])  # type: ignore
                    tc = clientType(settings)
                    if tc.connected():
                        logger.debug(f"Connected to {client}")
                        self.torrent_clients.append(tc)
                    else:
                        logger.error(f"Could not connect to {client}")
            except Exception as e:
                logger.error(f"Could not connect to {client}")
                logger.debug(f"Exception: {e}")
                pass
        logger.debug(f"Configured {len(self.torrent_clients)} torrent client(s)")

    def get(self, section: str, key: str, default=None):
        if section in self.conf:
            if key in self.conf[section]:  # type: ignore
                return self.conf[section][key]  # type: ignore
        if section in self.tag_conf and key in self.tag_conf[section]:  # type: ignore
            return self.tag_conf[section][key]  # type: ignore
        return default

    def set(self, section: str, key: str, value) -> None:
        if section not in self.conf:
            if section in self.tag_conf:
                self.tag_conf[section][key] = value  # type: ignore
                return
            self.conf[section] = {}
        self.conf[section][key] = value  # type: ignore
    
    def set_subkey(self, section: str, subsection: str, key: str, value):
        if section not in self.conf:
            self.conf[section] = {}
        if subsection not in self.conf[section]:
            self.conf[section][subsection] = {}
        self.conf[section][subsection][key] = value

    def delete(self, section: str, key: str | None = None) -> None:
        if section in self.conf:
            if key:
                if key in self.conf[section]:  # type: ignore
                    del self.conf[section][key]  # type: ignore
            else:
                del self.conf[section]
        elif section in self.tag_conf:
            if key:
                if key in self.tag_conf[section]:  # type: ignore
                    del self.tag_conf[section][key]  # type: ignore
            else:
                del self.tag_conf[section]

    def delete_subkey(self, section: str, key: str, subkey: str) -> None:
        if section in self.conf:
            if key in self.conf[section] and subkey in self.conf[section][key]:
                del self.conf[section][key][subkey]

    def items(self, section: str) -> dict:
        if section in self.conf:
            return CaseInsensitiveDict(self.conf[section])  # type: ignore
        if section in self.tag_conf:
            return CaseInsensitiveDict(self.tag_conf[section])  # type: ignore
        return {}

    def __iter__(self):
        for section in self.conf:
            yield section

    def __contains__(self, __key: object) -> bool:
        return self.conf.__contains__(__key) or self.tag_conf.__contains__(__key)

    def __getitem__(self, key: str):
        return self.conf.__getitem__(key) if self.conf.__contains__(key) else self.tag_conf.__getitem__(key)

    def migrate(self):
        renamed_settings = {
            "backend.contact_sheet_layout" : "images.contact_sheet_layout",
            "backend.use_preview": "images.use_preview",
            "backend.animated_cover": "images.animated_cover",
        }
        for key in renamed_settings.keys():
            logger.debug(f"Migrating {key} to {renamed_settings[key]}")
            section, setting = key.split(".", 1)
            new_section, new_setting = renamed_settings[key].split(".", 1)
            if section in self.conf and setting in self.conf[section]:
                if new_section not in self.conf:
                    self.conf[new_section] = tomlkit.table()
                self.conf[new_section][new_setting] = self.conf[section][setting]
                self.delete(section, setting)
                logger.warning("Migrated setting {} to {}".format(key, renamed_settings[key]))
        self.update_file()

