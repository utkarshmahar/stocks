import schwab.auth
from shared.config import get_settings


def get_schwab_client():
    """Create an authenticated Schwab API client from token file.

    Adapted from /home/umahar/options/query_options_continuous_rpi.py
    """
    settings = get_settings()
    try:
        client = schwab.auth.client_from_token_file(
            settings.schwab_token_path,
            settings.schwab_api_key,
            settings.schwab_app_secret,
        )
        return client
    except FileNotFoundError:
        raise RuntimeError(
            f"Token file not found at {settings.schwab_token_path}. "
            "Run authenticate_schwab.py first."
        )
    except Exception as e:
        error_msg = str(e).lower()
        if "refresh token" in error_msg and "expired" in error_msg:
            raise RuntimeError(
                "Schwab refresh token has expired (7-day limit). "
                "Re-authenticate at /home/umahar/options/"
            )
        raise RuntimeError(f"Schwab auth failed: {e}")
