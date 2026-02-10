"""YouTube Audit Tool - Automated recommendation algorithm auditing.

This package provides tools for systematically auditing YouTube's recommendation
algorithm across long-form and short-form video formats.

Main Classes
------------
YouTubeAuditor : Core automation class
BatchRunner : Batch experiment orchestration
ExperimentConfig : Configuration management
StorageBackend : Result storage interface

Example
-------
from youtubeaudit import YouTubeAuditor, ExperimentConfig, BatchRunner

# Load config
config = ExperimentConfig.from_yaml('experiment.yaml')

# Run batch experiment
runner = BatchRunner(config)
runner.run()
"""

__version__ = "1.0.0"

from .core import YouTubeAuditor
from .batch import BatchRunner
from .config import ExperimentConfig, ExperimentTask
from .state import StatusTracker, TaskProgress
from .storage import StorageBackend, FileStorage, CompositeStorage

__all__ = [
    "YouTubeAuditor",
    "BatchRunner",
    "ExperimentConfig",
    "ExperimentTask",
    "StatusTracker",
    "TaskProgress",
    "StorageBackend",
    "FileStorage",
    "CompositeStorage",
]
