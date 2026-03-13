import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

import typer
from googleapiclient.errors import HttpError

from ytstudio.api import api, handle_api_error
from ytstudio.services import get_data_service
from ytstudio.ui import (
    console,
    create_kv_table,
    create_table,
    dim,
    success_message,
    truncate,
)

app = typer.Typer(help="Livestream management commands")


class BroadcastStatus(StrEnum):
    all = "all"
    active = "active"
    completed = "completed"
    upcoming = "upcoming"

    def to_api_value(self) -> str:
        """Convert to YouTube API broadcastStatus value"""
        return {"all": "all", "active": "active", "completed": "completed", "upcoming": "upcoming"}[
            self.value
        ]


class PrivacyStatus(StrEnum):
    public = "public"
    private = "private"
    unlisted = "unlisted"


@dataclass
class Broadcast:
    id: str
    title: str
    status: str
    lifecycle_status: str
    scheduled_start: str
    scheduled_end: str = ""
    description: str = ""
    privacy: str = "public"
    actual_start: str = ""
    actual_end: str = ""
    bound_stream_id: str = ""


_LIVESTREAM_ERRORS = {
    "invalidTransition": "Cannot perform this transition. Broadcast may not be in the correct state.",
    "redundantTransition": "Broadcast is already in the requested state.",
    "liveStreamingNotEnabled": "Live streaming is not enabled for this channel. Enable it at youtube.com/features",
    "errorStreamInactive": "No active live stream is bound to this broadcast. Bind a stream in YouTube Studio first.",
    "liveBroadcastNotFound": "Broadcast not found.",
}


def _handle_livestream_error(e: HttpError):
    detail = e.error_details[0] if e.error_details else {}
    error_details = detail if isinstance(detail, dict) else {}
    reason = error_details.get("reason", "")
    if reason in _LIVESTREAM_ERRORS:
        console.print(f"[red]{_LIVESTREAM_ERRORS[reason]}[/red]")
        raise typer.Exit(1)
    handle_api_error(e)


def _parse_broadcast(item: dict[str, Any]) -> Broadcast:
    snippet_value = item.get("snippet")
    status_value = item.get("status")
    content_value = item.get("contentDetails")
    snippet = snippet_value if isinstance(snippet_value, dict) else {}
    status = status_value if isinstance(status_value, dict) else {}
    content = content_value if isinstance(content_value, dict) else {}
    return Broadcast(
        id=str(item["id"]),
        title=snippet.get("title", ""),
        status=status.get("lifeCycleStatus", ""),
        lifecycle_status=status.get("lifeCycleStatus", ""),
        scheduled_start=snippet.get("scheduledStartTime", ""),
        scheduled_end=snippet.get("scheduledEndTime", ""),
        description=snippet.get("description", ""),
        privacy=status.get("privacyStatus", "public"),
        actual_start=snippet.get("actualStartTime", ""),
        actual_end=snippet.get("actualEndTime", ""),
        bound_stream_id=content.get("boundStreamId", ""),
    )


def _fetch_broadcast(service, broadcast_id: str) -> Broadcast | None:
    response = (
        api(
            service.liveBroadcasts().list(
                part="snippet,status,contentDetails",
                id=broadcast_id,
            )
        )
        or {}
    )
    for item in response.get("items", []):
        if item.get("id") == broadcast_id:
            return _parse_broadcast(item)
    return None


@app.command("list")
def list_broadcasts(
    status: BroadcastStatus = typer.Option(
        BroadcastStatus.all, "--status", "-s", help="Filter: all, active, completed, upcoming"
    ),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of broadcasts to list"),
    page_token: str = typer.Option(None, "--page-token", "-p", help="Page token for pagination"),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table, json"),
):
    """List your YouTube live broadcasts"""
    service = get_data_service()
    response = (
        api(
            service.liveBroadcasts().list(
                part="snippet,status,contentDetails",
                broadcastStatus=status.to_api_value(),
                maxResults=min(limit, 50),
                pageToken=page_token,
            )
        )
        or {}
    )
    broadcasts = [_parse_broadcast(item) for item in response.get("items", [])]
    broadcasts.sort(key=lambda b: b.scheduled_start or "", reverse=True)

    if not broadcasts:
        console.print("[yellow]No broadcasts found[/yellow]")
        return

    if output == "json":
        print(
            json.dumps(
                {
                    "broadcasts": [asdict(b) for b in broadcasts],
                    "next_page_token": response.get("nextPageToken"),
                    "total_results": (response.get("pageInfo") or {}).get("totalResults", 0),
                },
                indent=2,
            )
        )
    else:
        table = create_table()
        table.add_column("ID", style="yellow")
        table.add_column("Title", style="cyan")
        table.add_column("Status")
        table.add_column("Scheduled Start")
        table.add_column("Privacy")

        for broadcast in broadcasts:
            scheduled = (
                broadcast.scheduled_start[:16].replace("T", " ")
                if broadcast.scheduled_start
                else "—"
            )
            table.add_row(
                broadcast.id,
                truncate(broadcast.title),
                broadcast.lifecycle_status,
                scheduled,
                broadcast.privacy,
            )

        console.print(table)

        if response.get("nextPageToken"):
            console.print(f"\nNext page: --page-token {response['nextPageToken']}")


@app.command()
def show(
    broadcast_id: str = typer.Argument(..., help="Broadcast ID"),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table, json"),
):
    """Show details for a specific broadcast"""
    service = get_data_service()
    broadcast = _fetch_broadcast(service, broadcast_id)

    if not broadcast:
        console.print(f"[red]Broadcast not found: {broadcast_id}[/red]")
        raise typer.Exit(1)

    if output == "json":
        print(json.dumps(asdict(broadcast), indent=2))
        return

    console.print(f"\n[bold]{broadcast.title}[/bold]\n")

    table = create_kv_table()
    table.add_column("field", style="dim")
    table.add_column("value")

    table.add_row("status", broadcast.lifecycle_status)
    table.add_row("privacy", broadcast.privacy)
    table.add_row("scheduled start", broadcast.scheduled_start or "—")
    table.add_row("scheduled end", broadcast.scheduled_end or "—")
    table.add_row("actual start", broadcast.actual_start or "—")
    table.add_row("actual end", broadcast.actual_end or "—")
    table.add_row("stream bound", "Yes" if broadcast.bound_stream_id else "No")
    table.add_row("description", broadcast.description or "—")

    console.print(table)


@app.command()
def start(
    broadcast_id: str = typer.Argument(..., help="Broadcast ID"),
):
    """Start a live broadcast (transition to live)"""
    service = get_data_service()
    try:
        response = api(
            service.liveBroadcasts().transition(
                broadcastStatus="live",
                id=broadcast_id,
                part="id,snippet,status",
            )
        )
    except HttpError as e:
        _handle_livestream_error(e)
        return
    assert response is not None
    success_message(f"Broadcast transitioning to live: {broadcast_id}")
    console.print(f"Current status: {response['status']['lifeCycleStatus']}")
    console.print(dim("Note: Transition is asynchronous. Status may take a moment to update."))


@app.command()
def stop(
    broadcast_id: str = typer.Argument(..., help="Broadcast ID"),
):
    """Stop a live broadcast (transition to complete)"""
    service = get_data_service()
    try:
        response = api(
            service.liveBroadcasts().transition(
                broadcastStatus="complete",
                id=broadcast_id,
                part="id,snippet,status",
            )
        )
    except HttpError as e:
        _handle_livestream_error(e)
        return
    assert response is not None
    success_message(f"Broadcast stopped: {broadcast_id}")
    console.print(f"Current status: {response['status']['lifeCycleStatus']}")


@app.command()
def schedule(
    title: str = typer.Option(..., "--title", "-t", help="Broadcast title"),
    scheduled_start: str = typer.Option(
        ...,
        "--scheduled-start",
        help="Scheduled start time in ISO 8601 format (e.g. 2026-04-01T18:00:00-05:00)",
    ),
    description: str = typer.Option("", "--description", "-d", help="Broadcast description"),
    privacy: PrivacyStatus = typer.Option(
        PrivacyStatus.public, "--privacy", help="Privacy status: public, private, unlisted"
    ),
    scheduled_end: str = typer.Option(
        "",
        "--scheduled-end",
        help="Scheduled end time in ISO 8601 format (e.g. 2026-04-01T19:00:00-05:00)",
    ),
    execute: bool = typer.Option(False, "--execute", help="Create broadcast (default is dry-run)"),
):
    """Schedule a new live broadcast"""

    snippet_body = {
        "title": title,
        "description": description,
        "scheduledStartTime": scheduled_start,
    }
    status_body = {"privacyStatus": privacy.value}
    body = {"snippet": snippet_body, "status": status_body}
    if scheduled_end:
        snippet_body["scheduledEndTime"] = scheduled_end

    if not execute:
        console.print("[bold]Preview new broadcast:[/bold]\n")
        console.print(f"title: [green]{title}[/green]")
        console.print(f"scheduled start: [green]{scheduled_start}[/green]")
        if description:
            console.print(f"description: [green]{description}[/green]")
        console.print(f"privacy: [green]{privacy.value}[/green]")
        if scheduled_end:
            console.print(f"scheduled end: [green]{scheduled_end}[/green]")
        console.print("\nRun with --execute to create")
        return

    service = get_data_service()
    try:
        response = (
            api(
                service.liveBroadcasts().insert(
                    part="snippet,status,contentDetails",
                    body=body,
                )
            )
            or {}
        )
    except HttpError as e:
        _handle_livestream_error(e)
        return
    assert response is not None
    broadcast_id = response.get("id", "unknown")
    success_message(f"Broadcast created: {broadcast_id} — {title}")


@app.command()
def update(
    broadcast_id: str = typer.Argument(..., help="Broadcast ID"),
    title: str = typer.Option(None, "--title", "-t", help="New title"),
    description: str = typer.Option(None, "--description", "-d", help="New description"),
    privacy: PrivacyStatus = typer.Option(None, "--privacy", help="New privacy status"),
    scheduled_start: str = typer.Option(
        None,
        "--scheduled-start",
        help="New scheduled start in ISO 8601 format (e.g. 2026-04-01T18:00:00-05:00)",
    ),
    scheduled_end: str = typer.Option(
        None,
        "--scheduled-end",
        help="New scheduled end in ISO 8601 format (e.g. 2026-04-01T19:00:00-05:00)",
    ),
    execute: bool = typer.Option(False, "--execute", help="Apply changes (default is dry-run)"),
):
    """Update a live broadcast's metadata"""
    if not any([title, description, privacy, scheduled_start, scheduled_end]):
        console.print(
            "[yellow]Nothing to update. Provide --title, --description, --privacy, --scheduled-start, or --scheduled-end[/yellow]"
        )
        raise typer.Exit(1)

    service = get_data_service()
    broadcast = _fetch_broadcast(service, broadcast_id)
    if not broadcast:
        console.print(f"[red]Broadcast not found: {broadcast_id}[/red]")
        raise typer.Exit(1)

    new_title = title if title else broadcast.title
    new_description = description if description is not None else broadcast.description
    new_privacy = privacy.value if privacy else broadcast.privacy
    new_scheduled_start = scheduled_start if scheduled_start else broadcast.scheduled_start

    snippet_body = {
        "title": new_title,
        "description": new_description,
        "scheduledStartTime": new_scheduled_start,
    }
    status_body = {"privacyStatus": new_privacy}
    body = {"id": broadcast_id, "snippet": snippet_body, "status": status_body}
    new_scheduled_end = scheduled_end if scheduled_end else broadcast.scheduled_end
    if new_scheduled_end:
        snippet_body["scheduledEndTime"] = new_scheduled_end

    if not execute:
        console.print("[bold]Preview changes:[/bold]\n")
        if title:
            console.print(f"title: {broadcast.title} → [green]{new_title}[/green]")
        if description is not None:
            console.print("description: [green](updated)[/green]")
        if privacy:
            console.print(f"privacy: {broadcast.privacy} → [green]{new_privacy}[/green]")
        if scheduled_start:
            console.print(
                f"scheduled start: {broadcast.scheduled_start} → [green]{new_scheduled_start}[/green]"
            )
        if scheduled_end:
            console.print(
                f"scheduled end: {broadcast.scheduled_end or '—'} → [green]{new_scheduled_end}[/green]"
            )
        console.print("\nRun with --execute to apply")
        return

    try:
        api(
            service.liveBroadcasts().update(
                part="snippet,status",
                body=body,
            )
        )
    except HttpError as e:
        _handle_livestream_error(e)
        return
    success_message(f"Updated: {new_title}")
