# YouTube Auditor

![Python](https://img.shields.io/badge/python-%3E%3D3.10-blue) ![License](https://img.shields.io/badge/license-Apache%202.0-green) ![Selenium](https://img.shields.io/badge/selenium-%3E%3D4.11-brightgreen)

An automated auditing tool for studying how YouTube's recommendation algorithm behaves differently for long-form videos versus YouTube Shorts. Originally built to support the paper: ["Long Story Short: Auditing U.S. Political Polarization in Recommendations for Long- vs. Short-form Videos on YouTube"](https://kumarde.com/papers/longstoryshort.pdf).

The tool simulates a user's browsing session — watching a series of seed videos to shape a recommendation profile, then following the autoplay chain and capturing every recommendation YouTube surfaces along the way.

This tool is developed and tested with Chrome. Other browsers may be supported but without guaranteed functionality.


## Installation

**Requirements:** Python ≥ 3.10, Selenium ≥ 4.11.0

```bash
git clone https://github.com/slimykat/longstoryshort-yt-audit.git
cd longstoryshort-yt-audit
# if using python virtual environment (suggested)
# source .venv/bin/activate
pip install -e .
```

ChromeDriver is managed automatically by Selenium Manager (above version 4.11) — no separate download needed.

## Quick start

```python
from longstoryshort import YouTubeAuditor

auditor = YouTubeAuditor()

auditor.configure_browser(browser_type="Chrome", headless=True)
auditor.launch_browser(mode="long", max_duration=10)

auditor.train(["VIDEO_ID_1", "VIDEO_ID_2", "VIDEO_ID_3"])
auditor.collect_play_next(collect_video_num=15)

results = auditor.report()
auditor.clean_up()
```

See [`examples/demo.ipynb`](examples/demo.ipynb) for a full annotated walkthrough with pre-saved sample outputs for both long-form and Shorts modes.

## How it works

1. **Configure** — set browser options (headless, incognito, extensions)
2. **Train** — watch a list of seed videos for `max_duration` seconds each; this builds a recommendation profile that nudges YouTube's algorithm
3. **Collect** — press play-next (`Shift+N` for long-form, `↓` for Shorts) repeatedly and record every URL visited and every recommendation shown in the sidebar or preload queue
4. **Report** — get a structured dictionary of everything collected

## Example output

Running a 10-hop long-form audit seeded with three music videos:

```python
auditor.train(["dQw4w9WgXcQ", "9bZkp7q19f0", "kJQP7kiw5Fk"])
auditor.collect_play_next(collect_video_num=10)
print(json.dumps(auditor.report(), indent=2))
```

```json
{
  "training_ids": ["dQw4w9WgXcQ", "9bZkp7q19f0"],
  "seed_id": "kJQP7kiw5Fk",
  "player_mode": "long",
  "max_duration": 10,
  "recommendations": {
    "autoplay_rec": [
      "https://www.youtube.com/watch?v=Jma4nCMpaQM",
      "https://www.youtube.com/watch?v=iNJG3xbw-2E",
      "https://www.youtube.com/watch?v=vj5FtwDgmSs",
      "https://www.youtube.com/watch?v=pU7culxnZT0",
      "https://www.youtube.com/watch?v=ZWuXzQ4D9u8",
      "https://www.youtube.com/watch?v=C-fexNlzMtQ",
      "https://www.youtube.com/watch?v=zdjo712qnyE",
      "https://www.youtube.com/watch?v=9aBG9yGcWSc",
      "https://www.youtube.com/watch?v=ga95aB7CAPs",
      "https://www.youtube.com/watch?v=dZuVOViXOq0"
    ],
    "sidebar_rec": [[], [], [], [], [], [], [], [], [], []],
    "preload_rec": [],
    "restricted": []
  }
}
```

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `browser_type` | `"Chrome"` | Browser to use (`Chrome`, `Firefox`, `Edge`, `Safari`) |
| `headless` | `True` | Run without a visible window |
| `incognito` | `False` | Use private browsing mode |
| `extension` | `False` | Load a Chrome extension (`.crx` file path, directory, or `True` to auto-detect) |
| `mode` | — | `"long"` for regular videos, `"short"` for YouTube Shorts |
| `max_duration` | `10` | Seconds to watch each video (int), or fraction of length (float 0–1) |

## Collected data

`report()` returns a dictionary with all data collected during a run:

| Field | Description |
|-------|-------------|
| `training_ids` | Videos watched before the seed to build the profile |
| `seed_id` | The final seed video that triggers recommendation collection |
| `autoplay_rec` | Ordered URLs visited by following autoplay |
| `sidebar_rec` | Sidebar recommendations at each long-form hop |
| `preload_rec` | Preloaded next videos at each Shorts hop |
| `restricted` | Age-restricted videos encountered, with reason string |

<!-- 
## Design Process
This section documents major design decisions as the system evolved from a research prototype into a reusable tool.

### Package Modularization (Feb. 9th)
The initial system was designed for one-off research runs. As experiments scaled, the main challenge became orchestration and visibility: understanding what was running, what failed, and why.


> *AI Collaboration:*\
> LLMs were used to explore alternative package structures and UI patterns. All architectural decisions and tradeoffs were evaluated and finalized manually.
 -->
