import json
import re
from pathlib import Path
from typing import Any

import typer
from rich.prompt import Prompt

from ytstudio.ui import console, success_message

CONFIG_DIR = Path.home() / ".config" / "ytstudio-cli"
CLIENT_SECRETS_FILE = CONFIG_DIR / "client_secrets.json"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"


def ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def validate_profile_name(name: str) -> str:
    """Validate profile name - alphanumeric, hyphens, underscores only."""
    if not re.match(r"^[a-zA-Z0-9_-]+$", name):
        raise typer.BadParameter(
            f"Profile name '{name}' is invalid. Use only letters, numbers, hyphens, and underscores."
        )
    return name


def get_active_profile() -> str:
    """Return the active profile name. Defaults to 'default' if config.json missing."""
    config_file = CONFIG_DIR / "config.json"
    if not config_file.exists():
        return "default"
    data = json.loads(config_file.read_text())
    return data.get("active_profile", "default")


def set_active_profile(name: str) -> None:
    """Set the active profile name in config.json."""
    ensure_config_dir()
    config_file = CONFIG_DIR / "config.json"
    data = {}
    if config_file.exists():
        data = json.loads(config_file.read_text())
    data["active_profile"] = name
    config_file.write_text(json.dumps(data, indent=2))


def get_profile_dir(name: str) -> Path:
    """Return the Path to a named profile's directory."""
    return CONFIG_DIR / "profiles" / name


def get_profile_credentials_path(name: str) -> Path:
    """Return the Path to a named profile's credentials.json."""
    return get_profile_dir(name) / "credentials.json"


def ensure_profile_dir(name: str) -> None:
    """Create the profile directory if it doesn't exist."""
    get_profile_dir(name).mkdir(parents=True, exist_ok=True)


def list_profiles() -> list[str]:
    """Return sorted list of profile names. Returns [] if no profiles directory."""
    profiles_dir = CONFIG_DIR / "profiles"
    if not profiles_dir.exists():
        return []
    return sorted([p.name for p in profiles_dir.iterdir() if p.is_dir()])


def setup_credentials(client_secrets_file: str | None = None) -> None:
    ensure_config_dir()

    if client_secrets_file:
        # Copy provided file
        source = Path(client_secrets_file)
        if not source.exists():
            console.print(f"[red]File not found: {client_secrets_file}[/red]")
            raise SystemExit(1)

        CLIENT_SECRETS_FILE.write_text(source.read_text())
        success_message(f"Client secrets saved to {CLIENT_SECRETS_FILE}")
    else:
        # Interactive setup
        console.print("\n[bold]ytstudio-cli Setup[/bold]\n")
        console.print("You need to create a Google Cloud project and OAuth credentials.")
        console.print("See: https://github.com/jdwit/ytstudio-cli#setup\n")

        client_id = Prompt.ask("Enter your OAuth Client ID")
        client_secret = Prompt.ask("Enter your OAuth Client Secret")

        secrets = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        }

        CLIENT_SECRETS_FILE.write_text(json.dumps(secrets, indent=2))
        console.print()
        success_message(f"Client secrets saved to {CLIENT_SECRETS_FILE}")

    console.print("\nRun [bold]ytstudio login[/bold] to authenticate with YouTube.")


def get_client_secrets() -> dict[str, Any] | None:
    if not CLIENT_SECRETS_FILE.exists():
        return None
    return json.loads(CLIENT_SECRETS_FILE.read_text())


def save_credentials(credentials: dict[str, Any], profile: str | None = None) -> None:
    if profile is not None:
        ensure_profile_dir(profile)
        get_profile_credentials_path(profile).write_text(json.dumps(credentials, indent=2))
    else:
        active = get_active_profile()
        profile_path = get_profile_credentials_path(active)
        if profile_path.parent.exists() or (CONFIG_DIR / "profiles").exists():
            ensure_profile_dir(active)
            profile_path.write_text(json.dumps(credentials, indent=2))
        else:
            # Fallback: save to legacy path (before profiles/ dir exists)
            ensure_config_dir()
            CREDENTIALS_FILE.write_text(json.dumps(credentials, indent=2))


def load_credentials() -> dict[str, Any] | None:
    active = get_active_profile()
    profile_path = get_profile_credentials_path(active)
    if profile_path.exists():
        return json.loads(profile_path.read_text())
    # Legacy fallback: check old flat file
    if CREDENTIALS_FILE.exists():
        return json.loads(CREDENTIALS_FILE.read_text())
    return None


def clear_credentials(profile: str | None = None) -> None:
    target = profile if profile is not None else get_active_profile()
    profile_path = get_profile_credentials_path(target)
    if profile_path.exists():
        profile_path.unlink()
    elif CREDENTIALS_FILE.exists():
        CREDENTIALS_FILE.unlink()
