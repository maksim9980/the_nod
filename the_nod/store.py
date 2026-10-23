"""State storage: model objects in the files of the `.nod/` folder."""

import re
import secrets
import shutil
import string
import tomllib
from pathlib import Path

from the_nod import frontmatter
from the_nod.files import slugify, write_text_atomic
from the_nod.frontmatter import FrontmatterError
from the_nod.i18n import t
from the_nod.model import Acceptance, Card, Decision, ModelError, Review, Run, Spend

__all__ = ["Store", "LoadError", "slugify", "write_text_atomic"]

_ID_ALPHABET = string.digits + string.ascii_lowercase
_ID_LENGTH = 4
_ORDERED_STATUSES = ("backlog", "briefing", "waiting-owner", "ready")
_ID_FOLDERS = ("cards", "decisions", "runs")
# The same text in every language: two machines with different `lang` do not rewrite each other's heading.
# Readers skip every `#` line, so the Russian heading of older states still reads.
ORDER_TITLE = "# Backlog order"
FRAME_MAX_BYTES = 300 * 1024
FRAME_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp")
ID_RE = re.compile(r"[a-z]-[0-9a-z]{4,}")
WEEK_RE = re.compile(r"\d{4}-\d{2}")


def _check_id(id: str) -> str:
    if not isinstance(id, str) or not ID_RE.fullmatch(id):
        raise ValueError(t("store.bad_id", id=id))
    return id


def _check_week(week: str) -> str:
    if not isinstance(week, str) or not WEEK_RE.fullmatch(week):
        raise ValueError(t("store.bad_week", week=week))
    return week


class LoadError(ValueError):
    """A state file does not read: `path` is the file, `line` the line of the error when known."""

    def __init__(self, message: str, path: Path, line: int | None = None):
        super().__init__(f"{path}: {message}")
        self.path = path
        self.line = line


class Store:
    """State files in the folder `root` (that is `.nod/` itself)."""

    def __init__(self, root: Path):
        self.root = Path(root)
        for name in (*_ID_FOLDERS, "acceptance"):
            (self.root / name).mkdir(parents=True, exist_ok=True)

    # --- the shared path for cards, decisions and runs ---

    def _matches(self, folder: str, id: str) -> list[Path]:
        # The dash after the id is required: "c-7k3q" does not match "c-7k3qz-...".
        base = self.root / folder
        found = [base / f"{id}.md"] if (base / f"{id}.md").exists() else []
        return found + sorted(base.glob(f"{id}-*.md"))

    def _find(self, folder: str, id: str) -> Path | None:
        found = self._matches(folder, _check_id(id))
        if len(found) > 1:
            raise LoadError(t("store.duplicate_id", id=id, first=found[0], second=found[1]), found[1])
        return found[0] if found else None

    def _save(self, folder: str, obj, label: str = "") -> Path:
        _check_id(obj.id)
        slug = slugify(label)
        path = self.root / folder / (f"{obj.id}-{slug}.md" if slug else f"{obj.id}.md")
        write_text_atomic(path, frontmatter.dump(obj.to_meta(), obj.body))
        # The title changed: the other files with the same id are removed.
        for old in self._matches(folder, obj.id):
            if old != path:
                old.unlink()
        return path

    def _read(self, path: Path, cls):
        try:
            meta, body = frontmatter.parse(path.read_text(encoding="utf-8-sig"))
            return cls.from_meta(meta, body)
        except FrontmatterError as error:
            raise LoadError(str(error), path, error.line) from error
        except ModelError as error:
            raise LoadError(str(error), path) from error

    def _load(self, folder: str, id: str, cls):
        path = self._find(folder, id)
        if path is None:
            raise FileNotFoundError(t("store.not_found", id=id, folder=folder))
        return self._read(path, cls)

    def _all(self, folder: str, cls) -> list:
        by_id: dict[str, tuple[Path, object]] = {}
        for path in sorted((self.root / folder).glob("*.md")):
            item = self._read(path, cls)
            if item.id in by_id:
                first = by_id[item.id][0]
                raise LoadError(t("store.duplicate_id", id=item.id, first=first, second=path), path)
            by_id[item.id] = (path, item)
        return sorted((item for _, item in by_id.values()), key=lambda item: item.id)

    def _folder(self, folder: str, cls) -> list:
        """All `<folder>/*.md` by file name, with no dedup by id. No folder gives `[]`; it is not created."""
        return [self._read(path, cls) for path in sorted((self.root / folder).glob("*.md"))]

    # --- ids ---

    def new_id(self, prefix: str) -> str:
        """A free id such as `c-7k3q`."""
        while True:
            suffix = "".join(secrets.choice(_ID_ALPHABET) for _ in range(_ID_LENGTH))
            candidate = f"{prefix}-{suffix}"
            if not any(self._find(folder, candidate) for folder in _ID_FOLDERS):
                return candidate

    # --- cards, decisions, runs, acceptance ---

    def save_card(self, card: Card) -> Path:
        return self._save("cards", card, card.title)

    def load_card(self, id: str) -> Card:
        return self._load("cards", id, Card)

    def cards(self) -> list[Card]:
        return self._all("cards", Card)

    def save_decision(self, decision: Decision) -> Path:
        return self._save("decisions", decision, decision.question)

    def load_decision(self, id: str) -> Decision:
        return self._load("decisions", id, Decision)

    def decisions(self) -> list[Decision]:
        return self._all("decisions", Decision)

    def save_run(self, run: Run) -> Path:
        return self._save("runs", run)

    def load_run(self, id: str) -> Run:
        return self._load("runs", id, Run)

    def runs(self) -> list[Run]:
        return self._all("runs", Run)

    def save_spend(self, spend: Spend) -> Path:
        name = f"{spend.at.replace(':', '-')}-{spend.kind}-{_check_id(spend.card)}.md"
        path = self.root / "usage" / name
        write_text_atomic(path, frontmatter.dump(spend.to_meta(), spend.body))
        return path

    def spends(self) -> list[Spend]:
        return self._folder("usage", Spend)

    def save_review(self, review: Review) -> Path:
        """Writes the review to `reviews/<week>.md`."""
        path = self.root / "reviews" / f"{_check_week(review.week)}.md"
        write_text_atomic(path, frontmatter.dump(review.to_meta(), review.body))
        return path

    def load_review(self, week: str) -> Review | None:
        """The review of `week`, or `None` if there is none."""
        path = self.root / "reviews" / f"{_check_week(week)}.md"
        return self._read(path, Review) if path.exists() else None

    def reviews(self) -> list[Review]:
        """All reviews, by week."""
        return sorted(self._folder("reviews", Review), key=lambda r: r.week)

    def save_acceptance(self, acceptance: Acceptance) -> Path:
        path = self.root / "acceptance" / _check_id(acceptance.card) / "index.md"
        write_text_atomic(path, frontmatter.dump(acceptance.to_meta(), acceptance.body))
        return path

    def load_acceptance(self, card: str) -> Acceptance | None:
        path = self.root / "acceptance" / _check_id(card) / "index.md"
        return self._read(path, Acceptance) if path.exists() else None

    def add_frame(self, card_id: str, src: Path, n: int) -> str | None:
        """Copies a frame into the acceptance folder as `frame-<n><extension>`; over 300 KB gives `None`."""
        folder = self.root / "acceptance" / _check_id(card_id)
        src = Path(src)
        ext = src.suffix.lower()
        if ext not in FRAME_EXTENSIONS:
            raise ValueError(t("store.bad_frame_ext", ext=src.suffix))
        if src.stat().st_size > FRAME_MAX_BYTES:
            return None
        name = f"frame-{n}{ext}"
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, folder / name)
        return name

    # --- backlog order ---

    def order(self) -> list[str]:
        """The backlog order: from `order.md` without stray ids, new cards at the end."""
        cards = {c.id: c for c in self.cards()}
        result: list[str] = []
        for id in self._order_ids():
            if id in cards and id not in result:
                result.append(id)
        result += [
            id for id, c in cards.items()
            if c.status in _ORDERED_STATUSES and id not in result
        ]
        return result

    def _order_ids(self) -> list[str]:
        path = self.root / "order.md"
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        return [line.split()[0] for line in lines if line.strip() and not line.startswith("#")]

    def set_order(self, ids: list[str]) -> None:
        """Writes `order.md`; ids without a card are skipped, the title comes from the card."""
        cards = {c.id: c for c in self.cards()}
        rows = [f"{id}  {' '.join(cards[id].title.split())}" for id in ids if id in cards]
        write_text_atomic(self.root / "order.md", "\n".join([ORDER_TITLE, "", *rows]) + "\n")

    # --- the driver lock and "seen" ---

    def _read_toml(self, name: str) -> dict | None:
        path = self.root / name
        if not path.exists():
            return None
        try:
            return tomllib.loads(path.read_text(encoding="utf-8-sig"))
        except tomllib.TOMLDecodeError as error:
            raise LoadError(t("store.bad_toml", error=error), path) from error

    def lock(self) -> dict | None:
        """The driver lock `{"host", "at"}` or `None`."""
        return self._read_toml("driver.lock")

    def write_lock(self, host: str, at: str) -> None:
        write_text_atomic(self.root / "driver.lock", frontmatter.toml_flat({"host": host, "at": at}))

    def clear_lock(self) -> None:
        (self.root / "driver.lock").unlink(missing_ok=True)

    def seen(self) -> dict[str, str]:
        """When each machine last looked at the state."""
        return self._read_toml("seen.toml") or {}

    def mark_seen(self, host: str, at: str) -> None:
        write_text_atomic(self.root / "seen.toml", frontmatter.toml_flat({**self.seen(), host: at}))
