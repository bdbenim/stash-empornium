import os
import shutil
import tempfile
from typing import Any
from zipfile import ZipFile

from utils.confighandler import ConfigHandler
from utils.paths import mapPath

conf = ConfigHandler()
filetypes = tuple(s if s.startswith(".") else "." + s for s in
                  conf.get("backend", "image_formats", ["jpg", "jpeg", "png"]))  # type: ignore


def prep_dir(directory: str):
    if not os.path.exists(directory):
        os.makedirs(directory)
    elif not os.path.isdir(directory):
        raise ValueError(f"Cannot save files to {directory}: destination is not a directory!")


def link(source: str, dest: str):
    """
    Create a link in the dest directory pointing to source.
    """
    prep_dir(dest)
    basename = os.path.basename(source)
    method = conf.get("backend", "move_method")
    try:
        match method:
            case "hardlink":
                os.link(source, os.path.join(dest, basename))
            case "symlink":
                os.symlink(source, os.path.join(dest, basename))
            case "copy":
                shutil.copy(source, dest)
            case _:
                raise ValueError("move_method must be one of 'hardlink', 'symlink', or 'copy'")
    except FileExistsError:
        pass


def unzip(source: str, dest: str) -> list[str]:
    """
    Extracts all image files from `source` and places them in `dest`
    :param source: The file to unzip
    :param dest: The destination directory for unzipped files
    :return: A list containing the paths of all extracted files
    """
    prep_dir(dest)
    with ZipFile(source) as z:
        files = z.namelist()
        if ".*" not in filetypes:
            files = [file for file in files if file.endswith(filetypes)]
        z.extractall(dest, files)
        return [os.path.join(dest, file) for file in files]


def zip_files(files: list[str], dest: str, name: str):
    if not name.endswith(".zip"):
        name = name + ".zip"
    prep_dir(dest)
    with ZipFile(os.path.join(dest, name), "w") as z:
        for file in files:
            basename = os.path.basename(file)
            z.write(file, basename)


def get_torrent_directory(scene: dict[str, Any] = None, title: str = None) -> str | None:
    """
    Returns a directory name for a given Stash scene.
    :param title:
    :param scene:
    :raises: ValueError if media_directory not specified in config
    :return: The path for the torrent contents
    """
    if scene is None and title is None:
        raise ValueError("a title or scene must be provided")
    parent: str = conf.get("backend", "media_directory")  # type: ignore
    if not parent:
        raise ValueError("media_directory not specified in config")
    if title:
        directory = title
    elif scene and scene["title"]:
        directory = scene["title"]
    elif scene:
        directory = ".".join(scene["files"][0]["basename"].split(".")[:-1])
    else:
        raise ValueError("unable to create directory for torrent")
    return os.path.join(parent, directory)


def read_gallery(scene: dict[str, Any]) -> tuple[str, str, bool] | None:
    """
    Find gallery associated with a scene. If one is present, copy
    (by hard or soft link) its files to the media_directory specified
    in config.toml.

    Additionally, if the gallery is a zip file, extract the images to a
    temporary directory to allow a contact sheet to be generated later.

    Returns a tuple containing the directory for torrent creation, the
    directory where image files are located, and a boolean indicating
    whether the image files are in a temporary directory (requiring cleanup)
    """
    if len(scene["galleries"]) < 1:
        return
    dirname = get_torrent_directory(scene)
    image_dir = os.path.join(dirname, "Gallery")
    temp = False
    gallery = scene["galleries"][0]
    if gallery["folder"]:
        source_dir = mapPath(gallery["folder"]["path"], conf.items("file.maps"))
        os.makedirs(image_dir, exist_ok=True)
        for file in os.listdir(source_dir):
            link(os.path.join(source_dir, file), image_dir)
    elif gallery["files"]:
        temp = True
        zip_file = mapPath(gallery["files"][0]["path"], conf.items("file.maps"))
        source_dir = tempfile.mkdtemp()
        files = unzip(zip_file, source_dir)
        for file in files:
            os.chmod(file, 0o666)  # Ensures torrent client can read the file
            shutil.copy(file, image_dir)
    else:
        return
    return dirname, source_dir, temp
