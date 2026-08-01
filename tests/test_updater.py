from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from openhalo.release_manager import ReleaseLayout
from openhalo.release_manager import ReleaseManifest
from openhalo.updater import ReleaseUpdater


class _Feed:
    def __init__(self, manifest: ReleaseManifest) -> None:
        self.manifest = manifest

    def latest(self) -> ReleaseManifest:
        return self.manifest


class _Stager:
    def __init__(self, candidate: Path) -> None:
        self.candidate = candidate
        self.calls = 0

    def stage(self, manifest: ReleaseManifest) -> Path:
        self.calls += 1
        return self.candidate


class _Supervisor:
    def __init__(self, executable: Path | None, calls: list[str]) -> None:
        self.executable = executable
        self.calls = calls

    def status(self) -> dict:
        return {"state": "running", "pid": 123}

    def stop(self) -> dict:
        self.calls.append(f"stop:{self._label()}")
        return {"state": "stopping", "pid": 123}

    def wait_until_stopped(self) -> None:
        self.calls.append(f"wait:{self._label()}")

    def start(self) -> dict:
        self.calls.append(f"start:{self._label()}")
        if self.executable is not None and self.executable.parent.parent.parent.name == "b" * 40:
            raise RuntimeError("candidate did not become ready")
        return {"state": "running", "pid": 456}

    def _label(self) -> str:
        if self.executable is None:
            return "current"
        return self.executable.parent.parent.parent.name


def test_failed_candidate_start_restores_previous_release_and_runtime() -> None:
    with TemporaryDirectory() as directory:
        layout = ReleaseLayout(Path(directory) / "release-home")
        current = "a" * 40
        candidate = "b" * 40
        for commit in (current, candidate):
            python = layout.release_directory(commit) / "venv/bin/python"
            python.parent.mkdir(parents=True)
            python.touch()
        layout.activate(current)
        manifest = ReleaseManifest(
            version="0.22.0",
            tag="v0.22.0",
            commit=candidate,
            archive_name="openhalo-v0.22.0.tar.gz",
            archive_url="https://example.test/openhalo-v0.22.0.tar.gz",
            sha256="c" * 64,
        )
        calls: list[str] = []

        def supervisor_factory(executable: Path | None) -> _Supervisor:
            return _Supervisor(executable, calls)

        result = ReleaseUpdater(
            layout=layout,
            feed=_Feed(manifest),
            stager=_Stager(layout.release_directory(candidate)),
            supervisor_factory=supervisor_factory,
        ).update()

        assert result == {
            "state": "rolled_back",
            "restored": current,
            "target": candidate,
        }
        assert layout.active_release() == current
        assert calls == [
            "stop:current",
            "wait:current",
            f"start:{candidate}",
            f"stop:{candidate}",
            f"wait:{candidate}",
            f"start:{current}",
        ]


def test_update_continues_release_recovery_when_state_rollback_fails() -> None:
    with TemporaryDirectory() as directory:
        layout = ReleaseLayout(Path(directory) / "release-home")
        current = "a" * 40
        candidate = "b" * 40
        for commit in (current, candidate):
            python = layout.release_directory(commit) / "venv/bin/python"
            python.parent.mkdir(parents=True)
            python.touch()
        layout.activate(current)
        calls: list[str] = []

        def fail_state_rollback() -> None:
            raise RuntimeError("state rollback failed")

        result = ReleaseUpdater(
            layout=layout,
            feed=_Feed(
                ReleaseManifest(
                    version="0.1.8",
                    tag="v0.1.8",
                    commit=candidate,
                    archive_name="openhalo-v0.1.8.tar.gz",
                    archive_url="https://example.test/openhalo-v0.1.8.tar.gz",
                    sha256="c" * 64,
                )
            ),
            stager=_Stager(layout.release_directory(candidate)),
            supervisor_factory=lambda executable: _Supervisor(executable, calls),
            state_rollback_migrator=fail_state_rollback,
        ).update()

        assert result["state"] == "rolled_back"
        assert result["recovery_errors"] == ["state rollback failed"]
        assert layout.active_release() == current
        assert calls == [
            "stop:current",
            "wait:current",
            f"start:{candidate}",
            f"stop:{candidate}",
            f"wait:{candidate}",
            f"start:{current}",
        ]


def test_state_migration_runs_before_candidate_activation_and_start() -> None:
    with TemporaryDirectory() as directory:
        layout = ReleaseLayout(Path(directory) / "release-home")
        current = "a" * 40
        candidate = "b" * 40
        for commit in (current, candidate):
            python = layout.release_directory(commit) / "venv/bin/python"
            python.parent.mkdir(parents=True)
            python.touch()
        layout.activate(current)
        calls: list[str] = []

        def migration(manifest: ReleaseManifest) -> None:
            calls.append(f"migrate:{manifest.commit}")

        def commit_migration(manifest: ReleaseManifest) -> None:
            calls.append(f"commit:{manifest.commit}")

        class OrderedSupervisor(_Supervisor):
            def stop(self) -> dict:
                calls.append("stop")
                return {"state": "stopping", "pid": 123}

            def wait_until_stopped(self) -> None:
                calls.append("wait")

            def start(self) -> dict:
                calls.append(f"start:{self._label()}")
                return {"state": "running", "pid": 456}

        manifest = ReleaseManifest(
            version="0.1.9",
            tag="v0.1.9",
            commit=candidate,
            archive_name="openhalo-v0.1.9.tar.gz",
            archive_url="https://example.test/openhalo-v0.1.9.tar.gz",
            sha256="c" * 64,
            state_schema="sqlite-v1",
        )

        result = ReleaseUpdater(
            layout=layout,
            feed=_Feed(manifest),
            stager=_Stager(layout.release_directory(candidate)),
            supervisor_factory=lambda executable: OrderedSupervisor(executable, calls),
            state_migrator=migration,
            state_commit_migrator=commit_migration,
        ).update()

        assert result["state"] == "updated"
        assert calls[:5] == [
            "stop",
            "wait",
            f"migrate:{candidate}",
            f"start:{candidate}",
            f"commit:{candidate}",
        ]


def test_update_refuses_to_turn_a_development_command_into_an_installer() -> None:
    with TemporaryDirectory() as directory:
        layout = ReleaseLayout(Path(directory) / "release-home")
        manifest = ReleaseManifest(
            version="0.22.0",
            tag="v0.22.0",
            commit="b" * 40,
            archive_name="openhalo-v0.22.0.tar.gz",
            archive_url="https://example.test/openhalo-v0.22.0.tar.gz",
            sha256="c" * 64,
        )
        stager = _Stager(layout.release_directory(manifest.commit))

        with pytest.raises(ValueError, match="installed immutable release"):
            ReleaseUpdater(
                layout=layout,
                feed=_Feed(manifest),
                stager=stager,
                supervisor_factory=lambda executable: _Supervisor(executable, []),
            ).update()

        assert stager.calls == 0


def test_failed_manual_rollback_restores_the_previously_running_release() -> None:
    with TemporaryDirectory() as directory:
        layout = ReleaseLayout(Path(directory) / "release-home")
        current = "a" * 40
        previous = "b" * 40
        for commit in (current, previous):
            python = layout.release_directory(commit) / "venv/bin/python"
            python.parent.mkdir(parents=True)
            python.touch()
        layout.activate(previous)
        layout.activate(current)
        calls: list[str] = []

        class RollbackSupervisor(_Supervisor):
            def start(self) -> dict:
                self.calls.append(f"start:{self._label()}")
                if self.executable is not None and self._label() == previous:
                    raise RuntimeError("previous release did not become ready")
                return {"state": "running", "pid": 456}

        with pytest.raises(RuntimeError, match="previous release did not become ready"):
            ReleaseUpdater(
                layout=layout,
                feed=_Feed(
                    ReleaseManifest(
                        version="unused",
                        tag="v0.22.0",
                        commit="c" * 40,
                        archive_name="unused.tar.gz",
                        archive_url="https://example.test/unused.tar.gz",
                        sha256="d" * 64,
                    )
                ),
                stager=_Stager(layout.release_directory("c" * 40)),
                supervisor_factory=lambda executable: RollbackSupervisor(executable, calls),
            ).rollback()

        assert layout.active_release() == current
        assert calls == [
            "stop:current",
            "wait:current",
            f"start:{previous}",
            f"stop:{previous}",
            f"wait:{previous}",
            f"start:{current}",
        ]


def test_failed_manual_rollback_link_switch_restarts_the_original_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TemporaryDirectory() as directory:
        layout = ReleaseLayout(Path(directory) / "release-home")
        current = "a" * 40
        previous = "b" * 40
        for commit in (current, previous):
            python = layout.release_directory(commit) / "venv/bin/python"
            python.parent.mkdir(parents=True)
            python.touch()
        layout.activate(previous)
        layout.activate(current)
        original_switch = layout._switch_link
        switch_calls = 0

        def fail_once(link: Path, target: Path) -> None:
            nonlocal switch_calls
            switch_calls += 1
            if switch_calls == 2:
                raise OSError("link switch failed")
            original_switch(link, target)

        monkeypatch.setattr(layout, "_switch_link", fail_once)
        calls: list[str] = []

        with pytest.raises(OSError, match="link switch failed"):
            ReleaseUpdater(
                layout=layout,
                feed=_Feed(
                    ReleaseManifest(
                        version="unused",
                        tag="v0.22.0",
                        commit="c" * 40,
                        archive_name="unused.tar.gz",
                        archive_url="https://example.test/unused.tar.gz",
                        sha256="d" * 64,
                    )
                ),
                stager=_Stager(layout.release_directory("c" * 40)),
                supervisor_factory=lambda executable: _Supervisor(executable, calls),
            ).rollback()

        assert layout.active_release() == current
        assert calls == ["stop:current", "wait:current", f"start:{current}"]


def test_manual_rollback_keeps_the_target_release_selected_when_it_cannot_stop() -> None:
    with TemporaryDirectory() as directory:
        layout = ReleaseLayout(Path(directory) / "release-home")
        current = "a" * 40
        target = "b" * 40
        for commit in (current, target):
            python = layout.release_directory(commit) / "venv/bin/python"
            python.parent.mkdir(parents=True)
            python.touch()
        layout.activate(target)
        layout.activate(current)
        calls: list[str] = []

        class StuckTargetSupervisor(_Supervisor):
            def start(self) -> dict:
                self.calls.append(f"start:{self._label()}")
                if self.executable is not None and self._label() == target:
                    raise RuntimeError("target did not become ready")
                return {"state": "running", "pid": 456}

            def wait_until_stopped(self) -> None:
                self.calls.append(f"wait:{self._label()}")
                if self.executable is not None and self._label() == target:
                    raise RuntimeError("target did not stop")

        with pytest.raises(RuntimeError, match="target did not stop"):
            ReleaseUpdater(
                layout=layout,
                feed=_Feed(
                    ReleaseManifest(
                        version="unused",
                        tag="v0.22.0",
                        commit="c" * 40,
                        archive_name="unused.tar.gz",
                        archive_url="https://example.test/unused.tar.gz",
                        sha256="d" * 64,
                    )
                ),
                stager=_Stager(layout.release_directory("c" * 40)),
                supervisor_factory=lambda executable: StuckTargetSupervisor(executable, calls),
            ).rollback()

        assert layout.active_release() == target
        assert calls == [
            "stop:current",
            "wait:current",
            f"start:{target}",
            f"stop:{target}",
            f"wait:{target}",
        ]
