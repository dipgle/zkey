from dataclasses import asdict, dataclass
from pathlib import Path
import os
import tempfile
import tomllib


@dataclass(frozen=True)
class Config:
    enabled: bool = True
    modern_tone: bool = True
    max_word_keys: int = 256

    def __post_init__(self):
        if type(self.enabled) is not bool or type(self.modern_tone) is not bool:
            raise ValueError("enabled and modern_tone must be boolean")
        if type(self.max_word_keys) is not int or not 8 <= self.max_word_keys <= 256:
            raise ValueError("max_word_keys must be between 8 and 256")


def config_path():
    if explicit := os.environ.get("ZKEY_CONFIG_PATH"):
        return Path(explicit)
    return Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "zkey/config.toml"


def load(path=None):
    path = Path(path) if path is not None else config_path()
    try:
        with path.open("rb") as stream:
            data = tomllib.load(stream)
    except FileNotFoundError:
        return Config()
    if set(data) - set(asdict(Config())):
        raise ValueError("Unknown zkey configuration keys")
    return Config(**data)


def save(config, path=None):
    path = Path(path) if path is not None else config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = "".join(f"{key} = {str(value).lower()}\n" for key, value in asdict(config).items())
    fd, temporary = tempfile.mkstemp(prefix=".zkey-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
