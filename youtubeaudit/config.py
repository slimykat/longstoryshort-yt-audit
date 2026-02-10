"""Configuration management for YouTube audit experiments."""

from dataclasses import dataclass, field
from typing import Literal, Optional
import yaml
import json
from pathlib import Path


@dataclass
class ExperimentTask:
    """Configuration for a single audit task (one video or pair of videos).

    Attributes
    ----------
    video_ids : list[str]
        List of video IDs to use as training seeds (will watch all in sequence)
    mode : Literal["long", "short"]
        Video player mode - "long" for regular videos, "short" for YouTube Shorts
    seed_id : Optional[str]
        The final seed video ID (last one in training sequence) for identification
    """
    video_ids: list[str]
    mode: Literal["long", "short"]
    seed_id: Optional[str] = None

    def __post_init__(self):
        if self.seed_id is None and self.video_ids:
            self.seed_id = self.video_ids[-1]


@dataclass
class ExperimentConfig:
    """Configuration for a batch YouTube audit experiment.

    Attributes
    ----------
    name : str
        Unique identifier for this experiment
    tasks : list[ExperimentTask]
        List of tasks to execute (can be single mode or paired long+short)
    watch_time : int | float
        Time to watch each video (int=seconds, float=percentage of video length)
    hops : int
        Number of recommendation hops to collect per task
    threads : int
        Number of parallel threads for batch processing
    sleep_range : tuple[int, int]
        Random sleep time range (min, max) in seconds between task batches
    headless : bool
        Run browser in headless mode
    adblock : bool | str
        Enable ad blocker (True for default, or path to extension)
    incognito : bool
        Run browser in incognito mode
    output_dir : str
        Directory to store experiment results
    """
    name: str
    tasks: list[ExperimentTask]
    watch_time: int | float = 10
    hops: int = 15
    threads: int = 2
    sleep_range: tuple[int, int] = (300, 900)
    headless: bool = True
    adblock: bool | str = False
    incognito: bool = False
    output_dir: str = "experiments"

    @classmethod
    def from_yaml(cls, path: str) -> "ExperimentConfig":
        """Load configuration from YAML file.

        Parameters
        ----------
        path : str
            Path to YAML configuration file

        Returns
        -------
        ExperimentConfig
            Parsed configuration object
        """
        with open(path, 'r') as f:
            data = yaml.safe_load(f)

        # Parse tasks
        tasks = []
        for task_data in data.get('tasks', []):
            if isinstance(task_data, dict):
                tasks.append(ExperimentTask(**task_data))
            elif isinstance(task_data, list):
                # Handle legacy format: [[{short:id, long:id}, ...]]
                for item in task_data:
                    if 'long' in item:
                        tasks.append(ExperimentTask(
                            video_ids=[item['long']],
                            mode='long'
                        ))
                    if 'short' in item:
                        tasks.append(ExperimentTask(
                            video_ids=[item['short']],
                            mode='short'
                        ))

        data['tasks'] = tasks
        return cls(**data)

    @classmethod
    def from_json(cls, path: str, mode: Literal["paired", "long", "short"] = "paired") -> "ExperimentConfig":
        """Load configuration from JSON file (legacy format support).

        Parameters
        ----------
        path : str
            Path to JSON file with video pairs
        mode : Literal["paired", "long", "short"]
            Execution mode:
            - "paired": run both long and short for each pair
            - "long": only run long-form videos
            - "short": only run short-form videos

        Returns
        -------
        ExperimentConfig
            Generated configuration from JSON pairs
        """
        with open(path, 'r') as f:
            pairs = json.load(f)

        tasks = []
        for pair_group in pairs:
            for item in pair_group:
                if mode in ["paired", "long"] and 'long' in item:
                    video_id = item['long'].split('/')[-1]
                    tasks.append(ExperimentTask(
                        video_ids=[video_id],
                        mode='long'
                    ))
                if mode in ["paired", "short"] and 'short' in item:
                    video_id = item['short'].split('/')[-1]
                    tasks.append(ExperimentTask(
                        video_ids=[video_id],
                        mode='short'
                    ))

        # Extract name from path
        name = Path(path).stem

        return cls(
            name=name,
            tasks=tasks
        )

    def to_yaml(self, path: str):
        """Save configuration to YAML file.

        Parameters
        ----------
        path : str
            Output path for YAML file
        """
        data = {
            'name': self.name,
            'watch_time': self.watch_time,
            'hops': self.hops,
            'threads': self.threads,
            'sleep_range': list(self.sleep_range),
            'headless': self.headless,
            'adblock': self.adblock,
            'incognito': self.incognito,
            'output_dir': self.output_dir,
            'tasks': [
                {
                    'video_ids': task.video_ids,
                    'mode': task.mode,
                    'seed_id': task.seed_id
                }
                for task in self.tasks
            ]
        }

        with open(path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False)

    def get_experiment_dir(self) -> Path:
        """Get the directory path for this experiment.

        Returns
        -------
        Path
            Directory path where experiment data will be stored
        """
        return Path(self.output_dir) / self.name

    def create_experiment_dir(self):
        """Create the experiment directory structure."""
        exp_dir = self.get_experiment_dir()
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "results").mkdir(exist_ok=True)
        (exp_dir / "logs").mkdir(exist_ok=True)
