import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    """Loads required/optional API keys from .env. GOOGLE_MAPS_ROUTES_API_KEY isn't listed here
    since it's only needed by the testing/ harness (services/google_routes_client.py), not by
    the app itself, read directly via os.getenv() at the point of use instead."""
    STM_API_KEY = os.environ.get("STM_API_KEY", "")

    # STM_API_KEY powers realtime bus positions/delays (services/stm_client.py), the app still
    # runs and plans trips off the static schedule without it, just without live adjustments, so
    # this only warns rather than failing startup.
    _OPTIONAL_FOR_NOW = ("STM_API_KEY",)

    @classmethod
    def validate(cls):
        missing = [name for name in cls._OPTIONAL_FOR_NOW if not getattr(cls, name)]
        for name in missing:
            print(f"[config] warning: {name} is not set in .env (required by a later phase)")
        return missing
