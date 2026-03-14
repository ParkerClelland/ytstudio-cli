# pyright: reportMissingImports=false, reportMissingTypeStubs=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownMemberType=false

import json
from typing import cast

from typer.testing import CliRunner

from ytstudio.main import app

runner = CliRunner()


class TestLivestreamsList:
    def test_list_default(self, mock_auth):
        assert mock_auth is not None
        result = runner.invoke(app, ["livestreams", "list"])

        assert result.exit_code == 0
        assert "test_broadcast_123" in result.stdout
        assert "Test Live Stream" in result.stdout

    def test_list_json_output(self, mock_auth):
        mock_auth.liveBroadcasts.return_value.list.return_value.execute.return_value = {
            "items": [
                {
                    "id": "test_broadcast_123",
                    "snippet": {
                        "title": "Test Live Stream",
                        "description": "A test broadcast for unit testing",
                        "scheduledStartTime": "2026-04-01T20:00:00Z",
                        "scheduledEndTime": "2026-04-01T22:00:00Z",
                        "actualStartTime": "",
                        "actualEndTime": "",
                    },
                    "status": {
                        "lifeCycleStatus": "ready",
                        "privacyStatus": "public",
                        "recordingStatus": "notRecording",
                    },
                    "contentDetails": {"boundStreamId": "test_stream_001"},
                }
            ],
            "nextPageToken": "next-page-token",
            "pageInfo": {"totalResults": 1},
        }

        result = runner.invoke(app, ["livestreams", "list", "--output", "json"])

        assert result.exit_code == 0
        data = cast(dict[str, object], json.loads(result.stdout))
        broadcasts = cast(list[dict[str, object]], data["broadcasts"])
        assert "broadcasts" in data
        assert broadcasts[0]["id"] == "test_broadcast_123"
        assert data["next_page_token"] == "next-page-token"
        assert data["total_results"] == 1

    def test_list_empty(self, mock_auth):
        mock_auth.liveBroadcasts.return_value.list.return_value.execute.return_value = {"items": []}

        result = runner.invoke(app, ["livestreams", "list"])

        assert result.exit_code == 0
        assert "No broadcasts found" in result.stdout

    def test_list_status_filter(self, mock_auth):
        result = runner.invoke(app, ["livestreams", "list", "--status", "active"])

        assert result.exit_code == 0
        mock_auth.liveBroadcasts.return_value.list.assert_called_once_with(
            part="snippet,status,contentDetails",
            broadcastStatus="active",
            maxResults=50,
            pageToken=None,
        )

    def test_list_limit_and_page_token(self, mock_auth):
        result = runner.invoke(
            app,
            ["livestreams", "list", "--limit", "5", "--page-token", "page-2"],
        )

        assert result.exit_code == 0
        mock_auth.liveBroadcasts.return_value.list.assert_called_once_with(
            part="snippet,status,contentDetails",
            broadcastStatus="all",
            maxResults=50,
            pageToken="page-2",
        )

    def test_list_next_page_hint(self, mock_auth):
        mock_auth.liveBroadcasts.return_value.list.return_value.execute.return_value = {
            "items": [
                {
                    "id": "test_broadcast_123",
                    "snippet": {
                        "title": "Test Live Stream",
                        "description": "A test broadcast for unit testing",
                        "scheduledStartTime": "2026-04-01T20:00:00Z",
                        "scheduledEndTime": "2026-04-01T22:00:00Z",
                        "actualStartTime": "",
                        "actualEndTime": "",
                    },
                    "status": {
                        "lifeCycleStatus": "ready",
                        "privacyStatus": "public",
                        "recordingStatus": "notRecording",
                    },
                    "contentDetails": {"boundStreamId": "test_stream_001"},
                }
            ],
            "nextPageToken": "page-2",
        }

        result = runner.invoke(app, ["livestreams", "list"])

        assert result.exit_code == 0
        assert "--page-token page-2" in result.stdout


class TestLivestreamsShow:
    def test_show_table(self, mock_auth):
        assert mock_auth is not None
        result = runner.invoke(app, ["livestreams", "show", "test_broadcast_123"])

        assert result.exit_code == 0
        assert "Test Live Stream" in result.stdout
        assert "A test broadcast for unit testing" in result.stdout

    def test_show_json(self, mock_auth):
        assert mock_auth is not None
        result = runner.invoke(
            app, ["livestreams", "show", "test_broadcast_123", "--output", "json"]
        )

        assert result.exit_code == 0
        data = cast(dict[str, str], json.loads(result.stdout))
        assert data["id"] == "test_broadcast_123"
        assert data["title"] == "Test Live Stream"

    def test_show_not_found(self, mock_auth):
        mock_auth.liveBroadcasts.return_value.list.return_value.execute.return_value = {"items": []}

        result = runner.invoke(app, ["livestreams", "show", "test_broadcast_123"])

        assert result.exit_code == 1
        assert "Broadcast not found" in result.stdout

    def test_show_fetches_requested_id(self, mock_auth):
        result = runner.invoke(app, ["livestreams", "show", "test_broadcast_123"])

        assert result.exit_code == 0
        mock_auth.liveBroadcasts.return_value.list.assert_called_once_with(
            part="snippet,status,contentDetails",
            id="test_broadcast_123",
        )


class TestLivestreamsStart:
    def test_start_success(self, mock_auth):
        assert mock_auth is not None
        result = runner.invoke(app, ["livestreams", "start", "test_broadcast_123"])

        assert result.exit_code == 0
        assert "transitioning to live" in result.stdout.lower()
        assert "Current status: ready" in result.stdout

    def test_start_calls_live_transition(self, mock_auth):
        result = runner.invoke(app, ["livestreams", "start", "test_broadcast_123"])

        assert result.exit_code == 0
        mock_auth.liveBroadcasts.return_value.transition.assert_called_once_with(
            broadcastStatus="live",
            id="test_broadcast_123",
            part="id,snippet,status",
        )

    def test_stop_success(self, mock_auth):
        assert mock_auth is not None
        result = runner.invoke(app, ["livestreams", "stop", "test_broadcast_123"])

        assert result.exit_code == 0
        assert "stopped" in result.stdout.lower()
        assert "Current status: ready" in result.stdout

    def test_stop_calls_complete_transition(self, mock_auth):
        result = runner.invoke(app, ["livestreams", "stop", "test_broadcast_123"])

        assert result.exit_code == 0
        mock_auth.liveBroadcasts.return_value.transition.assert_called_once_with(
            broadcastStatus="complete",
            id="test_broadcast_123",
            part="id,snippet,status",
        )


class TestLivestreamsSchedule:
    def test_schedule_preview(self, mock_auth):
        assert mock_auth is not None
        result = runner.invoke(
            app,
            [
                "livestreams",
                "schedule",
                "--title",
                "Launch Stream",
                "--scheduled-start",
                "2026-04-01T20:00:00Z",
            ],
        )

        assert result.exit_code == 0
        assert "Preview" in result.stdout
        mock_auth.liveBroadcasts.return_value.insert.assert_not_called()

    def test_schedule_preview_shows_optional_fields(self, mock_auth):
        assert mock_auth is not None
        result = runner.invoke(
            app,
            [
                "livestreams",
                "schedule",
                "--title",
                "Launch Stream",
                "--scheduled-start",
                "2026-04-01T20:00:00Z",
                "--description",
                "Going live soon",
                "--privacy",
                "private",
                "--scheduled-end",
                "2026-04-01T22:00:00Z",
            ],
        )

        assert result.exit_code == 0
        assert "Going live soon" in result.stdout
        assert "private" in result.stdout
        assert "2026-04-01T22:00:00Z" in result.stdout

    def test_schedule_execute(self, mock_auth):
        result = runner.invoke(
            app,
            [
                "livestreams",
                "schedule",
                "--title",
                "Launch Stream",
                "--scheduled-start",
                "2026-04-01T20:00:00Z",
                "--execute",
            ],
        )

        assert result.exit_code == 0
        assert "Broadcast created" in result.stdout
        mock_auth.liveBroadcasts.return_value.insert.assert_called_once()

    def test_schedule_execute_passes_insert_body(self, mock_auth):
        result = runner.invoke(
            app,
            [
                "livestreams",
                "schedule",
                "--title",
                "Launch Stream",
                "--scheduled-start",
                "2026-04-01T20:00:00Z",
                "--description",
                "Going live soon",
                "--privacy",
                "unlisted",
                "--scheduled-end",
                "2026-04-01T22:00:00Z",
                "--execute",
            ],
        )

        assert result.exit_code == 0
        mock_auth.liveBroadcasts.return_value.insert.assert_called_once_with(
            part="snippet,status,contentDetails",
            body={
                "snippet": {
                    "title": "Launch Stream",
                    "description": "Going live soon",
                    "scheduledStartTime": "2026-04-01T20:00:00Z",
                    "scheduledEndTime": "2026-04-01T22:00:00Z",
                },
                "status": {"privacyStatus": "unlisted"},
            },
        )

    def test_schedule_missing_title(self, mock_auth):
        assert mock_auth is not None
        result = runner.invoke(
            app,
            ["livestreams", "schedule", "--scheduled-start", "2026-04-01T20:00:00Z"],
        )

        assert result.exit_code != 0

    def test_schedule_missing_scheduled_start(self, mock_auth):
        assert mock_auth is not None
        result = runner.invoke(app, ["livestreams", "schedule", "--title", "Launch Stream"])

        assert result.exit_code != 0


class TestLivestreamsUpdate:
    def test_update_preview(self, mock_auth):
        assert mock_auth is not None
        result = runner.invoke(
            app,
            ["livestreams", "update", "test_broadcast_123", "--title", "New Title"],
        )

        assert result.exit_code == 0
        assert "Preview" in result.stdout
        mock_auth.liveBroadcasts.return_value.update.assert_not_called()

    def test_update_preview_shows_changed_fields(self, mock_auth):
        assert mock_auth is not None
        result = runner.invoke(
            app,
            [
                "livestreams",
                "update",
                "test_broadcast_123",
                "--privacy",
                "private",
                "--scheduled-end",
                "2026-04-01T23:00:00Z",
            ],
        )

        assert result.exit_code == 0
        assert "privacy: public" in result.stdout
        assert "2026-04-01T23:00:00Z" in result.stdout

    def test_update_execute(self, mock_auth):
        result = runner.invoke(
            app,
            ["livestreams", "update", "test_broadcast_123", "--title", "New Title", "--execute"],
        )

        assert result.exit_code == 0
        assert "Updated: New Title" in result.stdout
        mock_auth.liveBroadcasts.return_value.update.assert_called_once()

    def test_update_execute_passes_merged_body(self, mock_auth):
        assert mock_auth is not None
        result = runner.invoke(
            app,
            [
                "livestreams",
                "update",
                "test_broadcast_123",
                "--title",
                "New Title",
                "--description",
                "Updated description",
                "--privacy",
                "private",
                "--scheduled-start",
                "2026-04-02T20:00:00Z",
                "--scheduled-end",
                "2026-04-02T22:00:00Z",
                "--execute",
            ],
        )

        assert result.exit_code == 0
        mock_auth.liveBroadcasts.return_value.update.assert_called_once_with(
            part="snippet,status",
            body={
                "id": "test_broadcast_123",
                "snippet": {
                    "title": "New Title",
                    "description": "Updated description",
                    "scheduledStartTime": "2026-04-02T20:00:00Z",
                    "scheduledEndTime": "2026-04-02T22:00:00Z",
                },
                "status": {"privacyStatus": "private"},
            },
        )

    def test_update_uses_existing_values_for_unchanged_fields(self, mock_auth):
        result = runner.invoke(
            app,
            ["livestreams", "update", "test_broadcast_123", "--title", "Renamed", "--execute"],
        )

        assert result.exit_code == 0
        mock_auth.liveBroadcasts.return_value.update.assert_called_once_with(
            part="snippet,status",
            body={
                "id": "test_broadcast_123",
                "snippet": {
                    "title": "Renamed",
                    "description": "A test broadcast for unit testing",
                    "scheduledStartTime": "2026-04-01T20:00:00Z",
                    "scheduledEndTime": "2026-04-01T22:00:00Z",
                },
                "status": {"privacyStatus": "public"},
            },
        )

    def test_update_no_changes(self, mock_auth):
        assert mock_auth is not None
        result = runner.invoke(app, ["livestreams", "update", "test_broadcast_123"])

        assert result.exit_code == 1
        assert "Nothing to update" in result.stdout

    def test_update_not_found(self, mock_auth):
        mock_auth.liveBroadcasts.return_value.list.return_value.execute.return_value = {"items": []}

        result = runner.invoke(
            app,
            ["livestreams", "update", "test_broadcast_123", "--title", "New Title"],
        )

        assert result.exit_code == 1
        assert "Broadcast not found" in result.stdout
