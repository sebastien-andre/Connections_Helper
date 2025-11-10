"""
gui.py

PyQt6 GUI for the Connections Helper application.

This module wires together:
- the database abstraction (database.py),
- the CSV importer (importer.py),
- the Safari opener (safari.py),

into a single, usable desktop app

Some nice features I wanted:
- main view: alphabetized list of everyone
- left panel: multi-select companies (only companies with >= 3 people)
- fuzzy company search
- persistent “connection note” (saved in DB)
- open selected people in Safari, each in a tab, in a new window
- auto-mark visited after opening
- dark/light theme toggle
"""

import os
import pyperclip

from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QGroupBox,
    QPlainTextEdit,
    QLabel,
    QFileDialog,
    QAbstractItemView,
    QDialog,
    QToolBar,
    QStatusBar,
    QMessageBox,
    QSpinBox,
)

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from rapidfuzz import process, fuzz
from database import Database, DB_FILE
from importer import import_csv
from safari import open_linkedin_tabs



class DuplicateDialog(QDialog):
    """Simple dialog to show which people were skipped as duplicates."""

    def __init__(self, duplicates, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Duplicates omitted")
        self.resize(400, 300)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Omitted {len(duplicates)} duplicate connections:"))
        box = QPlainTextEdit()
        box.setReadOnly(True)
        box.setPlainText("\n".join(duplicates))
        layout.addWidget(box)
        ok = QPushButton("OK")
        ok.clicked.connect(self.accept)
        layout.addWidget(ok)


class HelperGUI(QMainWindow):
    """
    Main PyQt6 window for the Connections Helper.

    Purpose:
    - build the layout (left company list, central table, right actions)
    - connect UI events to DB + importer + Safari
    - keep status bar up to date
    - keep note text persistent
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Connections Helper")
        self.resize(1200, 700)

        # DB backend
        self.db = Database()

        # build UI widgets
        self._init_ui()

        # restore saved zoom level 
        font_size = int(self.db.get_setting("ui_font_size") or 10)
        font = self.font()
        font.setPointSize(font_size)
        self.setFont(font)
        for w in [self.table, self.company_list, self.note_box, self.status, self.threshold_spin]:
            w.setFont(font)

        # Restore saved theme preference
        theme = self.db.get_setting("theme") or "dark"
        if theme == "dark":
            self._apply_dark_theme()
            self.toggle_theme_action.setChecked(True)
        else:
            self._apply_light_theme()
            self.toggle_theme_action.setChecked(False)

        # restore saved note if present
        saved_note = self.db.get_setting("connection_note")
        if saved_note:
            self.note_box.setPlainText(saved_note)
            self._update_note_counter()

        # if DB empty, prompt to import
        if not self.db.get_all_people():
            self._import_csv_from_dialog()

        # load initial data
        self._refresh_companies()
        self._load_people()
        self._update_status()

        self.table.cellDoubleClicked.connect(self._open_single_linkedin)





    # UI construction

    def _init_ui(self):
        """Create all widgets and lay them out."""
        # toolbar
        toolbar = QToolBar()
        self.addToolBar(toolbar)

        import_action = QAction("Import CSV", self)
        import_action.triggered.connect(self._import_csv_from_dialog)
        toolbar.addAction(import_action)

        self.toggle_theme_action = QAction("Dark Mode", self, checkable=True)
        self.toggle_theme_action.triggered.connect(self._toggle_theme)
        toolbar.addAction(self.toggle_theme_action)

        toolbar.addSeparator()
        toolbar.addWidget(QLabel(" Min Employees: "))

        self.threshold_spin = QSpinBox()
        self.threshold_spin.setRange(1, 100)
        current_val = int(self.db.get_setting("employee_threshold") or 3)
        self.threshold_spin.setValue(current_val)
        self.threshold_spin.valueChanged.connect(self._on_threshold_changed)
        toolbar.addWidget(self.threshold_spin)

        self.show_unvisited_action = QAction("Show Unvisited Only", self, checkable=True)
        self.show_unvisited_action.triggered.connect(self._toggle_unvisited_view)
        toolbar.addAction(self.show_unvisited_action)


        QShortcut(QKeySequence("Meta+="), self, activated=lambda: self._adjust_zoom(1))   # Cmd + +
        QShortcut(QKeySequence("Meta+-"), self, activated=lambda: self._adjust_zoom(-1))  # Cmd + -

        # central widget
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)

        # LEFT column: search + companies
        left_col = QVBoxLayout()
        self.company_search = QLineEdit(placeholderText="Search companies...")
        self.company_search.textChanged.connect(self._filter_companies)
        left_col.addWidget(self.company_search)

        self.company_list = QListWidget()
        # allow multi select
        self.company_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.company_list.itemSelectionChanged.connect(self._on_company_selection_changed)
        left_col.addWidget(self.company_list)

        root_layout.addLayout(left_col, 2)

        # CENTER: table of people
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["ID", "✓", "First", "Last", "Position", "Email", "Company"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        root_layout.addWidget(self.table, 5)

        # RIGHT: actions + note
        right_col = QVBoxLayout()
        self.open_btn = QPushButton("Open LinkedIn")
        self.open_btn.clicked.connect(self._open_linkedin_for_selection)
        right_col.addWidget(self.open_btn)

        self.mark_btn = QPushButton("Mark Visited")
        self.mark_btn.clicked.connect(self._mark_selected_visited)
        right_col.addWidget(self.mark_btn)

        self.unvisit_btn = QPushButton("Unmark Visited")
        self.unvisit_btn.clicked.connect(self._unmark_selected)
        right_col.addWidget(self.unvisit_btn)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self._delete_selected)
        right_col.addWidget(self.delete_btn)

        # Reset database
        self.reset_btn = QPushButton("Reset Database")
        self.reset_btn.setStyleSheet("background-color:#b33a3a; color:white; font-weight:bold;")
        self.reset_btn.clicked.connect(self._reset_database)
        right_col.addWidget(self.reset_btn)

        right_col.addStretch()

        # note box group
        note_group = QGroupBox("Connection Note")
        note_layout = QVBoxLayout(note_group)
        self.note_box = QPlainTextEdit()
        self.note_box.textChanged.connect(self._on_note_changed)
        self.note_counter = QLabel("0/300", alignment=Qt.AlignmentFlag.AlignRight)
        note_layout.addWidget(self.note_box)
        note_layout.addWidget(self.note_counter)

        right_col.addWidget(note_group)

        root_layout.addLayout(right_col, 2)

        # status bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)


        # Allow selecting and copying text in note box
        self.note_box.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)

        # For table: allow selecting individual cells and copying text
        self.table.setTextElideMode(Qt.TextElideMode.ElideNone)  # show full text
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)


    # Theming


    def _apply_dark_theme(self):
        """Refined dark theme with soft blue accents to match the pastel light mode."""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
                color: #eaeaea;
            }

            /* Lists, inputs, tables */
            QListWidget, QTableWidget, QLineEdit, QPlainTextEdit {
                background-color: #2b2b2b;
                color: #f1f1f1;
                selection-background-color: #5b8ef1; /* bright blue accent */
                selection-color: #ffffff;
                alternate-background-color: #333333;
                border: 1px solid #3a3a3a;
            }

            /* Buttons */
            QPushButton {
                background-color: #3a3a3a;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 6px;
                padding: 6px 10px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
            QPushButton:pressed {
                background-color: #5b8ef1; /* same blue as selection */
                color: #ffffff;
            }

            /* Table headers */
            QHeaderView::section {
                background-color: #3c3c3c;
                color: #ffffff;
                padding: 4px;
                border: 1px solid #444444;
                font-weight: 500;
            }

            /* Toolbar */
            QToolBar {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2b2b2b, stop:1 #242424
                ); /* subtle gradient */
                border-bottom: 1px solid #444444;
            }
            QToolButton {
                background-color: #2b2b2b;
                color: #eeeeee;
                border: none;
                padding: 6px 10px;
            }
            QToolButton:hover {
                background-color: #3a3a3a;
            }
            QToolButton:checked {
                background-color: #5b8ef1; /* blue accent when active */
                color: #ffffff;
                border-radius: 4px;
            }

            /* Status bar */
            QStatusBar {
                background: #1a1a1a;
                color: #cccccc;
                border-top: 1px solid #333333;
            }
        """)




    def _apply_light_theme(self):
        """Pastel light theme with pink and blue accents."""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #fdfbff;
                color: #333333;
            }

            /* General input + list styling */
            QListWidget, QTableWidget, QLineEdit, QPlainTextEdit {
                background-color: #ffffff;
                color: #333333;
                selection-background-color: #a0b8ff; /* soft blue */
                selection-color: #000000;
                alternate-background-color: #f8f4ff; /* lavender tint */
                border: 1px solid #e2def5;
            }

            /* Buttons */
            QPushButton {
                background-color: #ffd5e5; /* pastel pink */
                color: #333333;
                border: 1px solid #f5bcd3;
                border-radius: 6px;
                padding: 6px 10px;
            }
            QPushButton:hover {
                background-color: #ffecf2; /* lighter hover pink */
            }

            /* Table headers */
            QHeaderView::section {
                background-color: #cde4ff; /* soft blue headers */
                color: #333333;
                padding: 4px;
                border: 1px solid #b0d2ff;
                font-weight: 500;
            }

            /* Toolbar — use same blue accent for visibility */
            QToolBar {
                background: #cde4ff; /* soft pastel blue */
                border-bottom: 1px solid #b0d2ff;
            }
            QToolButton {
                background-color: #cde4ff; /* match toolbar background */
                color: #1b1b1b;
                border: none;
                padding: 6px 10px;
            }
            QToolButton:hover {
                background-color: #b8d7ff; /* slightly deeper hover */
            }
            QToolButton:checked {
                background-color: #a0b8ff; /* soft blue active toggle */
                border-radius: 4px;
            }

            /* Status bar */
            QStatusBar {
                background: #f8f4ff;
                color: #333333;
                border-top: 1px solid #e2def5;
            }
        """)

    def _toggle_theme(self):
        """Toggle between light and dark mode."""
        if self.toggle_theme_action.isChecked():
            self._apply_dark_theme()
        else:
            self._apply_light_theme()

        # Remember last theme
        self.db.set_setting("theme", "dark" if self.toggle_theme_action.isChecked() else "light")

    
    # Data loading / refreshing
    def _refresh_companies(self):
        """Load companies (>=3 people) from DB into the list."""
        companies = self.db.companies()
        self._company_cache = companies  # store for filtering
        self.company_list.clear()
        for c in companies:
            # show counts too
            self.company_list.addItem(f"{c['name_original']} ({c['num']})")

    # def _load_people(self, company_ids=None):
    #     """
    #     Load people into the table.

    #     If company_ids is None, load everyone (alphabetized).
    #     Otherwise, load only those people whose company id is in company_ids.
    #     """
    #     if company_ids:
    #         people = self.db.get_people_filtered(company_ids)
    #     else:
    #         people = self.db.get_all_people()

    #     self.table.setRowCount(0)
    #     for row in people:
    #         r = self.table.rowCount()
    #         self.table.insertRow(r)
    #         self.table.setItem(r, 0, QTableWidgetItem(str(row["id"])))
    #         self.table.setItem(r, 1, QTableWidgetItem("✅" if row["visited"] else ""))
    #         self.table.setItem(r, 2, QTableWidgetItem(row["first_name"] or ""))
    #         self.table.setItem(r, 3, QTableWidgetItem(row["last_name"] or ""))
    #         self.table.setItem(r, 4, QTableWidgetItem(row["position_raw"] or ""))
    #         self.table.setItem(r, 5, QTableWidgetItem(row["email"] or ""))
    #         self.table.setItem(r, 6, QTableWidgetItem(row["company"] or ""))
    #     self.table.resizeRowsToContents()

    def _populate_table(self, rows):
        """Fill the main table widget with people data."""
        self.table.setRowCount(0)
        for r in rows:
            i = self.table.rowCount()
            self.table.insertRow(i)
            self.table.setItem(i, 0, QTableWidgetItem(str(r["id"])))
            self.table.setItem(i, 1, QTableWidgetItem("✅" if r["visited"] else ""))
            self.table.setItem(i, 2, QTableWidgetItem(r["first_name"] or ""))
            self.table.setItem(i, 3, QTableWidgetItem(r["last_name"] or ""))
            self.table.setItem(i, 4, QTableWidgetItem(r["position_raw"] or ""))
            self.table.setItem(i, 5, QTableWidgetItem(r["email"] or ""))
            self.table.setItem(i, 6, QTableWidgetItem(r["company"] or ""))
        self.table.resizeRowsToContents()

    def _load_people(self, company_ids=None):
        """Load all people or filter by selected companies."""
        if company_ids:
            rows = self.db.get_people_filtered(company_ids)
        else:
            rows = self.db.get_all_people()
        self._populate_table(rows)


    # CSV import

    def _import_csv_from_dialog(self):
        """Open a file dialog to import a CSV and refresh UI."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Connections CSV",
            os.path.expanduser("~"),
            "CSV Files (*.csv)"
        )
        if not path:
            return

        duplicates = import_csv(path, self.db)
        if duplicates:
            dlg = DuplicateDialog(duplicates, self)
            dlg.exec()

        self._refresh_companies()
        self._load_people()
        self._update_status()

    # Change employee min threshold

    def _on_threshold_changed(self, val: int):
        """Called when the min-employee spinbox changes."""
        self.db.set_setting("employee_threshold", str(val))
        self._refresh_companies()

    # Adjust zoom
    def _adjust_zoom(self, delta: int):
        """
        Increase or decrease the global font size by delta.
        delta = +1 for zoom in, -1 for zoom out.
        """
        app = self.window().windowHandle().screen().virtualSiblings()[0].virtualSiblings()
        # store zoom factor persistently
        current_zoom = int(self.db.get_setting("ui_font_size") or 10)
        new_size = max(8, min(24, current_zoom + delta))
        self.db.set_setting("ui_font_size", str(new_size))

        # Apply to QApplication font
        font = self.font()
        font.setPointSize(new_size)
        self.setFont(font)

        # Apply recursively to major widgets
        for w in [self.table, self.company_list, self.note_box, self.status, self.threshold_spin]:
            w.setFont(font)

        # optional: adjust row height proportionally
        self.table.verticalHeader().setDefaultSectionSize(new_size * 2)
        self.status.showMessage(f"Font size: {new_size} pt", 1500)


    # Search + filtering

    def _filter_companies(self):
        """Filter the company list using fuzzy search."""
        text = self.company_search.text().strip().lower()
        if not text:
            self._refresh_companies()
            return

        names = [c["name_original"] for c in self._company_cache]
        # get tuples: (name, score, idx)
        results = process.extract(
            text,
            names,
            scorer=fuzz.WRatio,
            limit=50
        )
        # sort highest score first
        results = sorted(results, key=lambda x: x[1], reverse=True)

        self.company_list.clear()
        for name, score, _ in results:
            # find the original company row
            comp = next((c for c in self._company_cache if c["name_original"] == name), None)
            if comp:
                self.company_list.addItem(f"{comp['name_original']} ({comp['num']})")

    def _on_company_selection_changed(self):
        """When user selects/deselects companies, refresh people list."""
        items = self.company_list.selectedItems()
        if not items:
            self._load_people()
            return

        selected_names = [i.text().split(" (")[0] for i in items]
        ids = [c["id"] for c in self._company_cache if c["name_original"] in selected_names]
        self._load_people(ids)


    def _toggle_unvisited_view(self):
        """Toggle between showing all people and only unvisited ones."""
        if self.show_unvisited_action.isChecked():
            self._load_unvisited()
        else:
            self._load_people()

    def _load_unvisited(self):
        """Load only unvisited people, optionally filtered by selected companies."""
        sels = [i.text().split(" (")[0] for i in self.company_list.selectedItems()]
        ids = [c["id"] for c in self._company_cache if c["name_original"] in sels]
        rows = self.db.get_unvisited_people(ids if ids else None)
        self._populate_table(rows)


    # Actions

    def _get_selected_ids(self):
        """Return a list of person IDs currently selected in the table."""
        ids = []
        for idx in self.table.selectionModel().selectedRows():
            item = self.table.item(idx.row(), 0)
            if item:
                ids.append(int(item.text()))
        return ids

    def _open_linkedin_for_selection(self):
        """
        Open the selected people in Safari.

        - Copies current note to clipboard
        - Opens a new Safari window with one tab per person
        - Auto-marks those people as visited
        """
        ids = self._get_selected_ids()
        if not ids:
            return

        # copy note
        note_text = self.note_box.toPlainText()
        pyperclip.copy(note_text)

        # fetch URLs for selected people
        placeholders = ",".join("?" * len(ids))
        q = f"SELECT url FROM people WHERE id IN ({placeholders})"
        urls = [r["url"] for r in self.db.conn.execute(q, ids).fetchall() if r["url"]]

        if urls:
            # open in Safari
            open_linkedin_tabs(urls)

        # auto-mark visited
        self.db.mark_visited(ids)
        self._on_company_selection_changed()  # refresh current view
        self._update_status()

    def _open_single_linkedin(self, row, column):
        """Open the LinkedIn URL for a single person when double-clicked."""
        person_id_item = self.table.item(row, 0)
        if not person_id_item:
            return

        pid = int(person_id_item.text())
        cur = self.db.conn.cursor()
        cur.execute("SELECT url FROM people WHERE id=?", (pid,))
        url_row = cur.fetchone()
        if not url_row or not url_row["url"]:
            return

        from safari import open_linkedin_tabs
        open_linkedin_tabs([url_row["url"]])

        # Mark visited automatically
        self.db.mark_visited([pid])
        self._on_company_selection_changed()
        self._update_status()

    def _mark_selected_visited(self):
        """Manually mark selected rows as visited."""
        ids = self._get_selected_ids()
        if not ids:
            return
        self.db.mark_visited(ids)
        self._on_company_selection_changed()
        self._update_status()


    def _unmark_selected(self):
        """Undo 'visited' status for selected rows."""
        ids = self._get_selected_ids()
        if not ids:
            return
        self.db.unmark_visited(ids)
        self._on_company_selection_changed()
        self._update_status()


    def _delete_selected(self):
        """Delete selected people after confirmation."""
        ids = self._get_selected_ids()
        if not ids:
            return

        res = QMessageBox.question(
            self,
            "Delete?",
            f"Delete {len(ids)} people?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if res == QMessageBox.StandardButton.Yes:
            self.db.delete_people(ids)
            self._on_company_selection_changed()
            self._refresh_companies()
            self._update_status()


    def _reset_database(self):
        """Completely delete all records and reset the database."""
        confirm = QMessageBox.warning(
            self,
            "⚠️ Confirm Reset",
            (
                "This will permanently delete ALL data, including companies, people, positions, and settings.\n\n"
                "Are you absolutely sure you want to reset the database?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            # Close and remove the DB file
            self.db.conn.close()
            import os
            from database import DB_FILE

            if os.path.exists(DB_FILE):
                os.remove(DB_FILE)

            # Reinitialize everything
            from database import Database
            self.db = Database()
            self._refresh_companies()
            self._load_people()
            self._update_status()

            QMessageBox.information(
                self,
                "Database Reset",
                "All data has been cleared. The database is now empty.",
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to reset database:\n{e}")

        finally:
            if not self.db.get_all_people():
                self._import_csv_from_dialog()



    # Note persistence

    def _on_note_changed(self):
        """Handle note changes: update counter + store in DB."""
        self._update_note_counter()
        self.db.set_setting("connection_note", self.note_box.toPlainText())

    def _update_note_counter(self):
        """Update the 'x/300' label and color."""
        text = self.note_box.toPlainText()
        length = len(text)
        self.note_counter.setText(f"{length}/300")
        if length > 300:
            self.note_counter.setStyleSheet("color:red;")
        else:
            self.note_counter.setStyleSheet("color:#ccc;")


    # Status bar

    def _update_status(self):
        """Update status bar with visited/total counts."""
        visited, total = self.db.visited_stats()
        self.status.showMessage(f"Visited {visited}/{total} connections")