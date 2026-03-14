# YT Studio CLI

[![CI](https://github.com/jdwit/ytstudio/actions/workflows/ci.yml/badge.svg)](https://github.com/jdwit/ytstudio/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/ytstudio-cli)](https://pypi.org/project/ytstudio-cli/)
[![Python](https://img.shields.io/pypi/pyversions/ytstudio-cli)](https://pypi.org/project/ytstudio-cli/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Manage and analyze your YouTube channel from the terminal. Ideal for automation and AI workflows.

![demo](demo.gif)

## Motivation

I built this because I needed to bulk update video titles for a YouTube channel I manage with 300+
videos. YouTube Studio does not support bulk search-replace operations, which made it a tedious
manual process. This tool uses the YouTube Data API to perform bulk operations on video metadata.
Furthermore, it provides features for analytics and comment moderation, all accesible from the
command line.

## Installation

I recommend the excellent [uv](https://uv.io/) tool for installation:

```bash
uv tool install ytstudio-cli
```

## Setup

1. Create a [Google Cloud project](https://console.cloud.google.com/)
1. Enable **YouTube Data API v3** and **YouTube Analytics API**
1. Configure OAuth consent screen:
   - Go to **APIs & Services** → **OAuth consent screen**
   - Select **External** and create
   - Fill in app name and your email
   - Skip scopes, then add yourself as a test user
   - Leave the app in "Testing" mode (no verification needed)
1. Create OAuth credentials:
   - Go to **APIs & Services** → **Credentials**
   - Click **Create Credentials** → **OAuth client ID**how
   - Select **Desktop app** as application type
   - Download the JSON file
1. Configure ytstudio:

```bash
ytstudio init --client-secrets path/to/client_secret_<id>.json
ytstudio login
```

Credentials stored in `~/.config/ytstudio/`.

## API quota

The YouTube Data API enforces a default quota of 10_000 units per project per day. Most read
operations (listing videos, comments, channel info) cost 1 unit, while write operations like
updating video metadata or moderating comments cost 50 units each. Bulk updates can consume quota
quickly. When exceeded, the API returns a 403 error; quota resets at midnight Pacific Time.

You can request a quota increase via **IAM & Admin** → **Quotas** in the
[Google Cloud Console](https://console.cloud.google.com/). See the
[official quota documentation](https://developers.google.com/youtube/v3/getting-started#quota) for
full details.

## Livestreams

Manage live broadcasts from the command line: list, inspect, schedule, update settings, and control
broadcast lifecycle.

### List broadcasts

```bash
ytstudio livestreams list                        # List upcoming/active/completed broadcasts
ytstudio livestreams list --status active         # Filter by status: all, active, completed, upcoming
ytstudio livestreams list --limit 10              # Limit displayed results (default: 20)
ytstudio livestreams list --output json           # JSON output
```

Results are fetched in batches of 50 from the API, sorted by scheduled start date, then truncated to
`--limit`. Use `--page-token` to paginate through larger result sets.

### Show broadcast details

```bash
ytstudio livestreams show BROADCAST_ID
ytstudio livestreams show BROADCAST_ID --output json
```

Displays metadata, scheduling, and broadcast settings including auto-start/stop, DVR, embed,
recording, closed captions, latency, projection, and made-for-kids status.

### Schedule a broadcast

```bash
ytstudio livestreams schedule \
  --title "My Stream" \
  --scheduled-start "2026-04-01T18:00:00-05:00"

# Preview first (default), then create:
ytstudio livestreams schedule \
  --title "My Stream" \
  --scheduled-start "2026-04-01T18:00:00-05:00" \
  --description "Going live!" \
  --privacy unlisted \
  --scheduled-end "2026-04-01T20:00:00-05:00" \
  --execute
```

### Update a broadcast

Update metadata and broadcast settings. All updates are dry-run by default — add `--execute` to
apply.

```bash
# Metadata
ytstudio livestreams update BROADCAST_ID --title "New Title"
ytstudio livestreams update BROADCAST_ID --privacy private --execute

# Broadcast settings
ytstudio livestreams update BROADCAST_ID --auto-start --auto-stop
ytstudio livestreams update BROADCAST_ID --no-dvr --latency low
ytstudio livestreams update BROADCAST_ID --no-embed --projection 360
ytstudio livestreams update BROADCAST_ID --made-for-kids --execute
```

Available broadcast setting flags:

| Flag | Description |
|---|---|
| `--auto-start / --no-auto-start` | Auto-start broadcast when stream begins |
| `--auto-stop / --no-auto-stop` | Auto-stop broadcast when stream ends |
| `--dvr / --no-dvr` | Enable DVR controls (pause/rewind) for viewers |
| `--embed / --no-embed` | Allow embedding on external sites |
| `--record-from-start / --no-record-from-start` | Record broadcast for archive (default: on) |
| `--closed-captions` | Caption ingestion method (see note below) |
| `--latency` | Latency preference: `normal`, `low`, `ultraLow` |
| `--projection` | Video projection: `rectangular`, `360` |
| `--made-for-kids / --not-made-for-kids` | Made-for-kids designation |

> **Note on closed captions:** The `--closed-captions` setting controls how captions are *ingested*
> into the broadcast — it does not control YouTube's automatic live captions. The values
> `closedCaptionsHttpPost` and `closedCaptionsEmbedded` are for external captioning services that
> send captions via HTTP or embed them in the video stream (CEA-608/708). YouTube's automatic
> speech-to-text captions are managed separately in YouTube Studio and are not exposed through the
> Data API. A value of `closedCaptionsDisabled` simply means no external caption source is
> configured.

Most broadcast settings can only be changed while the broadcast is in `created` or `ready` status.
Once a broadcast transitions to `testing` or `live`, these fields become read-only.

### Start and stop

```bash
ytstudio livestreams start BROADCAST_ID    # Transition to live
ytstudio livestreams stop BROADCAST_ID     # Transition to complete
```

## Disclaimer

This project is not affiliated with or endorsed by Google. YouTube and YouTube Studio are trademarks
of Google. All channel data is accessed exclusively through the official
[YouTube Data API](https://developers.google.com/youtube/v3) and
[YouTube Analytics API](https://developers.google.com/youtube/analytics).
