"""Russian messages: the area modules listed in AREAS, merged."""

from the_nod.i18n import collect

AREAS = ("core", "driver", "review", "doctor", "mcp", "importer", "autostart", "migrate")
MESSAGES = collect(__name__, AREAS)
