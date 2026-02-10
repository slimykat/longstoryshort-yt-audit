"""Batch processing for YouTube audit experiments."""

import time
import logging
from random import randint
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Callable
from pathlib import Path

from .core import YouTubeAuditor
from .config import ExperimentConfig, ExperimentTask
from .state import StatusTracker, TaskProgress
from .storage import StorageBackend, FileStorage


class BatchRunner:
    """Orchestrates batch YouTube audit experiments with multi-threading and retry logic.

    This class manages the execution of multiple audit tasks in parallel,
    tracks progress, handles retries, and saves results.

    Parameters
    ----------
    config : ExperimentConfig
        Experiment configuration
    storage : StorageBackend, optional
        Storage backend for results (default: FileStorage)
    on_event : Callable, optional
        Callback for experiment events
    max_retries : int, optional
        Maximum number of retries per task (default: 3)

    Attributes
    ----------
    config : ExperimentConfig
        Experiment configuration
    status : StatusTracker
        Status tracker for experiment state
    storage : StorageBackend
        Storage backend for results
    """

    def __init__(
        self,
        config: ExperimentConfig,
        storage: Optional[StorageBackend] = None,
        on_event: Optional[Callable[[dict], None]] = None,
        max_retries: int = 3,
    ):
        self.config = config
        self.max_retries = max_retries
        self.on_event = on_event or (lambda x: None)

        # Create experiment directory
        config.create_experiment_dir()
        exp_dir = config.get_experiment_dir()

        # Initialize status tracker
        self.status = StatusTracker(config.name, exp_dir)

        # Initialize storage backend
        if storage is None:
            storage = FileStorage(exp_dir)
        self.storage = storage

        # Set up logging
        log_file = exp_dir / "logs" / "experiment.log"
        logging.basicConfig(
            filename=str(log_file),
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )

    def _emit_event(self, event_type: str, **data):
        """Emit experiment event.

        Parameters
        ----------
        event_type : str
            Event type
        **data
            Event data
        """
        event = {
            "event": event_type,
            "experiment_id": self.config.name,
            "timestamp": time.time(),
            **data
        }
        self.on_event(event)

    def _execute_task(self, task_idx: int, task: ExperimentTask) -> Optional[dict]:
        """Execute a single audit task.

        Parameters
        ----------
        task_idx : int
            Index of task in batch
        task : ExperimentTask
            Task configuration

        Returns
        -------
        Optional[dict]
            Task result, or None if failed
        """
        task_id = f"task_{task_idx:04d}"
        self._emit_event("task_started", task_idx=task_idx, task_id=task_id, mode=task.mode)

        # Create progress callback
        def on_progress(event):
            # Update status tracker based on progress events
            if event["event"] == "training_progress":
                self.status.update_task_progress(
                    task_id,
                    task.mode,
                    "training",
                    event["current"],
                    event["total"]
                )
            elif event["event"] == "collection_progress":
                self.status.update_task_progress(
                    task_id,
                    task.mode,
                    "collection",
                    event["current"],
                    event["total"]
                )
            elif event["event"] == "restricted_video":
                self.status.increment_health("restricted_videos")

        # Initialize auditor
        auditor = YouTubeAuditor(
            adblock=self.config.adblock,
            incognito=self.config.incognito,
            headless=self.config.headless,
            verbose=logging.INFO,
            on_progress=on_progress,
        )

        # Initialize driver
        if auditor.InitDriver(task.mode, self.config.watch_time):
            logging.error(f"Failed to initialize driver for task {task_id}")
            self._emit_event("task_failed", task_idx=task_idx, error="driver_init_failed")
            return None

        # Update status
        task_progress = TaskProgress(
            video_id=task.seed_id or task.video_ids[-1],
            mode=task.mode,
            phase="pending",
            training_progress=(0, len(task.video_ids)),
            collection_progress=(0, self.config.hops),
            status="running"
        )
        self.status.update_current_task(task_idx, task_id, {task.mode: task_progress})

        try:
            # Training phase
            if auditor.Train(task.video_ids):
                logging.error(f"Training failed for task {task_id}")
                self.status.increment_failed()
                self.status.increment_health("failed_runs")
                auditor.CleanUp(kill=True)
                return None

            # Collection phase
            result_code = auditor.Run(self.config.hops, self.config.watch_time)
            if result_code == -1:
                logging.error(f"Collection failed for task {task_id}")
                self.status.increment_failed()
                self.status.increment_health("failed_runs")
                auditor.CleanUp(kill=True)
                return None

            # Generate report
            result = auditor.Report()

            # Update metrics
            self.status.increment_completed()
            self.status.increment_health("successful_runs")
            self.status.update_data_collected(
                autoplay_paths=len(result["recommendations"]["autoplay_rec"]),
                sidebar_recs=sum(len(s) for s in result["recommendations"]["sidebar_rec"]),
                preload_recs=sum(len(p) for p in result["recommendations"]["preload_rec"]),
            )

            self._emit_event("task_completed", task_idx=task_idx, task_id=task_id)

            return result

        except Exception as e:
            logging.error(f"Error in task {task_id}: {e}")
            self._emit_event("task_failed", task_idx=task_idx, error=str(e))
            self.status.increment_failed()
            self.status.increment_health("failed_runs")
            return None

        finally:
            auditor.CleanUp(kill=True)

    def _execute_task_with_retry(self, task_idx: int, task: ExperimentTask) -> Optional[dict]:
        """Execute task with retry logic.

        Parameters
        ----------
        task_idx : int
            Index of task in batch
        task : ExperimentTask
            Task configuration

        Returns
        -------
        Optional[dict]
            Task result, or None if all retries failed
        """
        for attempt in range(self.max_retries):
            if attempt > 0:
                self._emit_event("task_retry", task_idx=task_idx, attempt=attempt)
                self.status.increment_health("retries")
                logging.info(f"Retrying task {task_idx}, attempt {attempt + 1}/{self.max_retries}")

            result = self._execute_task(task_idx, task)
            if result is not None:
                return result

        logging.error(f"Task {task_idx} failed after {self.max_retries} attempts")
        return None

    def run(self):
        """Run the batch experiment.

        Executes all tasks with multi-threading, retry logic, and progress tracking.
        """
        total_tasks = len(self.config.tasks)
        self._emit_event("experiment_started", total_tasks=total_tasks)
        self.status.start(total_tasks)

        logging.info(f"Starting experiment {self.config.name} with {total_tasks} tasks")

        with ThreadPoolExecutor(max_workers=self.config.threads) as executor:
            # Group tasks by pairs if needed (for compatibility with original design)
            # For now, we'll process tasks sequentially in groups of config.threads
            for batch_start in range(0, total_tasks, self.config.threads):
                batch_end = min(batch_start + self.config.threads, total_tasks)
                batch_tasks = self.config.tasks[batch_start:batch_end]

                # Submit tasks to thread pool
                futures = {
                    executor.submit(self._execute_task_with_retry, batch_start + i, task): (batch_start + i, task)
                    for i, task in enumerate(batch_tasks)
                }

                # Wait for all tasks in this batch to complete
                results = []
                for future in as_completed(futures):
                    task_idx, task = futures[future]
                    try:
                        result = future.result()
                        results.append((task_idx, result))

                        # Save result
                        if result is not None:
                            task_id = f"task_{task_idx:04d}"
                            metadata = {
                                "experiment_id": self.config.name,
                                "task_index": task_idx,
                                "mode": task.mode,
                                "seed_ids": task.video_ids,
                            }
                            self.storage.save_result(task_id, result, metadata)
                            logging.info(f"Saved result for task {task_id}")

                    except Exception as e:
                        logging.error(f"Unexpected error in task {task_idx}: {e}")
                        self._emit_event("task_failed", task_idx=task_idx, error=str(e))

                # Sleep between batches (rate limiting)
                if batch_end < total_tasks:
                    sleep_time = randint(self.config.sleep_range[0], self.config.sleep_range[1])
                    logging.info(f"Sleeping for {sleep_time} seconds before next batch")
                    self._emit_event("batch_sleep", duration=sleep_time)
                    time.sleep(sleep_time)

        # Mark experiment as complete
        self.status.complete()
        self._emit_event("experiment_completed", total_tasks=total_tasks)
        logging.info(f"Experiment {self.config.name} completed")

    def get_results(self) -> list[dict]:
        """Get all experiment results.

        Returns
        -------
        list[dict]
            List of all task results
        """
        results = []
        for task_id in sorted(self.storage.list_results()):
            result = self.storage.load_result(task_id)
            if result:
                results.append(result)
        return results
