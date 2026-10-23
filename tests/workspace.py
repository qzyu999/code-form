"""Temporary test data stays under this checkout, including on Windows."""

import shutil
import os
import stat
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TemporaryWorkspace:
    def __init__(self):
        self.base = (ROOT / ".codeform" / "test-tmp").resolve()
        self.base.mkdir(parents=True, exist_ok=True)
        self.path = self.base / uuid.uuid4().hex
        self.path.mkdir()
        self.name = str(self.path)

    def __enter__(self):
        return self.name

    def cleanup(self):
        target = self.path.resolve()
        if not target.is_relative_to(self.base) or target == self.base:
            raise ValueError("Refusing to clean outside the test workspace.")
        def remove_read_only(function, path, error):
            checked = Path(path).resolve()
            if not checked.is_relative_to(target):
                raise ValueError("Refusing to alter permissions outside test data.")
            os.chmod(checked, stat.S_IWRITE | stat.S_IREAD)
            function(path)

        shutil.rmtree(target, onerror=remove_read_only)

    def __exit__(self, *args):
        self.cleanup()
