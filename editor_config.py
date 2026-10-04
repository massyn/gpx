"""Clean-up and routing settings for the track editor, read from gpx_config.ini."""

import configparser
import logging
import os
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

SECTION = "cleanup"
DEFAULTS = {
    "stop_radius_m": 50.0,
    "stop_min_duration_sec": 120.0,
    "stop_merge_radius_m": 100.0,
    "rdp_epsilon": 0.00005,
    "smooth_min_reduction_pct": 2.0,
    "gap_min_km": 5.0,
    "osrm_url": "https://router.project-osrm.org/route/v1/driving",
    "nominatim_url": "https://nominatim.openstreetmap.org/search",
    "overpass_url": "https://overpass-api.de/api/interpreter",
    "nearby_max_results": 20,
    "osm_lookup_radius_m": 250.0,
    "osm_url": "https://www.openstreetmap.org",
}

CONFIG_PATH = Path(
    os.environ.get("GPX_CONFIG", Path(__file__).parent / "gpx_config.ini")
)


class ConfigError(ValueError):
    """A setting in the config file has the wrong type."""


@lru_cache(maxsize=1)
def load() -> dict:
    """Defaults overridden by known keys in the [cleanup] section, cast to each default's type."""
    config = dict(DEFAULTS)
    parser = configparser.ConfigParser()
    if not parser.read(CONFIG_PATH, encoding="utf-8"):
        logger.info("No editor config at %s; using defaults", CONFIG_PATH)
        return config
    if not parser.has_section(SECTION):
        logger.warning("%s has no [%s] section; using defaults", CONFIG_PATH, SECTION)
        return config

    for key, raw in parser.items(SECTION):
        if key not in DEFAULTS:
            logger.warning("Ignoring unknown editor config key: %s", key)
            continue
        try:
            config[key] = type(DEFAULTS[key])(raw)
        except ValueError:
            raise ConfigError(
                f"{CONFIG_PATH}: {key} = {raw!r} is not a valid number"
            ) from None
    return config
