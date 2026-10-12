"""A small, local-first personal budget tracker built with PySide6."""

from __future__ import annotations

import sqlite3
import sys
from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)


APP_DIR = Path.home() / ".budget_tracker"
DB_PATH = APP_DIR / "budget.db"


class Database:
    def __init__(self) -> None:
        APP_DIR.mkdir(exist_ok=True)
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("""CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL CHECK(kind IN ('Income', 'Expense')),
            amount REAL NOT NULL CHECK(amount > 0),
            category TEXT NOT NULL,
            note TEXT,
            transaction_date TEXT NOT NULL
        )""")
        self.conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self.conn.commit()

    def budget(self) -> float:
        row = self.conn.execute("SELECT value FROM settings WHERE key = 'monthly_budget'").fetchone()
        return float(row["value"]) if row else 0.0

    def set_budget(self, value: float) -> None:
        self.conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES ('monthly_budget', ?)", (str(value),))
        self.conn.commit()

    def add(self, kind: str, amount: float, category: str, note: str, transaction_date: str) -> None:
        self.conn.execute("INSERT INTO transactions(kind, amount, category, note, transaction_date) VALUES (?, ?, ?, ?, ?)",
                          (kind, amount, category, note, transaction_date))
        self.conn.commit()

    def update(self, transaction_id: int, kind: str, amount: float, category: str, note: str, transaction_date: str) -> None:
        self.conn.execute("UPDATE transactions SET kind=?, amount=?, category=?, note=?, transaction_date=? WHERE id=?",
                          (kind, amount, category, note, transaction_date, transaction_id))
        self.conn.commit()

    def delete(self, transaction_id: int) -> None:
        self.conn.execute("DELETE FROM transactions WHERE id=?", (transaction_id,))
        self.conn.commit()

    def all(self):
        return self.conn.execute("SELECT * FROM transactions ORDER BY transaction_date DESC, id DESC").fetchall()

    def totals_this_month(self) -> tuple[float, float]:
        prefix = date.today().strftime("%Y-%m") + "%"
        row = self.conn.execute("""SELECT
            COALESCE(SUM(CASE WHEN kind='Income' THEN amount END), 0) income,
            COALESCE(SUM(CASE WHEN kind='Expense' THEN amount END), 0) expense
            FROM transactions WHERE transaction_date LIKE ?""", (prefix,)).fetchone()
        return float(row["income"]), float(row["expense"])


class TransactionDialog(QDialog):
    def __init__(self, parent=None, transaction=None):
        super().__init__(parent)
        self.setWindowTitle("Edit transaction" if transaction else "Add transaction")
        self.setMinimumWidth(360)
        form = QFormLayout(self)
        self.kind = QComboBox(); self.kind.addItems(["Expense", "Income"])
        self.amount = QDoubleSpinBox(); self.amount.setRange(0.01, 9_999_999); self.amount.setPrefix("$"); self.amount.setDecimals(2)
        self.category = QLineEdit(); self.category.setPlaceholderText("e.g. Groceries, Paycheck")
        self.note = QLineEdit(); self.note.setPlaceholderText("Optional")
        self.when = QDateEdit(); self.when.setCalendarPopup(True); self.when.setDate(QDate.currentDate())
        form.addRow("Type", self.kind); form.addRow("Amount", self.amount); form.addRow("Category", self.category)
        form.addRow("Note", self.note); form.addRow("Date", self.when)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); form.addRow(buttons)
        if transaction:
            self.kind.setCurrentText(transaction["kind"]); self.amount.setValue(transaction["amount"])
            self.category.setText(transaction["category"]); self.note.setText(transaction["note"] or "")
            self.when.setDate(QDate.fromString(transaction["transaction_date"], "yyyy-MM-dd"))

    def values(self):
        return (self.kind.currentText(), self.amount.value(), self.category.text().strip() or "Other",
                self.note.text().strip(), self.when.date().toString("yyyy-MM-dd"))


class BudgetWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = Database()
        self.setWindowTitle("Budget Tracker")
        self.resize(970, 660)
        self.setStyleSheet("""
            QWidget { font-family: Arial; font-size: 14px; color: #1f2937; }
            QMainWindow { background: #f6f7fb; }
            QFrame#card { background: white; border: 1px solid #e8eaf0; border-radius: 14px; }
            QLabel#title { font-size: 27px; font-weight: 700; color: #111827; }
            QLabel#amount { font-size: 24px; font-weight: 700; }
            QPushButton { background: #2563eb; color: white; font-weight: 600; border: 0; border-radius: 8px; padding: 10px 15px; }
            QPushButton:hover { background: #1d4ed8; } QPushButton#secondary { background: #e9edf8; color: #1e3a8a; }
            QTableWidget { background: white; border: 1px solid #e8eaf0; border-radius: 10px; gridline-color: #edf0f5; }
            QHeaderView::section { background: #f8fafc; border: 0; border-bottom: 1px solid #e8eaf0; padding: 9px; font-weight: 700; }
            QLineEdit, QSpinBox { background: white; border: 1px solid #d7dce5; border-radius: 7px; padding: 7px; }
        """)
        self.build_ui(); self.refresh()

    def card(self, label: str, color: str):
        box = QFrame(); box.setObjectName("card"); layout = QVBoxLayout(box); layout.setContentsMargins(18, 15, 18, 15)
        caption = QLabel(label); caption.setStyleSheet("color: #667085; font-weight: 600;")
        amount = QLabel("$0.00"); amount.setObjectName("amount"); amount.setStyleSheet(f"color: {color};")
        layout.addWidget(caption); layout.addWidget(amount); return box, amount

    def build_ui(self):
        central = QWidget(); self.setCentralWidget(central); layout = QVBoxLayout(central); layout.setContentsMargins(28, 24, 28, 28); layout.setSpacing(16)
        top = QHBoxLayout(); title = QLabel("Budget Tracker"); title.setObjectName("title")
        subtitle = QLabel("Keep an eye on this month’s money."); subtitle.setStyleSheet("color: #667085;")
        heading = QVBoxLayout(); heading.addWidget(title); heading.addWidget(subtitle); top.addLayout(heading); top.addStretch()
        add_button = QPushButton("+ Add transaction"); add_button.clicked.connect(self.add_transaction); top.addWidget(add_button); layout.addLayout(top)
        cards = QGridLayout(); self.income_card, self.income_amount = self.card("MONTHLY INCOME", "#059669")
        self.expense_card, self.expense_amount = self.card("MONTHLY EXPENSES", "#dc2626")
        self.net_card, self.net_amount = self.card("NET BALANCE", "#2563eb")
        cards.addWidget(self.income_card, 0, 0); cards.addWidget(self.expense_card, 0, 1); cards.addWidget(self.net_card, 0, 2); layout.addLayout(cards)
        budget_row = QHBoxLayout(); budget_label = QLabel("Monthly spending budget:"); budget_label.setStyleSheet("font-weight: 600;")
        self.budget_input = QSpinBox(); self.budget_input.setRange(0, 9_999_999); self.budget_input.setPrefix("$"); self.budget_input.setValue(round(self.db.budget()))
        save_budget = QPushButton("Save budget"); save_budget.setObjectName("secondary"); save_budget.clicked.connect(self.save_budget)
        self.budget_status = QLabel(); self.budget_status.setStyleSheet("font-weight: 600;")
        budget_row.addWidget(budget_label); budget_row.addWidget(self.budget_input); budget_row.addWidget(save_budget); budget_row.addSpacing(12); budget_row.addWidget(self.budget_status); budget_row.addStretch(); layout.addLayout(budget_row)
        table_header = QHBoxLayout(); table_title = QLabel("Transactions"); table_title.setStyleSheet("font-size: 18px; font-weight: 700;")
        edit = QPushButton("Edit selected"); edit.setObjectName("secondary"); edit.clicked.connect(self.edit_transaction)
        delete = QPushButton("Delete selected"); delete.setStyleSheet("background: #dc2626;"); delete.clicked.connect(self.delete_transaction)
        table_header.addWidget(table_title); table_header.addStretch(); table_header.addWidget(edit); table_header.addWidget(delete); layout.addLayout(table_header)
        self.table = QTableWidget(0, 6); self.table.setHorizontalHeaderLabels(["Date", "Type", "Category", "Note", "Amount", "ID"])
        self.table.setColumnHidden(5, True); self.table.setSelectionBehavior(QTableWidget.SelectRows); self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch); self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for col in (1, 2, 4): self.table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.table.cellDoubleClicked.connect(lambda *_: self.edit_transaction()); layout.addWidget(self.table, 1)

    def save_budget(self):
        self.db.set_budget(float(self.budget_input.value())); self.refresh()

    def selected_id(self):
        row = self.table.currentRow()
        return int(self.table.item(row, 5).text()) if row >= 0 else None

    def add_transaction(self):
        dialog = TransactionDialog(self)
        if dialog.exec() and dialog.values()[1] > 0:
            self.db.add(*dialog.values()); self.refresh()

    def edit_transaction(self):
        transaction_id = self.selected_id()
        if transaction_id is None: QMessageBox.information(self, "Select a transaction", "Choose a row to edit first."); return
        transaction = next(row for row in self.db.all() if row["id"] == transaction_id)
        dialog = TransactionDialog(self, transaction)
        if dialog.exec(): self.db.update(transaction_id, *dialog.values()); self.refresh()

    def delete_transaction(self):
        transaction_id = self.selected_id()
        if transaction_id is None: QMessageBox.information(self, "Select a transaction", "Choose a row to delete first."); return
        if QMessageBox.question(self, "Delete transaction", "Delete the selected transaction?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.db.delete(transaction_id); self.refresh()

    def refresh(self):
        income, expenses = self.db.totals_this_month(); budget = self.db.budget(); net = income - expenses
        self.income_amount.setText(f"${income:,.2f}"); self.expense_amount.setText(f"${expenses:,.2f}"); self.net_amount.setText(f"${net:,.2f}")
        self.net_amount.setStyleSheet(f"color: {'#059669' if net >= 0 else '#dc2626'};")
        if budget <= 0: self.budget_status.setText("Set a budget to track spending."); self.budget_status.setStyleSheet("color: #667085; font-weight: 600;")
        elif expenses > budget: self.budget_status.setText(f"Over budget by ${expenses - budget:,.2f}"); self.budget_status.setStyleSheet("color: #dc2626; font-weight: 700;")
        else: self.budget_status.setText(f"${budget - expenses:,.2f} left of ${budget:,.2f}"); self.budget_status.setStyleSheet("color: #059669; font-weight: 700;")
        rows = self.db.all(); self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            values = [row["transaction_date"], row["kind"], row["category"], row["note"] or "", f"${row['amount']:,.2f}", str(row["id"])]
            for j, value in enumerate(values):
                item = QTableWidgetItem(value); item.setTextAlignment(Qt.AlignRight if j == 4 else Qt.AlignVCenter)
                if j == 4: item.setForeground(QColor("#059669" if row["kind"] == "Income" else "#dc2626")); item.setFont(QFont("Arial", 10, QFont.Bold))
                self.table.setItem(i, j, item)


if __name__ == "__main__":
    app = QApplication(sys.argv); app.setApplicationName("Budget Tracker")
    window = BudgetWindow(); window.show(); sys.exit(app.exec())
