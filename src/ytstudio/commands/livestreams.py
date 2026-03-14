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


class ClosedCaptionsType(StrEnum):
    disabled = "closedCaptionsDisabled"
    http_post = "closedCaptionsHttpPost"
    embedded = "closedCaptionsEmbedded"


class LatencyPreference(StrEnum):
    normal = "normal"
    low = "low"
    ultra_low = "ultraLow"


class Projection(StrEnum):
    rectangular = "rectangular"
    three_sixty = "360"


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
    auto_start: bool = False
    auto_stop: bool = False
    dvr: bool = True
    embed: bool = True
    record_from_start: bool = True
    closed_captions_type: str = "closedCaptionsDisabled"
    latency_preference: str = "normal"
    projection: str = "rectangular"
    made_for_kids: bool = False


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
        auto_start=content.get("enableAutoStart", False),
        auto_stop=content.get("enableAutoStop", False),
        dvr=content.get("enableDvr", True),
        embed=content.get("enableEmbed", True),
        record_from_start=content.get("recordFromStart", True),
        closed_captions_type=content.get("closedCaptionsType", "closedCaptionsDisabled"),
        latency_preference=content.get("latencyPreference", "normal"),
        projection=content.get("projection", "rectangular"),
        made_for_kids=status.get("selfDeclaredMadeForKids", False),
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
                maxResults=50,
                pageToken=page_token,
            )
        )
        or {}
    )
    broadcasts = [_parse_broadcast(item) for item in response.get("items", [])]
    broadcasts.sort(key=lambda b: b.scheduled_start or "", reverse=True)
    broadcasts = broadcasts[:limit]

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
    table.add_row("auto start", "Yes" if broadcast.auto_start else "No")
    table.add_row("auto stop", "Yes" if broadcast.auto_stop else "No")
    table.add_row("dvr", "Yes" if broadcast.dvr else "No")
    table.add_row("embed", "Yes" if broadcast.embed else "No")
    table.add_row("record from start", "Yes" if broadcast.record_from_start else "No")
    table.add_row("closed captions", broadcast.closed_captions_type)
    table.add_row("latency", broadcast.latency_preference)
    table.add_row("projection", broadcast.projection)
    table.add_row("made for kids", "Yes" if broadcast.made_for_kids else "No")
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
    auto_start: bool | None = typer.Option(
        None, "--auto-start/--no-auto-start", help="Auto-start when stream begins"
    ),
    auto_stop: bool | None = typer.Option(
        None, "--auto-stop/--no-auto-stop", help="Auto-stop when stream ends"
    ),
    dvr: bool | None = typer.Option(None, "--dvr/--no-dvr", help="Enable DVR controls for viewers"),
    embed: bool | None = typer.Option(
        None, "--embed/--no-embed", help="Allow embedding on external sites"
    ),
    record_from_start: bool | None = typer.Option(
        None, "--record-from-start/--no-record-from-start", help="Record broadcast for archive"
    ),
    closed_captions: ClosedCaptionsType = typer.Option(
        None,
        "--closed-captions",
        help="Closed captions: closedCaptionsDisabled, closedCaptionsHttpPost, closedCaptionsEmbedded",
    ),
    latency: LatencyPreference = typer.Option(
        None, "--latency", help="Latency: normal, low, ultraLow"
    ),
    projection: Projection = typer.Option(
        None, "--projection", help="Projection: rectangular, 360"
    ),
    made_for_kids: bool | None = typer.Option(
        None, "--made-for-kids/--not-made-for-kids", help="Made for kids designation"
    ),
    execute: bool = typer.Option(False, "--execute", help="Apply changes (default is dry-run)"),
):
    """Update a live broadcast's metadata and settings"""
    has_snippet_changes = any([title, description, privacy, scheduled_start, scheduled_end])
    has_content_changes = any(
        v is not None
        for v in [
            auto_start,
            auto_stop,
            dvr,
            embed,
            record_from_start,
            closed_captions,
            latency,
            projection,
        ]
    )
    has_status_changes = made_for_kids is not None

    if not has_snippet_changes and not has_content_changes and not has_status_changes:
        console.print(
            "[yellow]Nothing to update. Provide --title, --description, --privacy, --scheduled-start, --scheduled-end, "
            "--auto-start, --auto-stop, --dvr, --embed, --record-from-start, --closed-captions, --latency, --projection, "
            "or --made-for-kids[/yellow]"
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
    status_body: dict[str, Any] = {"privacyStatus": new_privacy}
    new_scheduled_end = scheduled_end if scheduled_end else broadcast.scheduled_end
    if new_scheduled_end:
        snippet_body["scheduledEndTime"] = new_scheduled_end

    content_body: dict[str, Any] = {
        "enableAutoStart": auto_start if auto_start is not None else broadcast.auto_start,
        "enableAutoStop": auto_stop if auto_stop is not None else broadcast.auto_stop,
        "enableDvr": dvr if dvr is not None else broadcast.dvr,
        "enableEmbed": embed if embed is not None else broadcast.embed,
        "recordFromStart": record_from_start
        if record_from_start is not None
        else broadcast.record_from_start,
        "closedCaptionsType": closed_captions.value
        if closed_captions
        else broadcast.closed_captions_type,
        "latencyPreference": latency.value if latency else broadcast.latency_preference,
        "projection": projection.value if projection else broadcast.projection,
    }

    if made_for_kids is not None:
        status_body["selfDeclaredMadeForKids"] = made_for_kids

    parts = ["snippet", "status"]
    if has_content_changes:
        parts.append("contentDetails")

    body: dict[str, Any] = {"id": broadcast_id, "snippet": snippet_body, "status": status_body}
    if has_content_changes:
        body["contentDetails"] = content_body

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
        if auto_start is not None:
            console.print(f"auto start: {broadcast.auto_start} → [green]{auto_start}[/green]")
        if auto_stop is not None:
            console.print(f"auto stop: {broadcast.auto_stop} → [green]{auto_stop}[/green]")
        if dvr is not None:
            console.print(f"dvr: {broadcast.dvr} → [green]{dvr}[/green]")
        if embed is not None:
            console.print(f"embed: {broadcast.embed} → [green]{embed}[/green]")
        if record_from_start is not None:
            console.print(
                f"record from start: {broadcast.record_from_start} → [green]{record_from_start}[/green]"
            )
        if closed_captions:
            console.print(
                f"closed captions: {broadcast.closed_captions_type} → [green]{closed_captions.value}[/green]"
            )
        if latency:
            console.print(
                f"latency: {broadcast.latency_preference} → [green]{latency.value}[/green]"
            )
        if projection:
            console.print(f"projection: {broadcast.projection} → [green]{projection.value}[/green]")
        if made_for_kids is not None:
            console.print(
                f"made for kids: {broadcast.made_for_kids} → [green]{made_for_kids}[/green]"
            )
        console.print("\nRun with --execute to apply")
        return

    try:
        api(
            service.liveBroadcasts().update(
                part=",".join(parts),
                body=body,
            )
        )
    except HttpError as e:
        _handle_livestream_error(e)
        return
    success_message(f"Updated: {new_title}")
