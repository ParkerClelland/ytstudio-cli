import json
import shutil

import typer

from ytstudio.api import api, authenticate
from ytstudio.config import (
    ensure_profile_dir,
    get_active_profile,
    get_profile_dir,
    list_profiles,
    set_active_profile,
    validate_profile_name,
)
from ytstudio.demo import is_demo_mode
from ytstudio.services import get_data_service
from ytstudio.ui import console, create_table

app = typer.Typer(help="Manage channel profiles")


@app.command("list")
def list_channels(
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    profiles = list_profiles()
    active_profile = get_active_profile()

    if not profiles:
        console.print(
            "[yellow]No channel profiles configured. Run 'ytstudio channel add NAME' to get started.[/yellow]"
        )
        return

    rows = [{"name": profile, "active": profile == active_profile} for profile in profiles]

    if as_json:
        print(json.dumps(rows, indent=2))
        return

    table = create_table()
    table.add_column("Profile")
    table.add_column("Active")
    for profile in profiles:
        table.add_row(profile, "[green]✓[/green]" if profile == active_profile else "")
    console.print(table)


@app.command()
def status():
    profiles = list_profiles()
    if not profiles:
        console.print(
            "[red]No channel profiles configured. Add one with 'ytstudio channel add NAME'.[/red]"
        )
        raise typer.Exit(1)

    profile = get_active_profile()
    service = get_data_service()
    response = api(service.channels().list(part="snippet,statistics", mine=True)) or {}

    items = response.get("items", [])
    if not items:
        console.print("[red]No channel found for the active profile.[/red]")
        raise typer.Exit(1)

    channel = items[0]
    snippet = channel.get("snippet", {})
    statistics = channel.get("statistics", {})

    table = create_table()
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Profile", profile)
    table.add_row("Channel", str(snippet.get("title", "N/A")))
    table.add_row("Subscribers", str(statistics.get("subscriberCount", "N/A")))
    table.add_row("Videos", str(statistics.get("videoCount", "N/A")))
    console.print(table)


@app.command()
def add(
    name: str = typer.Argument(...),
):
    name = validate_profile_name(name)

    if get_profile_dir(name).exists():
        console.print(f"[red]Profile '{name}' already exists.[/red]")
        raise typer.Exit(1)

    ensure_profile_dir(name)

    if is_demo_mode():
        console.print(f"[green]✓[/green] Channel added as profile '{name}'")
        return

    try:
        authenticate(profile=name)
    except Exception as exc:
        shutil.rmtree(get_profile_dir(name), ignore_errors=True)
        console.print(f"[red]Failed to authenticate profile '{name}': {exc}[/red]")
        raise typer.Exit(1) from None

    console.print(f"[green]✓[/green] Channel added as profile '{name}'")


@app.command()
def use(
    name: str = typer.Argument(...),
):
    name = validate_profile_name(name)
    profiles = list_profiles()
    if name not in profiles:
        console.print(f"[red]Profile '{name}' not found.[/red]")
        console.print(f"Available profiles: {', '.join(profiles)}")
        raise typer.Exit(1)

    set_active_profile(name)
    console.print(f"[green]✓[/green] Switched to profile '{name}'")


@app.command()
def remove(
    name: str = typer.Argument(...),
):
    name = validate_profile_name(name)

    profile_dir = get_profile_dir(name)
    if not profile_dir.exists():
        console.print(f"[red]Profile '{name}' not found.[/red]")
        raise typer.Exit(1)

    if name == get_active_profile():
        console.print(
            f"[red]Cannot remove active profile '{name}'. Switch to another profile first with 'ytstudio channel use OTHER'.[/red]"
        )
        raise typer.Exit(1)

    _ = typer.confirm(f"Remove profile '{name}' and its credentials?", abort=True)
    shutil.rmtree(profile_dir)
    console.print(f"[green]✓[/green] Removed profile '{name}'")
