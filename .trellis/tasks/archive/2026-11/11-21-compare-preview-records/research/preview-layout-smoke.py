"""临时冒烟：预览槽等宽、长路径不撑开、图片等比缩放（不进仓库行为）。"""

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="preview-smoke-appdata-")

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QImage, QPixmap
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QVBoxLayout, QWidget

REPO_ROOT = next(
    parent for parent in Path(__file__).resolve().parents
    if (parent / "duplicate_scan_core.py").is_file()
)
sys.path.insert(0, str(REPO_ROOT))
import media_thumbnail as mt

app = QApplication(sys.argv)

LONG_DIR = "C:/Users/someone/OneDrive - Contoso/Pictures/2026/11/HEIC_UM"
LONG = Path(LONG_DIR + "/IMG_20261121_1234567890_" + "A" * 180 + ".HEIC")
LONG2 = Path(LONG_DIR + "/IMG_20261121_1234567890_" + "B" * 180 + ".MOV")

host = QWidget()
layout = QHBoxLayout(host)
layout.setContentsMargins(0, 0, 0, 0)
panel = mt.PreviewPanel(slots=2, size=256)
layout.addWidget(panel)
host.resize(820, 520)
host.show()
app.processEvents()

panel.set_slot(0, "A", LONG)
panel.set_slot(1, "B", LONG2)
app.processEvents()

print("panel minimumSizeHint", panel.minimumSizeHint().width())
print("panel sizeHint", panel.sizeHint().width())
print("slot widths", [slot.width() for slot in panel._slot_widgets])
print("slot min hints", [slot.minimumSizeHint().width() for slot in panel._slot_widgets])
print("path label min hints", [slot.path_label.minimumSizeHint().width() for slot in panel._slot_widgets])
print("image frames", [(slot.image_label.width(), slot.image_label.height()) for slot in panel._slot_widgets])

image = QImage(400, 200, QImage.Format.Format_RGB32)
image.fill(QColor("#336699"))
panel._slot_widgets[0].show_pixmap(QPixmap.fromImage(image))
app.processEvents()
shown = panel._slot_widgets[0].image_label.pixmap()
print("scaled pixmap", shown.width(), shown.height(), "ratio", round(shown.width() / shown.height(), 3))

# 缩窄看是否等比缩小且两槽仍等宽
host.resize(420, 520)
app.processEvents()
print("narrow slot widths", [slot.width() for slot in panel._slot_widgets])
print("narrow frames", [(slot.image_label.width(), slot.image_label.height()) for slot in panel._slot_widgets])
shown = panel._slot_widgets[0].image_label.pixmap()
print("narrow pixmap", shown.width(), shown.height())

panel.shutdown()
print("ok")
