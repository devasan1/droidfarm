"""Allow ``python -m droidfarm`` to boot the backend.

The Tauri desktop shell (``src-tauri/src/main.rs``) spawns the backend with
``python -m droidfarm``; without this shim, Python errors out with
``No module named droidfarm.__main__``.
"""

from droidfarm.main import main

if __name__ == "__main__":
    main()
