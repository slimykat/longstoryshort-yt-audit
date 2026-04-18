# YouTube Auditor 
A auditing tool for running and monitoring recommendation experiments across video formats. Originally built to support the [paper](https://kumarde.com/papers/longstoryshort.pdf): "Long Story Short: Auditing U.S. Political Polarization in Recommendations for Long- vs. Short-form Videos on YouTube

This tool is trying to automate simulating user's behavior when browsing on both YouTube and YouTube Shorts -- specifically the "swiping" pattern where the user simply consumes, or partically consumes, what was recommended by the recommendation system one after another. 

This tool is developed and tested with Chrome Browser. Other browsers may be supported but without guanrantee functionality.


## Installation

**Requirements:** Python ≥ 3.10, Selenium ≥ 4.11.0

```bash
git clone https://github.com/slimykat/longstoryshort-yt-audit.git
cd longstoryshort-yt-audit
# # if using python virtual environment (suggested)
# source .venv/bin/activate 
pip install -e .
```

ChromeDriver is managed automatically by Selenium Manager (above version 4.11) — no separate download needed.

## Usage

The simuation process starts from playing a series of pre-determined videos(seed videos in short) to build up the user profile. Then, after the last seed video was played, we collected the queued videos serveral times by pressing the play next button. In the traditional long-form YouTube player, we use the keybind **shift** plus **n**, and in the YouTube Shorts, the **down arrow key**.

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

See [`examples/demo.ipynb`](examples/demo.ipynb) for a full walkthrough with annotated outputs for both long-form and Shorts modes.

### Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `browser_type` | `"Chrome"` | Browser to use (`Chrome`, `Firefox`, `Edge`, `Safari`) |
| `headless` | `True` | Run without a visible window |
| `incognito` | `False` | Use private browsing mode |
| `adblock` | `False` | Load an ad-blocker extension (`.crx` file path or `True` to auto-detect) |
| `mode` | — | `"long"` for regular videos, `"short"` for YouTube Shorts |
| `max_duration` | `10` | Seconds to watch each video (int), or fraction of length (float 0–1) |

## Collected data

`report()` returns a dictionary with all data collected during a run:

```json
{
  "training_ids": ["VIDEO_ID_1", "VIDEO_ID_2"],
  "seed_id": "VIDEO_ID_3",
  "player_mode": "long",
  "max_duration": 10,
  "recommendations": {
    "autoplay_rec": [
      "https://www.youtube.com/watch?v=..."
    ],
    "sidebar_rec": [
      ["https://www.youtube.com/watch?v=...", "..."]
    ],
    "preload_rec": [],
    "restricted": []
  }
}
```

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