"""Unit tests for the host-managed boot greeting."""
import time

import app.greeting as greeting_mod
from app.greeting import BootGreeter


class FakeController:
    def __init__(self):
        self.commands = []

    def send_command(self, command):
        self.commands.append(command)
        return command != "kup"  # kup no-ops report failure on hardware


def fast(monkeypatch):
    monkeypatch.setattr(greeting_mod, "SEQUENCE",
                        [(c, 0.0) for c, _ in greeting_mod.SEQUENCE])


def test_greeting_runs_full_sequence(monkeypatch):
    fast(monkeypatch)
    ctrl = FakeController()
    greeter = BootGreeter(ctrl)
    assert greeter.run() is True
    assert ctrl.commands[0] == "kup"
    assert "kstr" in ctrl.commands
    assert any(c.startswith("b ") for c in ctrl.commands)  # go jingle
    assert ctrl.commands[-1] == "kbalance"
    assert greeter.status()["runs"] == 1


def test_on_online_debounces(monkeypatch):
    fast(monkeypatch)
    ctrl = FakeController()
    greeter = BootGreeter(ctrl)
    greeter.on_online()
    first = len(ctrl.commands)
    greeter.on_online()  # within debounce window: no second run
    assert len(ctrl.commands) == first
    assert greeter.status()["runs"] == 1


def test_disabled_greeter_stays_silent(monkeypatch):
    fast(monkeypatch)
    ctrl = FakeController()
    greeter = BootGreeter(ctrl, enabled=False)
    greeter.on_online()
    assert ctrl.commands == []
