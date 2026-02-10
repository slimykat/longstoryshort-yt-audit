"""State tracking for YouTube audit experiments."""

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Literal, Any
from dataclasses import dataclass, asdict


@dataclass
class TaskProgress:
    """Progress state for a single task (long or short video audit)."""
    video_id: str
    mode: Literal["long", "short"]
    phase: Literal["pending", "training", "collection", "complete", "failed"]
    training_progress: tuple[int, int]  # (current, total)
    collection_progress: tuple[int, int]  # (current, total)
    status: Literal["pending", "running", "complete", "failed"]
    error: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "video_id": self.video_id,
            "mode": self.mode,
            "phase": self.phase,
            "training_progress": {
                "current": self.training_progress[0],
                "total": self.training_progress[1]
            },
            "collection_progress": {
                "current": self.collection_progress[0],
                "total": self.collection_progress[1]
            },
            "status": self.status,
            "error": self.error
        }


class StatusTracker:
    """Thread-safe state tracker for batch experiments.

    This class manages the state file (status.json) for an experiment,
    providing atomic updates and thread-safe access.

    Attributes
    ----------
    experiment_id : str
        Unique identifier for the experiment
    experiment_dir : Path
        Directory containing experiment data
    """

    def __init__(self, experiment_id: str, experiment_dir: Path):
        """Initialize status tracker.

        Parameters
        ----------
        experiment_id : str
            Unique identifier for the experiment
        experiment_dir : Path
            Directory where experiment data is stored
        """
        self.experiment_id = experiment_id
        self.experiment_dir = Path(experiment_dir)
        self.status_file = self.experiment_dir / "status.json"
        self.lock = threading.Lock()

        # Ensure directory exists
        self.experiment_dir.mkdir(parents=True, exist_ok=True)

        # Initialize state
        self.state = {
            "experiment_id": experiment_id,
            "status": "pending",
            "started_at": None,
            "updated_at": self._timestamp(),
            "completed_at": None,
            "elapsed_seconds": 0,
            "batch_progress": {
                "total_tasks": 0,
                "completed_tasks": 0,
                "failed_tasks": 0,
                "current_task_index": -1
            },
            "current_tasks": {},
            "health": {
                "successful_runs": 0,
                "failed_runs": 0,
                "retries": 0,
                "restricted_videos": 0
            },
            "data_collected": {
                "total_recommendations": 0,
                "autoplay_paths": 0,
                "sidebar_recs": 0,
                "preload_recs": 0
            }
        }

    def _timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        return datetime.now(timezone.utc).isoformat()

    def _write(self):
        """Write state to file atomically."""
        with self.lock:
            self.state["updated_at"] = self._timestamp()

            # Calculate elapsed time
            if self.state["started_at"]:
                started = datetime.fromisoformat(self.state["started_at"])
                elapsed = (datetime.now(timezone.utc) - started).total_seconds()
                self.state["elapsed_seconds"] = int(elapsed)

            # Write atomically
            temp_file = self.status_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(self.state, f, indent=2)
            temp_file.replace(self.status_file)

    def start(self, total_tasks: int):
        """Mark experiment as started.

        Parameters
        ----------
        total_tasks : int
            Total number of tasks in the batch
        """
        with self.lock:
            self.state["status"] = "running"
            self.state["started_at"] = self._timestamp()
            self.state["batch_progress"]["total_tasks"] = total_tasks
        self._write()

    def complete(self):
        """Mark experiment as completed."""
        with self.lock:
            self.state["status"] = "completed"
            self.state["completed_at"] = self._timestamp()
        self._write()

    def fail(self, error: str):
        """Mark experiment as failed.

        Parameters
        ----------
        error : str
            Error message
        """
        with self.lock:
            self.state["status"] = "failed"
            self.state["error"] = error
            self.state["completed_at"] = self._timestamp()
        self._write()

    def update_current_task(self, task_index: int, task_id: str, tasks: dict[str, TaskProgress]):
        """Update the current task being processed.

        Parameters
        ----------
        task_index : int
            Index of current task in batch
        task_id : str
            Unique identifier for this task (e.g., "pair_023")
        tasks : dict[str, TaskProgress]
            Dictionary of sub-tasks (e.g., {"long": progress, "short": progress})
        """
        with self.lock:
            self.state["batch_progress"]["current_task_index"] = task_index
            self.state["current_tasks"] = {
                task_id: {
                    mode: progress.to_dict()
                    for mode, progress in tasks.items()
                }
            }
        self._write()

    def update_task_progress(
        self,
        task_id: str,
        mode: str,
        phase: str,
        current: int,
        total: int
    ):
        """Update progress for a specific sub-task.

        Parameters
        ----------
        task_id : str
            Unique identifier for the parent task
        mode : str
            Sub-task mode (e.g., "long" or "short")
        phase : str
            Current phase (training/collection)
        current : int
            Current progress count
        total : int
            Total count
        """
        with self.lock:
            if task_id in self.state["current_tasks"]:
                if mode in self.state["current_tasks"][task_id]:
                    self.state["current_tasks"][task_id][mode]["phase"] = phase
                    if phase == "training":
                        self.state["current_tasks"][task_id][mode]["training_progress"] = {
                            "current": current,
                            "total": total
                        }
                    elif phase == "collection":
                        self.state["current_tasks"][task_id][mode]["collection_progress"] = {
                            "current": current,
                            "total": total
                        }
        self._write()

    def increment_completed(self):
        """Increment completed task counter."""
        with self.lock:
            self.state["batch_progress"]["completed_tasks"] += 1
        self._write()

    def increment_failed(self):
        """Increment failed task counter."""
        with self.lock:
            self.state["batch_progress"]["failed_tasks"] += 1
        self._write()

    def increment_health(self, metric: str, amount: int = 1):
        """Increment a health metric.

        Parameters
        ----------
        metric : str
            Metric name (successful_runs, failed_runs, retries, restricted_videos)
        amount : int
            Amount to increment by
        """
        with self.lock:
            if metric in self.state["health"]:
                self.state["health"][metric] += amount
        self._write()

    def update_data_collected(self, **kwargs):
        """Update data collection counters.

        Parameters
        ----------
        **kwargs
            Metric names and values to update
        """
        with self.lock:
            for key, value in kwargs.items():
                if key in self.state["data_collected"]:
                    self.state["data_collected"][key] += value
        self._write()

    def get_state(self) -> dict:
        """Get current state.

        Returns
        -------
        dict
            Current state dictionary
        """
        with self.lock:
            return self.state.copy()

    def load_existing(self) -> bool:
        """Load existing state from file if available.

        Returns
        -------
        bool
            True if state was loaded, False if file doesn't exist
        """
        if self.status_file.exists():
            with self.lock:
                with open(self.status_file, 'r') as f:
                    self.state = json.load(f)
            return True
        return False
