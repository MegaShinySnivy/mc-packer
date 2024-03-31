
# from typing import

from filesystem import FileReal, DirectoryBase


class Log(FileReal):
    def identifyError(self, error: str) -> bool:
        return False
