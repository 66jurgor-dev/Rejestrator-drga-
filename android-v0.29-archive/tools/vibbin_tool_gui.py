#!/usr/bin/env python3
"""Small desktop interface for decoding VIBRAW files."""

from __future__ import annotations

import pathlib
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from vibbin_decoder import decode_file
from vibbin_features import generate_features


class VibBinTool(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("VIBRAW - dekoder danych")
        self.geometry("680x310")
        self.minsize(620, 290)

        self.input_path = tk.StringVar()
        self.mode = tk.StringVar(value="features")
        self.window_seconds = tk.StringVar(value="1.0")
        self.status = tk.StringVar(value="Wybierz plik BIN.")
        self._build_ui()

    def _build_ui(self):
        root = ttk.Frame(self, padding=18)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)

        ttk.Label(root, text="Plik źródłowy BIN", font=("Segoe UI", 11, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        file_row = ttk.Frame(root)
        file_row.grid(row=1, column=0, sticky="ew", pady=(6, 16))
        file_row.columnconfigure(0, weight=1)
        ttk.Entry(file_row, textvariable=self.input_path).grid(row=0, column=0, sticky="ew")
        ttk.Button(file_row, text="Wybierz...", command=self._choose_input).grid(
            row=0, column=1, padx=(8, 0)
        )

        ttk.Label(root, text="Rodzaj wyniku", font=("Segoe UI", 11, "bold")).grid(
            row=2, column=0, sticky="w"
        )
        mode_row = ttk.Frame(root)
        mode_row.grid(row=3, column=0, sticky="w", pady=(6, 16))
        ttk.Radiobutton(
            mode_row,
            text="Cechy ML",
            value="features",
            variable=self.mode,
            command=self._update_window_state,
        ).pack(side="left")
        ttk.Radiobutton(
            mode_row,
            text="Pełny CSV zdarzeń",
            value="events",
            variable=self.mode,
            command=self._update_window_state,
        ).pack(side="left", padx=(20, 0))

        window_row = ttk.Frame(root)
        window_row.grid(row=4, column=0, sticky="w", pady=(0, 18))
        ttk.Label(window_row, text="Długość okna [s]:").pack(side="left")
        self.window_entry = ttk.Entry(window_row, width=10, textvariable=self.window_seconds)
        self.window_entry.pack(side="left", padx=(8, 0))

        self.run_button = ttk.Button(root, text="Generuj CSV", command=self._start)
        self.run_button.grid(row=5, column=0, sticky="ew")
        ttk.Separator(root).grid(row=6, column=0, sticky="ew", pady=14)
        ttk.Label(root, textvariable=self.status, wraplength=620).grid(row=7, column=0, sticky="w")

    def _choose_input(self):
        selected = filedialog.askopenfilename(
            title="Wybierz plik VIBRAW",
            filetypes=[("VIBRAW BIN", "*.bin"), ("Wszystkie pliki", "*.*")],
        )
        if selected:
            self.input_path.set(selected)
            self.status.set("Gotowy do przetwarzania.")

    def _update_window_state(self):
        self.window_entry.configure(state="normal" if self.mode.get() == "features" else "disabled")

    def _start(self):
        source = pathlib.Path(self.input_path.get().strip())
        if not source.is_file():
            messagebox.showerror("Brak pliku", "Wybierz istniejący plik BIN.")
            return
        try:
            window = float(self.window_seconds.get().replace(",", "."))
            if window <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Błędne okno", "Długość okna musi być dodatnią liczbą.")
            return

        suffix = ".features.csv" if self.mode.get() == "features" else ".events.csv"
        suggested = source.with_suffix(suffix).name
        selected = filedialog.asksaveasfilename(
            title="Zapisz wynik CSV",
            initialdir=str(source.parent),
            initialfile=suggested,
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
        )
        if not selected:
            return

        self.run_button.configure(state="disabled")
        self.status.set("Przetwarzanie pliku...")
        threading.Thread(
            target=self._run_conversion,
            args=(source, pathlib.Path(selected), window, self.mode.get()),
            daemon=True,
        ).start()

    def _run_conversion(self, source, output, window, mode):
        try:
            if mode == "features":
                summary = generate_features(source, output, window)
                text = f"Gotowe: {summary['rows']} okien, {summary['columns']} kolumn.\n{output}"
            else:
                summary = decode_file(source, output)
                text = f"Gotowe: {summary['events']} zdarzeń, {summary['valid_chunks']} bloków.\n{output}"
            self.after(0, self._finish, text, None)
        except Exception as error:  # GUI boundary: report parser and filesystem errors.
            self.after(0, self._finish, None, str(error))

    def _finish(self, text, error):
        self.run_button.configure(state="normal")
        if error:
            self.status.set("Przetwarzanie nie powiodło się.")
            messagebox.showerror("Błąd", error)
            return
        self.status.set(text)
        messagebox.showinfo("Gotowe", text)


if __name__ == "__main__":
    VibBinTool().mainloop()
