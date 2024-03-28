
from attrs import define

from typing import List, Union, Optional, Generator, cast
from zipfile import ZipFile, Path
import hashlib
import os


BUF_SIZE = 65536 # 64 kB

@define
class FileBase:
    parent: Optional['DirectoryBase']
    name: str

    def __init__(self): raise Exception("Abstract class instantiated")

    def __len__(self): ...

    def _read(self, buffer_size: int): ... # abstract function

    def read(self) -> bytes:
        return b''.join(self._read(BUF_SIZE))

    def read_large(self, buffer_size: int = 0) -> Generator[bytes, None, None]:
        if buffer_size <= 0:
            buffer_size = BUF_SIZE
        while data := self._read(buffer_size):
            yield data

    def write(self, content: bytes): ...

    def rename(self, new_name: str): ...

    def watch(self): ...

    def hash(self) -> str:
        md5 = hashlib.md5(usedforsecurity=False)
        for chunk in self.read_large():
            md5.update(chunk)
        return md5.hexdigest()

    @property
    def full_path(self) -> str:
        if self.parent is not None:
            return os.path.join(self.parent.full_path, self.name)
        else:
            return self.name

@define
class DirectoryBase:
    parent: Optional['DirectoryBase']
    name: str

    def __init__(self): raise Exception("Abstract class instantiated")

    def list(self): ...
    def get(self, item: str): ...
    def has(self, item: str): ...

    def __getitem__(self, key: str) -> Union[FileBase, 'DirectoryBase']:
        return self.get(key)

    @property
    def full_path(self) -> str:
        if self.parent is not None:
            return os.path.join(self.parent.full_path, self.name)
        else:
            return self.name

@define
class FileReal(FileBase):
    def __len__(self) -> int:
        return os.path.getsize(self.full_path)

    def _read(self, buffer_size: int):
        self.parent = cast(DirectoryBase, self.parent)
        if self.parent.has(self.name) or not os.path.isfile(self.full_path):
            with open(self.full_path, 'rb') as file:
                while True:
                    data = file.read(buffer_size)
                    if not data:
                        break
                    yield data
        else:
            raise FileNotFoundError(f"Could not find {self.name} in {self.parent.full_path} as {self.full_path}")

@define
class DirectoryReal(DirectoryBase):
    def list(self) -> List[Union[FileBase, 'DirectoryBase']]:
        children: List[Union[FileBase, 'DirectoryBase']] = []

        for item in os.listdir(self.full_path):
            if os.path.isfile(os.path.join(self.full_path, item)):
                children.append(FileReal(self, item))
            elif os.path.isdir(os.path.join(self.full_path, item)):
                children.append(DirectoryReal(self, os.path.join(self.full_path, item)))

        return children

    def get(self, item: str) -> Union[FileBase, 'DirectoryBase']:
        return FileReal(self, item)

    def has(self, item: str) -> bool:
        return os.path.exists(os.path.join(self.full_path, item))

@define
class DirectoryZip(DirectoryBase):
    _zip: Optional[ZipFile]

    def list(self) -> List[Union[FileBase, 'DirectoryBase']]:
        children: List[Union[FileBase, 'DirectoryBase']] = []

        self._zip = cast(ZipFile, self._zip)
        for item in self._zip.infolist():
            if not item.is_dir():
                children.append(FileZip(item.filename, self))

        return children

    def get(self, item: str) -> Union[FileBase, DirectoryBase]:
        self._zip = cast(ZipFile, self._zip)
        result = Path(self._zip, item)
        if result.is_dir():
            return DirectoryZip(self, item, self._zip)
        else:
            return FileZip(parent=self, name=item)

    def has(self, item: str) -> bool:
        self._zip = cast(ZipFile, self._zip)
        path = Path(self._zip, item)
        return path.is_file() or path.is_dir()

@define
class FileZip(FileBase):
    parent: DirectoryZip

    def __len__(self) -> int:
        return cast(ZipFile, self.parent._zip).getinfo(self.name).file_size

    def _read(self, buffer_size: int) -> Generator[bytes, None, None]:
        zip_file = cast(ZipFile, self.parent._zip)
        with zip_file.open(self.name, 'r') as file:  # open a file inside the zip
            while chunk := file.read(buffer_size):
                yield chunk
    
    def write(self, content: bytes) -> None: ...

