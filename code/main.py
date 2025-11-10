"""
Launches the PyQt GUI and initializes the database backend.
"""

import sys
from PyQt6.QtWidgets import QApplication
from gui import HelperGUI


def main():
    app = QApplication(sys.argv)
    window = HelperGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()