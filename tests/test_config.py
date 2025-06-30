import unittest

from pydantic import ValidationError

from utils.models import Config
from tomlkit import parse


class MyTestCase(unittest.TestCase):
    def test_default_config(self):
        with open('default.toml', 'rb') as f:
            config = parse(f.read())
            conf = Config.model_validate(config)


if __name__ == '__main__':
    unittest.main()
