"""Hotel booking application package."""

import contextlib
import os
import sys

# On Windows, ensure PostgreSQL bin directory is in DLL search path
if sys.platform == "win32":
    for path in [
        r"C:\Program Files\PostgreSQL\18\bin",
        r"C:\Program Files\PostgreSQL\17\bin",
        r"C:\Program Files\PostgreSQL\16\bin",
    ]:
        if os.path.exists(path):
            with contextlib.suppress(OSError, AttributeError):
                os.add_dll_directory(path)
