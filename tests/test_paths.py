import unittest
from pathlib import PureWindowsPath

from utils import paths

path_maps = {
    "/data/media": "/mnt/share/data/media",         # POSIX->POSIX
    "/data/videos/": "/mnt/share/data/media",       # Trailing slash
    "Z:\\data\\media": "/mnt/share/data/media",     # Windows->POSIX
    "/data/Windows/media": "Z:\\data\\media",       # POSIX->Windows
    "X:\\data\\Windows\\media": "Y:\\data\\media",  # Windows->Windows
}

class MyTestCase(unittest.TestCase):
    def test_posix_mapping(self):
        remote = "/data/media/scene.mp4"
        expected = "/mnt/share/data/media/scene.mp4"
        result = paths.remap_path(remote, path_maps)
        self.assertEqual(expected, result)

    def test_trailing_slash(self):
        remote = "/data/videos/scene.mp4"
        expected = "/mnt/share/data/media/scene.mp4"
        result = paths.remap_path(remote, path_maps)
        self.assertEqual(expected, result)

    def test_posix_nested_mapping(self):
        remote = "/data/media/some/directories/scene.mp4"
        expected = "/mnt/share/data/media/some/directories/scene.mp4"
        result = paths.remap_path(remote, path_maps)
        self.assertEqual(expected, result)

    def test_windows_posix_mapping(self):
        remote = "Z:\\data\\media\\scene.mp4"
        expected = "/mnt/share/data/media/scene.mp4"
        result = paths.remap_path(remote, path_maps)
        self.assertEqual(expected, result)

    def test_windows_posix_nested_mapping(self):
        remote = "Z:\\data\\media\\some\\directories\\scene.mp4"
        expected = "/mnt/share/data/media/some/directories/scene.mp4"
        result = paths.remap_path(remote, path_maps)
        self.assertEqual(expected, result)

    def test_posix_windows_mapping(self):
        remote = "/data/Windows/media/scene.mp4"
        expected = str(paths.normalize_path("Z:\\data\\media\\scene.mp4")) # Required for test to pass on linux
        result = paths.remap_path(remote, path_maps)
        self.assertEqual(expected, result)

    def test_windows_mapping(self):
        remote = "X:\\data\\Windows\\media\\scene.mp4"
        expected = str(paths.normalize_path("Y:\\data\\media\\scene.mp4")) # Required for test to pass on linux
        result = paths.remap_path(remote, path_maps)
        self.assertEqual(expected, result)



if __name__ == '__main__':
    unittest.main()