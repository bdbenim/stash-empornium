import os, shutil, tempfile
from zipfile import ZipFile

from utils.confighandler import ConfigHandler
from utils.paths import mapPath

conf = ConfigHandler()
filetypes = tuple(s if s.startswith('.') else '.'+s for s in conf.get("backend", "image_formats", ["jpg", "jpeg", "png"]))

def prepDir(dir: str):
    if not os.path.exists(dir):
        os.makedirs(dir)
    elif not os.path.isdir(dir):
        raise ValueError(f"Cannot save files to {dir}: destination is not a directory!")


def link(source: str, dest: str):
    """
    Create a link in the dest directory pointing to source.
    """
    prepDir(dest)
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

def unzip(source: str, dest: str):
    prepDir(dest)
    with ZipFile(source) as z:
        files = z.namelist()
        if '.*' not in filetypes:
            files = [file for file in files if file.endswith(filetypes)]
        z.extractall(dest, files)

def zip(files: list[str], dest: str, name: str):
    if not name.endswith('.zip'):
        name = name + '.zip'
    prepDir(dest)
    with ZipFile(os.path.join(dest, name), 'w') as z:
        for file in files:
            basename = os.path.basename(file)
            z.write(file, basename)

def readGallery(scene: dict) -> tuple[str, str, bool] | None:
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
    if len(scene['galleries']) < 1:
        return
    dirname = conf.get("backend", "media_directory")
    if not dirname:
        raise ValueError("media_directory not specified in config")
    if scene['title']:
        dirname = os.path.join(dirname, scene['title'])
    else:
        title = '.'.join(scene['files'][0]['basename'].split('.')[:-1])
        dirname = os.path.join(dirname, title)
    temp = False
    gallery = scene['galleries'][0]
    if gallery['folder']:
        source_dir = mapPath(gallery['folder']['path'], conf.items("file.maps"))
        image_dir = os.path.join(dirname, 'Images')
        os.makedirs(image_dir, exist_ok=True)
        for file in os.listdir(source_dir):
            link(os.path.join(source_dir, file), image_dir)
    elif gallery['files']:
        temp = True
        zip = mapPath(gallery['files'][0]['path'], conf.items("file.maps"))
        source_dir = tempfile.mkdtemp()
        unzip(zip, source_dir)
        link(zip, dirname)
    else:
        return
    return dirname, source_dir, temp