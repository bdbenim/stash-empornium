from venv import logger
import tomlkit
import configupdater
import argparse
import os
import logging
import shutil
from utils.torrent import torrentclient, deluge, qbittorrent

__version__ = "0.11.0"


class ConfigHandler:
    logger: logging.Logger
    log_level: int
    args: argparse.Namespace
    conf: tomlkit.TOMLDocument
    default_template: str
    anon: bool
    port: int
    host: str | None
    rport: int
    ssl: bool
    username: str
    password: str
    torrent_dirs: list[str]
    date_format: str
    stash_url: str
    template_dir: str
    tag_codec: bool
    tag_date: bool
    tag_framerate: bool
    tag_resolution: bool
    title_template: str
    template_names: dict[str, str]
    config_file: str
    torrent_clients: list[torrentclient.TorrentClient] = []

    stash_headers = {
        "Content-type": "application/json",
    }

    stash_query = """
    findScene(id: "{}") {{
    title details director date studio {{ name url image_path parent_studio {{ url }} }} tags {{ name parents {{ name }} }} performers {{ name image_path tags {{ name }} }} paths {{ screenshot preview webp}}
    files {{ id path basename width height format duration video_codec audio_codec frame_rate bit_rate size }}
    }}
    """

    def __init__(self) -> None:
        self.parse_args()
        self.log_level = getattr(logging, self.args.log) if self.args.log else min(10 * self.args.level, 50)

    def logging_init(self) -> None:
        self.logger = logging.getLogger(__name__)

    def parse_args(self) -> None:
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
        parser.add_argument("--anon", action="store_true", help="upload anonymously")
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
        redisgroup.add_argument("--rhost", "--redis--host", "--rh", help="host redis server is listening on")
        redisgroup.add_argument(
            "--rport", "--redis-port", "--rp", help="port redis server is listening on (default: 6379)", type=int
        )
        redisgroup.add_argument("--username", "--redis-user", help="redis username")
        redisgroup.add_argument("--password", "--redis-pass", help="redis password")
        redisgroup.add_argument("--use-ssl", "-s", action="store_true", help="use SSL to connect to redis")
        redisgroup.add_argument("--flush", help="flush redis cache", action="store_true")
        cache = redisgroup.add_mutually_exclusive_group()
        cache.add_argument("--no-cache", help="do not retrieve cached values", action="store_true")  # TODO implement
        cache.add_argument("--overwrite", help="overwrite cached values", action="store_true")  # TODO implement

        self.args = parser.parse_args()

    def renameKey(self, section: str, oldkey: str, newkey: str) -> None:
        if oldkey in self.conf[section]:  # type: ignore
            self.conf[section][newkey] = self.conf[section][oldkey]  # type: ignore
            del self.conf[section][oldkey]  # type: ignore
            self.update_file()
            self.logger.info(f"Key '{oldkey}' renamed to '{newkey}'")

    def update_file(self) -> None:
        with open(self.config_file, "w") as f:
            tomlkit.dump(self.conf, f)

    def configure(self) -> None:
        config_dir = self.args.configdir[0]

        self.template_dir = os.path.join(config_dir, "templates")
        self.config_file = os.path.join(config_dir, "config.toml")

        # Ensure config file is present
        if not os.path.isfile(self.config_file):
            self.logger.info(f"Config file not found at {self.config_file}, creating")
            if not os.path.exists(config_dir):
                os.makedirs(config_dir)
            oldconf_file = os.path.join(config_dir, "config.ini")
            if os.path.isfile(oldconf_file):
                # TODO convert ini to toml
                self.logger.info("Translating config from ini")
                oldconf = configupdater.ConfigUpdater()
                oldconf.read(oldconf_file)

                self.conf = tomlkit.document()
                for section in oldconf.sections():
                    table = tomlkit.table(True)
                    for item in oldconf[section].iter_blocks():
                        match type(item):
                            case configupdater.Comment:
                                tomlitem = tomlkit.comment(str(item))
                                table.add(tomlitem)
                            case configupdater.Option:
                                value = str(item.value)  # type: ignore
                                if section in ["empornium", "demonyms"] or (section == "backend" and item.key == "torrent_directories"):  # type: ignore
                                    value = [x.strip() for x in value.split(",")]  # type: ignore
                                elif value.lower() == "true":
                                    value = True
                                elif value.lower() == "false":
                                    value = False
                                elif str.isdigit(value):
                                    value = int(value)
                                table.append(item.key, value)  # type: ignore
                    self.conf.append(section, table)
                self.update_file()
            else:
                shutil.copyfile("default.toml", self.config_file)

        # Ensure config file properly ends with a '\n' character
        fstr = ""
        with open(self.config_file, "r") as f:
            fstr = f.read()
        if fstr[-1] != "\n":
            with open(self.config_file, "w") as f:
                f.write(fstr + "\n")
        del fstr

        self.logger.info(f"Reading config from {self.config_file}")
        try:
            with open(self.config_file) as f:
                self.conf = tomlkit.load(f)
        except Exception as e:
            logger.critical(f"Failed to read config file: {e}")
            exit(1)
        self.renameKey("backend", "torrent_directory", "torrent_directories")
        with open("default.toml") as f:
            default_conf = tomlkit.load(f)
        skip_sections = ["empornium", "empornium.tags"]
        for section in default_conf:
            if section not in self.conf:
                s = tomlkit.table(True)
                s.add(tomlkit.comment("Section added from default.toml"))
                self.conf.append(section, s)
            if section not in skip_sections:
                for option in default_conf[section]:  # type: ignore
                    if option not in self.conf[section]:
                        self.conf[section].add(tomlkit.comment("Option imported automatically:"))  # type: ignore
                        value = default_conf[section][option]  # type: ignore
                        self.conf[section][option] = value  # type: ignore
                        self.logger.info(
                            f"Automatically added option '{option}' to section [{section}] with value '{value}'"
                        )
        try:
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
                    if filename not in conf["templates"]:  # type: ignore
                        with open("default.toml") as f:
                            tmpConf = tomlkit.load(f)
                        conf["templates"][filename] = tmpConf["templates"][filename]  # type: ignore

        # TODO: better handling of unexpected values
        anon = self.conf["backend"]["anon"]  # type: ignore
        if anon is not None:
            assert isinstance(anon, bool)
        self.anon: bool = self.args.anon or anon
        self.logger.debug(f"Anonymous uploading: {self.anon}")
        self.stash_url = self.conf["stash"]["url"]  # type: ignore
        if self.stash_url is None:
            self.stash_url = "http://localhost:9999"
        self.port = self.args.port[0] if self.args.port else self.conf["backend"]["port"]  # type: ignore
        if not isinstance(self.port, int):
            self.port = 9932
        self.default_template = self.conf["backend"]["default_template"]  # type: ignore
        if self.default_template is None:
            self.default_template = "fakestash-v2"
        # TODO check that template exists
        self.torrent_dirs = (
            [self.args.torrentdir[0]]
            if self.args.torrentdir
            else list(self.conf["backend"]["torrent_directories"])  # type: ignore
        )
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
        self.title_template = str(
            self.get(
                "backend",
                "title_template",
                "{% if studio %}[{{studio}}]{% endif %} {{performers|join(', ')}} - {{title}} {% if date %}({{date}}){% endif %}[{{resolution}}]",
            )
        )
        self.date_format = self.get("backend", "date_format", "%B %-d, %Y")  # type: ignore
        self.tag_codec = self.args.c or self.get("metadata", "tag_codec", False)  # type: ignore
        self.tag_date = self.args.d or self.get("metadata", "tag_date", False)  # type: ignore
        self.tag_framerate = self.args.f or self.get("metadata", "tag_framerate", False)  # type: ignore
        self.tag_resolution = self.args.r or self.get("metadata", "tag_resolution", False)  # type: ignore

        self.template_names = {}
        template_files = os.listdir(self.template_dir)
        for k in self.items("templates"):
            if k in template_files:
                self.template_names[k] = str(self.get("templates", k))
            else:
                self.logger.warning(f"Template {k} from config.ini is not present in {self.template_dir}")

        if "api_key" in self.conf["stash"]:  # type: ignore
            api_key = self.get("stash", "api_key")
            assert api_key is not None
            self.stash_headers["apiKey"] = str(api_key)

        self.host = self.args.rhost if self.args.rhost else str(self.get("redis", "host"))
        self.host = self.host if len(self.host) > 0 else None
        self.rport = self.args.rport if self.args.rport else self.get("redis", "port", 6379)  # type: ignore
        self.ssl = self.args.use_ssl or self.get("redis", "ssl", False)  # type: ignore
        self.username = self.args.username if self.args.username else self.get("redis", "username", "")  # type: ignore
        self.password = self.args.password if self.args.password else self.get("redis", "password", "")  # type: ignore
        self.configureTorrents()

    def configureTorrents(self) -> None:
        # rtorrent:
        clients = {"rtorrent": torrentclient.RTorrent, "deluge": deluge.Deluge, "qbittorrent": qbittorrent.Qbittorrent}
        for client in clients:
            try:
                if client in self.conf:
                    settings = dict(self.conf[client])  # type: ignore
                    clientType = clients[client]
                    self.torrent_clients.append(clientType(settings))
            except:
                pass
        self.logger.debug(f"Configured {len(self.torrent_clients)} torrent client(s)")

    def get(self, section: str, key: str, default=None):
        if section in self.conf:
            if key in self.conf[section]:  # type: ignore
                return self.conf[section][key]  # type: ignore
        return default

    def set(self, section: str, key: str, value) -> None:
        if section not in self.conf:
            self.conf[section] = {}
        self.conf[section][key] = value  # type: ignore

    # def append(self, section: str, key: str, value) -> None:
    #     if section not in self.conf:
    #         self.conf[section] = {}
    #     if key in self.conf[section]: # type: ignore
    #         self.conf[section][key].append(value) # type: ignore
    #     else:
    #         self.conf[section][key] = [value] # type: ignore
    #     self.update_file()

    def items(self, section: str) -> dict:
        if section in self.conf:
            return dict(self.conf[section])  # type: ignore
        return {}
