import io

import pytest
from PIL import Image, ImageDraw


@pytest.fixture
def popup_image():
    # Synthetic layout, no captured user content or device identifiers.
    image = Image.new('RGB', (960, 540), 'white')
    draw = ImageDraw.Draw(image)
    draw.rectangle((190, 350, 775, 455), fill=(203, 204, 206))
    draw.rectangle((630, 370, 745, 400), fill=(230, 230, 230))
    draw.rectangle((630, 415, 745, 440), fill=(125, 132, 140))
    return image


def test_recognizes_focused_popup_layout(watcher, popup_image):
    assert watcher.popup_match(popup_image)


def test_rejects_blank_and_wrong_focus(watcher, popup_image):
    assert not watcher.popup_match(Image.new('RGB', (960, 540), 'white'))
    ImageDraw.Draw(popup_image).rectangle((630, 370, 745, 400), fill=(125, 132, 140))
    assert not watcher.popup_match(popup_image)


def test_single_matching_pixels_are_not_enough(watcher):
    image = Image.new('RGB', (960, 540), 'white')
    for point, color in watcher.POPUP.items():
        image.putpixel(point, color)
    assert not watcher.popup_match(image)


def test_corrupt_screenshot_never_confirms(watcher, monkeypatch):
    monkeypatch.setattr(watcher, 'screenshot_bytes', lambda uri: b'not an image')
    monkeypatch.setattr(watcher, 'call', lambda *a: '{"payload":{"imageUri":"https://invalid/"}}')
    assert watcher.popup_state(None, 1) == 'UNKNOWN'


def test_valid_screenshot_confirms_focus(watcher, monkeypatch, popup_image):
    content = io.BytesIO()
    popup_image.save(content, format='PNG')
    monkeypatch.setattr(watcher, 'screenshot_bytes', lambda uri: content.getvalue())
    monkeypatch.setattr(watcher, 'call', lambda *a: '{"payload":{"imageUri":"https://invalid/"}}')
    assert watcher.popup_state(None, 1) == 'YES_FOCUSED'


def test_unknown_firmware_disables_menu(watcher, monkeypatch):
    monkeypatch.setattr(watcher, 'MENU_FALLBACK', True)
    monkeypatch.setattr(watcher, 'MENU_PROFILE', 'unknown')
    assert watcher.methods_for(0, False) == ['luna', 'luna']
