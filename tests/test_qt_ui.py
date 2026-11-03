import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('VOXORA_HEADLESS_TEST', '1')

from pathlib import Path
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication
from qt_app.main import VoxoraWindow


def make_window():
    app = QApplication.instance() or QApplication([])
    return app, VoxoraWindow()


def test_qt_shell_has_focused_pages_and_all_controls():
    app, window = make_window()
    assert window.tabs.count() == 5
    assert [window.tabs.tabText(i) for i in range(5)] == ['Studio', 'Voice controls', 'My voice', 'Library', 'Settings']
    assert len(window.sliders) == 16
    assert set(window.sliders) == {item[0] for item in window.CONTROL_SPEC}
    assert all(slider.minimum() == 0 and slider.maximum() == 100 for slider in window.sliders.values())
    assert window.player is None
    assert window.generate_btn.isEnabled()
    assert window.script_count.text() == f'{len(window.script.toPlainText()):,} characters'
    window.close()


def test_delivery_presets_update_the_same_model_parameters_as_gtk():
    app, window = make_window()
    expected = {0: (50, 0, 50), 1: (44, 25, 55), 2: (37, 15, 58), 3: (57, 35, 45), 4: (50, 65, 40)}
    for index, values in expected.items():
        window.preset.setCurrentIndex(index)
        actual = tuple(window.sliders[key].value() for key in ('speed', 'variation', 'voice_adherence'))
        assert actual == values
    window.close()


def test_script_selection_markup_wraps_only_selected_text():
    app, window = make_window()
    window.script.setPlainText('Hello important world')
    cursor = window.script.textCursor()
    cursor.setPosition(6)
    cursor.setPosition(15, QTextCursor.MoveMode.KeepAnchor)
    window.script.setTextCursor(cursor)
    window.wrap_selection_emphasis()
    assert window.script.toPlainText() == 'Hello [emphasis]important[/emphasis] world'
    window.close()


def test_reset_controls_restores_all_declared_defaults():
    app, window = make_window()
    for slider in window.sliders.values():
        slider.setValue(100)
    window.reset_controls()
    assert {key: slider.value() for key, slider in window.sliders.items()} == {key: default for key, _title, default, _hint in window.CONTROL_SPEC}
    window.close()


def test_gtk_remains_default_launcher_until_platform_gate_passes():
    root = Path(__file__).resolve().parents[1]
    assert 'native_app.py' in (root / 'run.sh').read_text()
    assert 'qt_app/main.py' in (root / 'run-qt.sh').read_text()
    gate = (root / 'docs/PLATFORM_SUPPORT.md').read_text()
    assert 'must not become the default' in gate
    assert 'Windows 11' in gate and 'macOS (Apple Silicon)' in gate
