"""探针：长连续 filename 是否真正任意字符换行、高度是否覆盖全文（视觉 QA 复验）。"""

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="wrap-probe-appdata-")

REPO_ROOT = next(
    parent for parent in Path(__file__).resolve().parents
    if (parent / "duplicate_scan_core.py").is_file()
)
sys.path.insert(0, str(REPO_ROOT))

from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QWidget

import media_thumbnail as mt

app = QApplication(sys.argv)

if "--capture" in sys.argv:
    fid = QFontDatabase.addApplicationFont(r"C:\Windows\Fonts\msyh.ttc")
    families = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
    print("loaded font", fid, families)
    if families:
        app.setFont(QFont(families[0], 9))

LONG = Path(
    "C:/Users/someone/OneDrive - Contoso/Pictures/2026/11/HEIC_UM/IMG_20261121_1234567890_"
    + "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789" * 2
    + ".HEIC"
)

host = QWidget()
layout = QHBoxLayout(host)
layout.setContentsMargins(0, 0, 0, 0)
panel = mt.PreviewPanel(slots=2, size=256)
layout.addWidget(panel)
host.resize(820, 560)
host.show()
panel.set_slot(0, "A", LONG, 12_345_678, 1_700_000_000_000_000_000)
panel.set_slot(1, "B", LONG.with_suffix(".MOV"), 12_345_678, 1_700_000_000_000_000_000)
for _ in range(3):
    app.processEvents()

for index, slot in enumerate(panel._slot_widgets):
    label = slot.path_label
    doc = label._doc
    lines = max(1, round(doc.size().height() / max(1, label.fontMetrics().lineSpacing())))
    print(
        f"slot{index}",
        "width=", label.width(),
        "height=", label.height(),
        "needed=", label.needed_height(),
        "lines=", lines,
        "minimum=", label.minimumSizeHint().width(),
        "meta_height=", slot.meta_label.height(),
        "meta_needed=", slot.meta_label.needed_height(),
        "slot_h=", slot.height(),
    )

print("host height", host.height(), "panel height", panel.height())
if "--capture" in sys.argv:
    out = Path(sys.argv[sys.argv.index("--capture") + 1])
    img = host.grab()
    img.save(str(out))
    print("saved", out)

panel.shutdown()
print("ok")
