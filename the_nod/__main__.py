"""Entry for `python -m the_nod` and `python -P <root>/the_nod/__main__.py`."""
import sys
from pathlib import Path

if not __package__:  # run as a file: the package is found from the parent folder, no PYTHONPATH needed
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from the_nod.cli import main  # noqa: E402

raise SystemExit(main())
