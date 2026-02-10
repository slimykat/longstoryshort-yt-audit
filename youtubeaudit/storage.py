"""Pluggable storage backends for experiment results."""

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional


class StorageBackend(ABC):
    """Abstract base class for storage backends.

    Storage backends handle persisting experiment results to various destinations
    (files, databases, cloud services, etc.).
    """

    @abstractmethod
    def save_result(self, task_id: str, result: dict, metadata: Optional[dict] = None):
        """Save a single task result.

        Parameters
        ----------
        task_id : str
            Unique identifier for the task
        result : dict
            Task result data
        metadata : Optional[dict]
            Additional metadata (experiment name, timestamp, etc.)
        """
        pass

    @abstractmethod
    def load_result(self, task_id: str) -> Optional[dict]:
        """Load a single task result.

        Parameters
        ----------
        task_id : str
            Unique identifier for the task

        Returns
        -------
        Optional[dict]
            Task result data, or None if not found
        """
        pass

    @abstractmethod
    def list_results(self) -> list[str]:
        """List all available result IDs.

        Returns
        -------
        list[str]
            List of task IDs with saved results
        """
        pass


class FileStorage(StorageBackend):
    """File-based storage backend (default).

    Stores results as JSON files in the experiment directory.

    Attributes
    ----------
    results_dir : Path
        Directory where result files are stored
    """

    def __init__(self, experiment_dir: Path):
        """Initialize file storage.

        Parameters
        ----------
        experiment_dir : Path
            Base directory for experiment data
        """
        self.results_dir = Path(experiment_dir) / "results"
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def save_result(self, task_id: str, result: dict, metadata: Optional[dict] = None):
        """Save result to JSON file.

        Parameters
        ----------
        task_id : str
            Task identifier (used as filename)
        result : dict
            Result data
        metadata : Optional[dict]
            Additional metadata to include in file
        """
        output = {
            "task_id": task_id,
            "result": result
        }
        if metadata:
            output["metadata"] = metadata

        output_file = self.results_dir / f"{task_id}.json"
        with open(output_file, 'w') as f:
            json.dump(output, f, indent=2)

    def load_result(self, task_id: str) -> Optional[dict]:
        """Load result from JSON file.

        Parameters
        ----------
        task_id : str
            Task identifier

        Returns
        -------
        Optional[dict]
            Result data, or None if file doesn't exist
        """
        result_file = self.results_dir / f"{task_id}.json"
        if not result_file.exists():
            return None

        with open(result_file, 'r') as f:
            data = json.load(f)
        return data.get("result")

    def list_results(self) -> list[str]:
        """List all result files.

        Returns
        -------
        list[str]
            List of task IDs
        """
        return [f.stem for f in self.results_dir.glob("*.json")]


class CompositeStorage(StorageBackend):
    """Composite storage that writes to multiple backends.

    Useful for writing to both local files and a remote service (e.g., Firebase).

    Attributes
    ----------
    backends : list[StorageBackend]
        List of storage backends to write to
    """

    def __init__(self, backends: list[StorageBackend]):
        """Initialize composite storage.

        Parameters
        ----------
        backends : list[StorageBackend]
            List of storage backends
        """
        self.backends = backends

    def save_result(self, task_id: str, result: dict, metadata: Optional[dict] = None):
        """Save to all backends.

        Parameters
        ----------
        task_id : str
            Task identifier
        result : dict
            Result data
        metadata : Optional[dict]
            Additional metadata
        """
        for backend in self.backends:
            backend.save_result(task_id, result, metadata)

    def load_result(self, task_id: str) -> Optional[dict]:
        """Load from first available backend.

        Parameters
        ----------
        task_id : str
            Task identifier

        Returns
        -------
        Optional[dict]
            Result data from first backend that has it
        """
        for backend in self.backends:
            result = backend.load_result(task_id)
            if result is not None:
                return result
        return None

    def list_results(self) -> list[str]:
        """List results from first backend.

        Returns
        -------
        list[str]
            List of task IDs
        """
        if self.backends:
            return self.backends[0].list_results()
        return []


# Example Firebase storage backend (user can implement)
class FirebaseStorageExample(StorageBackend):
    """Example Firebase storage backend.

    Users can implement this by installing firebase-admin and adding credentials.
    This is a template showing the interface.
    """

    def __init__(self, experiment_name: str, credentials_path: Optional[str] = None):
        """Initialize Firebase storage.

        Parameters
        ----------
        experiment_name : str
            Experiment name for Firebase path
        credentials_path : Optional[str]
            Path to Firebase credentials JSON
        """
        self.experiment_name = experiment_name
        # User would initialize firebase_admin here:
        # import firebase_admin
        # from firebase_admin import credentials, db
        # cred = credentials.Certificate(credentials_path)
        # firebase_admin.initialize_app(cred, {'databaseURL': '...'})
        # self.db = db.reference(f'/experiments/{experiment_name}')

    def save_result(self, task_id: str, result: dict, metadata: Optional[dict] = None):
        """Save to Firebase Realtime Database.

        Parameters
        ----------
        task_id : str
            Task identifier
        result : dict
            Result data
        metadata : Optional[dict]
            Additional metadata
        """
        # User implementation:
        # self.db.child(task_id).set({
        #     'result': result,
        #     'metadata': metadata
        # })
        raise NotImplementedError(
            "Firebase storage requires firebase-admin package and credentials. "
            "See documentation for setup instructions."
        )

    def load_result(self, task_id: str) -> Optional[dict]:
        """Load from Firebase.

        Parameters
        ----------
        task_id : str
            Task identifier

        Returns
        -------
        Optional[dict]
            Result data
        """
        # User implementation:
        # data = self.db.child(task_id).get()
        # return data.get('result') if data else None
        raise NotImplementedError("Firebase storage not configured")

    def list_results(self) -> list[str]:
        """List all results from Firebase.

        Returns
        -------
        list[str]
            List of task IDs
        """
        # User implementation:
        # return list(self.db.get().keys()) if self.db.get() else []
        raise NotImplementedError("Firebase storage not configured")
