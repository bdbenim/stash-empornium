import re
from typing import Optional, Literal, Annotated, TypeAlias

from pydantic import BaseModel, Field, model_validator, BeforeValidator, AfterValidator

def not_empty(s: str) -> str:
    if s.strip() == "":
        raise ValueError("String must not be empty")
    return s

def validate_layout_str(s: str) -> str:
    s = s.strip()
    if re.match("^[1-9]+x[1-9]+$", s):
        return s
    raise ValueError(f"{s} is not a valid layout")

PortNumber = Annotated[int, Field(ge=0), Field(le=65535)]
LogLevel: TypeAlias = Annotated[Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], BeforeValidator(lambda x: x.upper())]
MoveMethod: TypeAlias = Annotated[Literal["copy", "hardlink", "symlink"], BeforeValidator(lambda x: x.lower())]
ApiKey = Annotated[str, AfterValidator(not_empty)]

class BackendConfig(BaseModel):
    default_template: str
    torrent_directories: list[str]
    port: PortNumber = 9932
    title_template: str
    date_format: str = "%Y-%m-%d"
    anon: bool = False
    media_directory: Optional[str] = None
    move_method: MoveMethod = "copy"
    use_preview: bool = False
    animated_cover: bool = True
    log_level: LogLevel = "INFO"
    contact_sheet_layout: Annotated[str, AfterValidator(validate_layout_str)] = "3x6"
    save_images: Optional[str] = None

class HamsterConfig(BaseModel):
    api_key: ApiKey

# Base config options for all torrent clients
class TorrentConfig(BaseModel):
    host: str = "localhost"
    port: PortNumber = 8080
    ssl: bool = False
    password: Optional[str] = None
    label: Optional[str] = None
    pathmaps: Optional[dict[str, str]] = None

class RTorrentConfig(TorrentConfig):
    path: str = "RPC2"
    username: Optional[str] = None
    password: Optional[str] = None


class DelugeConfig(TorrentConfig):
    port: PortNumber = 8112

class QBittorrentConfig(TorrentConfig):
    pass

class TransmissionConfig(TorrentConfig):
    path: str = "/transmission/rpc"
    username: Optional[str] = None
    password: Optional[str] = None

class RedisConfig(BaseModel):
    host: str = "localhost"
    port: PortNumber = 6379
    username: Optional[str] = None
    password: Optional[str] = None
    ssl: bool = False

class MetadataConfig(BaseModel):
    tag_codec: bool = False
    tag_date: bool = False
    tag_framerate: bool = False
    tag_resolution: bool = False

class PerformersConfig(BaseModel):
    tag_ethnicity: bool = False
    tag_hair_color: bool = False
    tag_eye_color: bool = False
    cup_sizes: Optional[dict[str,str]] = None

class StashConfig(BaseModel):
    url: str
    api_key: Optional[ApiKey] = None

class Config(BaseModel):
    backend: BackendConfig
    hamster: Optional[HamsterConfig] = None
    rtorrent: Optional[RTorrentConfig] = None
    deluge: Optional[DelugeConfig] = None
    transmission: Optional[TransmissionConfig] = None
    redis: Optional[RedisConfig] = None
    metadata: MetadataConfig
    performers: PerformersConfig
    templates: dict[str, str]
    stash: StashConfig

    @model_validator(mode="after")
    def validate_template_in_list(self):
        if self.backend.default_template not in self.templates:
            raise ValueError(f"Invalid template: {self.backend.default_template} not in list of templates")
        return self