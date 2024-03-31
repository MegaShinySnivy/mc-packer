
from attrs import define

from typing import List, Union, Optional, Generator, cast
from zipfile import ZipFile, Path
from abc import ABC, abstractmethod
import hashlib
import os


BUF_SIZE = 65536  # 64 kB


@define
class FileBase(ABC):
    parent: Optional['DirectoryBase']
    name: str

    @abstractmethod
    def __len__(self) -> int:
        ...

    @abstractmethod
    def _read(self, buffer_size: int) -> Generator[bytes, None, None]:
        ...

    @abstractmethod
    def write(self, content: bytes) -> None:
        ...

    @abstractmethod
    def rename(self, new_name: str) -> None:
        ...

    # @abstractmethod
    # def watch(self): ...

    @property
    def full_path(self) -> str:
        if self.parent is not None:
            return os.path.join(self.parent.full_path, self.name)
        else:
            return self.name

    def read(self) -> bytes:
        return b''.join(self._read(BUF_SIZE))

    def read_large(self, buffer_size: int = 0) -> Generator[bytes, None, None]:
        if buffer_size <= 0:
            buffer_size = BUF_SIZE
        while data := self._read(buffer_size):
            yield cast(bytes, data)

    def hash(self) -> str:
        md5 = hashlib.md5(usedforsecurity=False)
        for chunk in self.read_large():
            md5.update(chunk)
        return md5.hexdigest()


@define
class DirectoryBase(ABC):
    parent: Optional['DirectoryBase']
    name: str

    @abstractmethod
    def list(self) -> List[Union[FileBase, 'DirectoryBase']]:
        ...

    @abstractmethod
    def get(self, item: str) -> Union[FileBase, 'DirectoryBase']:
        ...

    @abstractmethod
    def has(self, item: str) -> bool:
        ...

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
        if self.parent.has(self.name) or os.path.isfile(self.full_path):
            with open(self.full_path, 'rb') as file:
                while True:
                    data = file.read(buffer_size)
                    if not data:
                        break
                    yield data
        else:
            raise FileNotFoundError(
                f"Could not find {self.name} in {self.parent.full_path} "
                f"as {self.full_path}"
            )

    def rename(self, new_name: str) -> None:
        parent_dir = cast(DirectoryBase, self.parent).full_path
        new_path = os.path.join(parent_dir, new_name)
        os.rename(self.full_path, new_path)
        self.name = new_name

    def write(self, content: bytes) -> None:
        self.parent = cast(DirectoryBase, self.parent)
        if self.parent.has(self.name) or os.path.isfile(self.full_path):
            with open(self.full_path, 'wb') as file:
                file.write(content)


@define
class DirectoryReal(DirectoryBase):
    def list(self) -> List[Union[FileBase, 'DirectoryBase']]:
        children: List[Union[FileBase, 'DirectoryBase']] = []

        for item in os.listdir(self.full_path):
            if os.path.isfile(os.path.join(self.full_path, item)):
                children.append(FileReal(self, item))
            elif os.path.isdir(os.path.join(self.full_path, item)):
                item_path = os.path.join(self.full_path, item)
                children.append(DirectoryReal(self, item_path))

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
        with zip_file.open(self.name, 'r') as file:
            while chunk := file.read(buffer_size):
                yield chunk

    def write(self, content: bytes) -> None:
        zip_file = cast(ZipFile, self.parent._zip)
        with zip_file.open(self.name, 'wb') as file:
            file.write(content)

    def rename(self, new_name: str) -> None:
        raise AttributeError("renaming is not supported for FileZip")
