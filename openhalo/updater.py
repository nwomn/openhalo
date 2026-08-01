"""Owner-facing immutable Runtime update orchestration."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from openhalo.release_manager import ReleaseLayout
from openhalo.release_manager import ReleaseManifest


class ReleaseFeed(Protocol):
    def latest(self) -> ReleaseManifest: ...


class ReleaseStaging(Protocol):
    def stage(self, manifest: ReleaseManifest) -> Path: ...


class RuntimeControl(Protocol):
    def start(self) -> dict: ...

    def status(self) -> dict: ...

    def stop(self) -> dict: ...

    def wait_until_stopped(self) -> dict: ...


class ReleaseUpdater:
    """Switch only program files and restore the prior running Runtime on failure."""

    def __init__(
        self,
        *,
        layout: ReleaseLayout,
        feed: ReleaseFeed,
        stager: ReleaseStaging,
        supervisor_factory: Callable[[Path | None], RuntimeControl],
        state_migrator: Callable[[ReleaseManifest], None] | None = None,
        state_rollback_migrator: Callable[[], None] | None = None,
    ) -> None:
        self.layout = layout
        self.feed = feed
        self.stager = stager
        self._supervisor_factory = supervisor_factory
        self._state_migrator = state_migrator
        self._state_rollback_migrator = state_rollback_migrator

    def check(self) -> dict:
        manifest = self.feed.latest()
        current = self.layout.active_release()
        return {
            "current": current,
            "state": "up_to_date" if current == manifest.commit else "update_available",
            "target": manifest.commit,
            "version": manifest.version,
        }

    def update(self) -> dict:
        manifest = self.feed.latest()
        current = self.layout.active_release()
        if current is None:
            raise ValueError(
                "OpenHalo update requires an installed immutable release; use scripts/install.sh first"
            )
        if current == manifest.commit:
            return {
                "current": current,
                "state": "up_to_date",
                "target": manifest.commit,
                "version": manifest.version,
            }

        candidate = self.stager.stage(manifest)
        supervisor = self._supervisor_factory(None)
        was_running = supervisor.status().get("state") == "running"
        if was_running:
            supervisor.stop()
            supervisor.wait_until_stopped()

        activated = False
        candidate_supervisor: RuntimeControl | None = None
        try:
            if self._state_migrator is not None:
                self._state_migrator(manifest)
            self.layout.activate(manifest.commit)
            activated = True
            if was_running:
                candidate_supervisor = self._supervisor_factory(candidate / "venv/bin/python")
                candidate_supervisor.start()
            return {
                "current": current,
                "state": "updated",
                "target": manifest.commit,
                "version": manifest.version,
            }
        except Exception:
            recovery_errors: list[str] = []
            if candidate_supervisor is not None:
                try:
                    candidate_supervisor.stop()
                    candidate_supervisor.wait_until_stopped()
                except Exception as exc:
                    recovery_errors.append(str(exc))
            if self._state_rollback_migrator is not None:
                try:
                    self._state_rollback_migrator()
                except Exception as exc:
                    recovery_errors.append(str(exc))
            if activated:
                try:
                    self.layout.rollback()
                except Exception as exc:
                    recovery_errors.append(str(exc))
            if was_running:
                try:
                    self._supervisor_factory(
                        self.layout.release_directory(current) / "venv/bin/python"
                    ).start()
                except Exception as exc:
                    recovery_errors.append(str(exc))
            result = {
                "state": "rolled_back",
                "restored": current,
                "target": manifest.commit,
            }
            if recovery_errors:
                result["recovery_errors"] = recovery_errors
            return result

    def rollback(self) -> dict:
        current = self.layout.active_release()
        previous = self.layout.previous_release()
        if current is None or previous is None:
            raise ValueError("no previous OpenHalo release is available")
        supervisor = self._supervisor_factory(None)
        was_running = supervisor.status().get("state") == "running"
        if was_running:
            supervisor.stop()
            supervisor.wait_until_stopped()
        switched = False
        target_supervisor: RuntimeControl | None = None
        try:
            if self._state_rollback_migrator is not None:
                self._state_rollback_migrator()
            restored = self.layout.rollback()
            switched = True
            if was_running:
                target_supervisor = self._supervisor_factory(
                    self.layout.release_directory(restored) / "venv/bin/python"
                )
                target_supervisor.start()
            return {"state": "rolled_back", "restored": restored, "replaced": current}
        except Exception:
            if target_supervisor is not None:
                target_supervisor.stop()
                target_supervisor.wait_until_stopped()
            if switched:
                self.layout.rollback()
            if was_running:
                self._supervisor_factory(
                    self.layout.release_directory(current) / "venv/bin/python"
                ).start()
            raise
