from PySide6.QtCore import QByteArray, QDataStream, QIODevice
from PySide6.QtGui import QPainterPath

path = QPainterPath()
path.moveTo(0, 0)
path.cubicTo(10, 10, 20, -10, 30, 0)

ba = QByteArray()
stream = QDataStream(ba, QIODevice.OpenModeFlag.WriteOnly)
# try to write
try:
    stream << path
    print("operator<< works")
except Exception as e:
    print("operator<< failed:", e)

# try to read
try:
    stream2 = QDataStream(ba, QIODevice.OpenModeFlag.ReadOnly)
    path2 = QPainterPath()
    stream2 >> path2
    print("operator>> works! Element count:", path2.elementCount())
except Exception as e:
    print("operator>> failed:", e)
