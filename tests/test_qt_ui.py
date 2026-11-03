import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication
from qt_app.main import VoxoraWindow


def test_qt_shell_constructs_with_all_primary_pages_and_controls():
    app = QApplication.instance() or QApplication([])
    window = VoxoraWindow()
    assert window.tabs.count() == 4
    assert len(window.sliders) == 16
    assert set(window.sliders) == {item[0] for item in window.CONTROL_SPEC}
    assert window.player is not None
    assert window.media_recorder is not None
    window.close()
