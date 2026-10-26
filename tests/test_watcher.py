import pytest


def test_blip_does_not_count_as_power_off(watcher):
    t = watcher.PowerTracker(off_after=3)
    assert [t.update(r) for r in (False, False, True)] == [None, None, None]
    assert t.online


def test_off_after_consecutive_failures_then_on_again(watcher):
    t = watcher.PowerTracker(off_after=3)
    assert [t.update(False) for _ in range(3)] == [None, None, "off"]
    assert not t.online
    assert t.update(False) is None  # already off: no repeated event
    assert t.update(True) == "on"
    assert t.online


def test_failures_must_be_consecutive(watcher):
    t = watcher.PowerTracker(off_after=3)
    for r in (False, False, True, False, False):
        assert t.update(r) is None
    assert t.online


def test_first_round_after_power_on_may_replay_menu(watcher):
    assert watcher.methods_for(failed_rounds=0, adopted=False) == ["luna", "luna", "menu", "menu"]


def test_menu_never_used_on_retries_or_adopted_session(watcher):
    assert "menu" not in watcher.methods_for(failed_rounds=1, adopted=False)
    assert "menu" not in watcher.methods_for(failed_rounds=0, adopted=True)


def test_retry_delays_are_bounded(watcher):
    delays = [watcher.retry_delay(n) for n in range(1, 6)]
    assert delays == [120, 600, 1800, None, None]


@pytest.mark.parametrize("addr", ["", "aa:bb:cc:00:00:a9", "C4:38:75:1C:7D:AA".lower() + "x", "c4-38-75-1c-7d-a9"])
def test_validate_bt_rejects_unset_placeholder_and_malformed(watcher, addr):
    with pytest.raises(ValueError):
        watcher.validate_bt(addr)


def test_validate_bt_accepts_real_address(watcher):
    assert watcher.validate_bt("C4:38:75:1C:7D:A9") == "c4:38:75:1c:7d:a9"


def test_parse_keys(watcher):
    assert watcher.parse_keys("down, ENTER ,right") == ["DOWN", "ENTER", "RIGHT"]
    assert watcher.parse_keys("") == watcher.DEFAULT_MENU_KEYS
