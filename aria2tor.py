import subprocess
import aria2p
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
import threading
import os

# Start aria2c with RPC enabled and secure secret
aria2c_path = r"C:\Users\chum.layan\AppData\Local\Programs\Python\WPy64-312101\python\Lib\site-packages\aria2c\aria2c.exe"
aria2c_command = [
    aria2c_path,
    "--enable-rpc",
    "--rpc-listen-all=true",
    "--rpc-allow-origin-all",
    "--rpc-secret=168@Appletree"
]
subprocess.Popen(aria2c_command)

REFRESH_INTERVAL_MS = 5000  # 5 seconds


class Aria2TransmissionStyleApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Aria2 — Transmission-like GUI")
        self.api = aria2p.API(aria2p.Client(host="http://localhost", port=6800, secret="168@Appletree"))

        self.default_download_dir = os.path.expanduser("~/Downloads")
        self.default_options = {
            'max-connection-per-server': '16',
            'split': '16',
            'min-split-size': '10M',
            'file-allocation': 'none',
            'max-overall-download-limit': '0',
            'max-download-limit': '0',
            'continue': 'true'
        }

        self._progressbars = {}

        # Toolbar
        toolbar = ttk.Frame(root)
        toolbar.pack(fill="x", padx=6, pady=6)

        ttk.Button(toolbar, text="Add Magnet", command=self.add_magnet_dialog).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Set Download Location", command=self.set_download_location).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Download Options", command=self.configure_download_options).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Start", command=self.start_selected).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Pause", command=self.pause_selected).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Remove", command=self.remove_selected).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Refresh", command=self.manual_refresh).pack(side="left", padx=8)

        ttk.Label(toolbar, text="  (Double-click a row to toggle Pause/Resume)").pack(side="right")

        # Main split: treeview above, details below
        main_pane = ttk.Panedwindow(root, orient="vertical")
        main_pane.pack(fill="both", expand=True)

        # Treeview
        tree_frame = ttk.Frame(main_pane)
        self.tree = ttk.Treeview(tree_frame, columns=("name", "status", "progress", "speed", "eta"),
                                 show="headings", selectmode="extended")
        self.tree.heading("name", text="Name")
        self.tree.heading("status", text="Status")
        self.tree.heading("progress", text="Progress")
        self.tree.heading("speed", text="Speed")
        self.tree.heading("eta", text="ETA")

        self.tree.column("name", width=420, anchor="w")
        self.tree.column("status", width=80, anchor="center")
        self.tree.column("progress", width=140, anchor="center")
        self.tree.column("speed", width=100, anchor="center")
        self.tree.column("eta", width=90, anchor="center")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True, side="left")
        main_pane.add(tree_frame, weight=3)

        # Bindings
        self.tree.bind("<Double-1>", self.on_tree_double_click)
        self.tree.bind("<Button-3>", self.on_tree_right_click)
        self.tree.bind("<Configure>", lambda e: self._reposition_all_progressbars())

        # Details pane
        details_frame = ttk.Frame(main_pane)
        nb = ttk.Notebook(details_frame)
        nb.pack(fill="both", expand=True)

        # Info tab
        self.info_text = tk.Text(nb, height=8, state="disabled")
        nb.add(self.info_text, text="Info")

        # Files tab
        self.files_tree = ttk.Treeview(nb, columns=("path", "size", "progress"), show="headings")
        self.files_tree.heading("path", text="Path")
        self.files_tree.heading("size", text="Size")
        self.files_tree.heading("progress", text="Progress")
        self.files_tree.column("path", width=400, anchor="w")
        self.files_tree.column("size", width=100, anchor="center")
        self.files_tree.column("progress", width=100, anchor="center")
        nb.add(self.files_tree, text="Files")

        # Trackers tab
        self.trackers_tree = ttk.Treeview(nb, columns=("tracker", "status"), show="headings")
        self.trackers_tree.heading("tracker", text="Tracker URL")
        self.trackers_tree.heading("status", text="Status")
        self.trackers_tree.column("tracker", width=440, anchor="w")
        self.trackers_tree.column("status", width=100, anchor="center")
        nb.add(self.trackers_tree, text="Trackers")

        main_pane.add(details_frame, weight=1)

        # Right-click menu
        self.rc_menu = tk.Menu(root, tearoff=0)
        self.rc_menu.add_command(label="Start", command=self.start_selected)
        self.rc_menu.add_command(label="Pause", command=self.pause_selected)
        self.rc_menu.add_separator()
        self.rc_menu.add_command(label="Remove", command=self.remove_selected)

        # Periodic refresh
        self._is_refreshing = False
        self.root.after(200, self.refresh_loop)

        # Selection change updates
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.update_details_for_selection())

    def configure_download_options(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Download Options")
        dialog.resizable(False, False)
        dialog.geometry("+%d+%d" % (self.root.winfo_rootx()+50, self.root.winfo_rooty()+50))

        options_frame = ttk.Frame(dialog, padding="10 10 10 10")
        options_frame.pack(fill="both", expand=True)

        entries = {}
        row = 0

        ttk.Label(options_frame, text="Connection Settings:").grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 5))
        row += 1

        ttk.Label(options_frame, text="Max connections per server:").grid(row=row, column=0, sticky="e", padx=5)
        entries['max-connection-per-server'] = ttk.Entry(options_frame, width=10)
        entries['max-connection-per-server'].grid(row=row, column=1, sticky="w")
        entries['max-connection-per-server'].insert(0, self.default_options['max-connection-per-server'])
        row += 1

        ttk.Label(options_frame, text="Split Settings:").grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 5))
        row += 1

        ttk.Label(options_frame, text="Number of segments to split:").grid(row=row, column=0, sticky="e", padx=5)
        entries['split'] = ttk.Entry(options_frame, width=10)
        entries['split'].grid(row=row, column=1, sticky="w")
        entries['split'].insert(0, self.default_options['split'])
        row += 1

        ttk.Label(options_frame, text="Minimum split size:").grid(row=row, column=0, sticky="e", padx=5)
        entries['min-split-size'] = ttk.Entry(options_frame, width=10)
        entries['min-split-size'].grid(row=row, column=1, sticky="w")
        entries['min-split-size'].insert(0, self.default_options['min-split-size'])
        row += 1

        ttk.Label(options_frame, text="File Allocation:").grid(row=row, column=0, sticky="e", padx=5)
        allocation_var = tk.StringVar(value=self.default_options['file-allocation'])
        allocation_menu = ttk.OptionMenu(options_frame, allocation_var,
                                         self.default_options['file-allocation'],
                                         "none", "prealloc", "trunc")
        allocation_menu.grid(row=row, column=1, sticky="w")
        entries['file-allocation'] = allocation_var
        row += 1

        ttk.Label(options_frame, text="Speed Limits:").grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 5))
        row += 1

        ttk.Label(options_frame, text="Max overall download limit:").grid(row=row, column=0, sticky="e", padx=5)
        entries['max-overall-download-limit'] = ttk.Entry(options_frame, width=10)
        entries['max-overall-download-limit'].grid(row=row, column=1, sticky="w")
        entries['max-overall-download-limit'].insert(0, self.default_options['max-overall-download-limit'])
        ttk.Label(options_frame, text="(0 for unlimited)").grid(row=row, column=2, sticky="w")
        row += 1

        ttk.Label(options_frame, text="Max download limit per torrent:").grid(row=row, column=0, sticky="e", padx=5)
        entries['max-download-limit'] = ttk.Entry(options_frame, width=10)
        entries['max-download-limit'].grid(row=row, column=1, sticky="w")
        entries['max-download-limit'].insert(0, self.default_options['max-download-limit'])
        ttk.Label(options_frame, text="(0 for unlimited)").grid(row=row, column=2, sticky="w")
        row += 1

        continue_var = tk.BooleanVar(value=self.default_options['continue'] == 'true')
        ttk.Checkbutton(options_frame, text="Continue interrupted downloads", variable=continue_var).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(10, 0)
        )
        entries['continue'] = continue_var
        row += 1

        def save_options():
            for key in entries:
                if key == 'continue':
                    self.default_options[key] = 'true' if entries[key].get() else 'false'
                elif key == 'file-allocation':
                    self.default_options[key] = entries[key].get()
                else:
                    self.default_options[key] = entries[key].get().strip()
            dialog.destroy()
            messagebox.showinfo("Options Saved", "Download options have been updated.")

        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill="x", padx=10, pady=10)
        ttk.Button(button_frame, text="Save", command=save_options).pack(side="right", padx=5)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side="right", padx=5)

    # TODO: Rest of methods (set_download_location, add_magnet_dialog, start_selected, pause_selected, remove_selected, refresh_all, etc.)
    # would follow here with proper indentation exactly like above
    def set_download_location(self):
        new_dir = filedialog.askdirectory(
            title="Select Default Download Location",
            initialdir=self.default_download_dir
        )
        if new_dir:
            self.default_download_dir = new_dir
            messagebox.showinfo(
                "Download Location Set",
                f"New download location set to:\n{self.default_download_dir}"
            )

    def add_magnet_dialog(self):
        magnet = simpledialog.askstring("Add Magnet", "Paste magnet link:")
        if not magnet:
            return
        if not magnet.strip().startswith("magnet:?"):
            messagebox.showerror("Invalid Magnet", "Please paste a valid magnet link starting with 'magnet:?'.")
            return

        dl_dir = filedialog.askdirectory(
            title="Select download directory",
            initialdir=self.default_download_dir
        )
        options = self.default_options.copy()
        options["dir"] = dl_dir if dl_dir else self.default_download_dir

        def add_thread():
            try:
                self.api.add_magnet(magnet.strip(), options=options)
                self._safe_message("Added magnet",
                    f"Magnet added to aria2.\n"
                    f"Download location: {options['dir']}\n"
                    f"Options: {', '.join(f'{k}={v}' for k,v in options.items() if k != 'dir')}")
            except Exception as e:
                self._safe_message("Error adding magnet", str(e))
            self.refresh_all()

        threading.Thread(target=add_thread, daemon=True).start()

    def manual_refresh(self):
        self.refresh_all()

    def _get_selected_gids(self):
        return list(self.tree.selection())

    def start_selected(self):
        gids = self._get_selected_gids()
        if not gids:
            messagebox.showinfo("Start", "No downloads selected.")
            return
        for gid in gids:
            try:
                self.api.resume(gid)
            except Exception as e:
                self._safe_message("Error", f"Failed to start {gid}:\n{e}")
        self.refresh_all()

    def pause_selected(self):
        gids = self._get_selected_gids()
        if not gids:
            messagebox.showinfo("Pause", "No downloads selected.")
            return
        for gid in gids:
            try:
                self.api.pause(gid)
            except Exception as e:
                self._safe_message("Error", f"Failed to pause {gid}:\n{e}")
        self.refresh_all()

    def remove_selected(self):
        gids = self._get_selected_gids()
        if not gids:
            messagebox.showinfo("Remove", "No downloads selected.")
            return
        if not messagebox.askyesno("Remove", f"Remove {len(gids)} selected download(s)?"):
            return
        for gid in gids:
            try:
                self.api.remove(gid)
            except Exception as e:
                self._safe_message("Error", f"Failed to remove {gid}:\n{e}")
        self.refresh_all()

    def on_tree_double_click(self, event):
        item = self.tree.identify_row(event.y)
        if not item:
            return
        try:
            download = self.api.get_download(item)
            if download.is_paused:
                self.api.resume(item)
            else:
                self.api.pause(item)
        except Exception as e:
            self._safe_message("Error", f"Failed toggling {item}:\n{e}")
        self.refresh_all()

    def on_tree_right_click(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            if iid not in self.tree.selection():
                self.tree.selection_set(iid)
            try:
                self.rc_menu.tk_popup(event.x_root, event.y_root)
            finally:
                self.rc_menu.grab_release()

    def refresh_loop(self):
        if not self._is_refreshing:
            self._is_refreshing = True
            try:
                self.refresh_all()
            finally:
                self._is_refreshing = False
        self.root.after(REFRESH_INTERVAL_MS, self.refresh_loop)

    def refresh_all(self):
        try:
            downloads = list(self.api.get_downloads())
        except Exception as e:
            self._safe_message("Connection error", f"Could not contact aria2 RPC:\n{e}")
            downloads = []

        current_gids = set(d.gid for d in downloads)
        existing = set(self.tree.get_children())

        for gid in existing - current_gids:
            try:
                self.tree.delete(gid)
            except Exception:
                pass
            if gid in self._progressbars:
                pb = self._progressbars.pop(gid)
                pb.destroy()

        for d in downloads:
            gid = d.gid
            name = d.name or (d.files[0].path if getattr(d, "files", None) else gid)
            status = d.status if hasattr(d, "status") else ("Paused" if d.is_paused else "Active")
            try:
                progress = float(d.progress) if hasattr(d, 'progress') else (
                    d.completed_length / d.total_length * 100 if getattr(d, 'total_length', 0) else 0.0
                )
            except Exception:
                progress = 0.0

            progress_text = f"{progress:.1f}%"
            try:
                speed = d.download_speed_string() if callable(getattr(d, "download_speed_string", None)) else getattr(d, "downloadSpeed", "-")
            except Exception:
                speed = "-"

            try:
                eta_text = d.eta_string() if callable(getattr(d, "eta_string", None)) else "-"
            except Exception:
                eta_text = "-"

            values = (name, status, progress_text, speed if speed else "-", eta_text if eta_text else "-")

            if gid in existing:
                self.tree.item(gid, values=values)
            else:
                self.tree.insert("", "end", iid=gid, values=values)

            self._ensure_progressbar_for_row(gid, progress)

        self._reposition_all_progressbars()
        self.update_details_for_selection()

    def _ensure_progressbar_for_row(self, gid, percent):
        if gid not in self._progressbars:
            pb = ttk.Progressbar(self.tree, orient="horizontal", mode="determinate", maximum=100)
            pb._gid = gid
            pb.place_forget()
            self._progressbars[gid] = pb
        try:
            self._progressbars[gid]['value'] = max(0.0, min(100.0, percent))
        except Exception:
            self._progressbars[gid]['value'] = 0

    def _bbox_for_progress_column(self, item_iid):
        try:
            return self.tree.bbox(item_iid, column="progress")
        except Exception:
            return None

    def _reposition_all_progressbars(self):
        for gid, pb in list(self._progressbars.items()):
            if not self.tree.exists(gid):
                pb.place_forget()
                continue
            bbox = self._bbox_for_progress_column(gid)
            if not bbox:
                pb.place_forget()
                continue
            x, y, w, h = bbox
            pb.place(x=x+2, y=y+2, width=max(20, w-4), height=max(8, h-4))

    def update_details_for_selection(self):
        sel = self.tree.selection()
        if not sel:
            self._set_info_text("")
            self._set_files([])
            self._set_trackers([])
            return
        gid = sel[0]
        try:
            d = self.api.get_download(gid)
        except Exception:
            self._set_info_text("Could not fetch details.")
            return

        info_lines = [f"Name: {d.name}", f"GID: {d.gid}"]
        try:
            total = getattr(d, "total_length", None)
            completed = getattr(d, "completed_length", None)
            if total and completed is not None:
                info_lines.append(f"Size: {self._fmt_bytes(int(total))} (completed {self._fmt_bytes(int(completed))})")
        except Exception:
            pass
        info_lines.append(f"Status: {d.status}")
        try:
            info_lines.append(f"Download Dir: {d.dir}")
        except Exception:
            pass
        try:
            info_lines.append(f"Files: {len(getattr(d, 'files', []) or [])}")
        except Exception:
            pass
        self._set_info_text("\n".join(info_lines))

        files = getattr(d, "files", None)
        file_rows = []
        if files:
            for f in files:
                path = getattr(f, "path", "<unknown>")
                size = getattr(f, "length", getattr(f, "size", 0))
                prog = getattr(f, "completed_length", 0)
                prog_pct = (int(prog) / int(size) * 100) if size and int(size) > 0 else 0
                file_rows.append((path, self._fmt_bytes(int(size) if size else 0), f"{prog_pct:.1f}%"))
        self._set_files(file_rows)

        tracker_rows = []
		try:
		# Try aria2p trackers attribute first
    		trackers = getattr(d, "trackers", None)
		if trackers:
			for t in trackers:
				tracker_rows.append((getattr(t, "announce", str(t)), getattr(t, "status", "-")))
		else:
		# Fallback to direct RPC call
		tlist = self.api.client.get_trackers(d.gid)
			for t in tlist:
				tracker_rows.append((t.get("announce", ""), t.get("status", "-")))
		except Exception as e:
		tracker_rows.append(("Error fetching trackers", str(e)))	
        self._set_trackers(tracker_rows)

    def _set_info_text(self, text):
        self.info_text.configure(state="normal")
        self.info_text.delete("1.0", "end")
        self.info_text.insert("1.0", text)
        self.info_text.configure(state="disabled")

    def _set_files(self, rows):
        for r in self.files_tree.get_children():
            self.files_tree.delete(r)
        for path, size, prog in rows:
            self.files_tree.insert("", "end", values=(path, size, prog))

    def _set_trackers(self, rows):
        for r in self.trackers_tree.get_children():
            self.trackers_tree.delete(r)
        for tr, st in rows:
            self.trackers_tree.insert("", "end", values=(tr, st))

    def _fmt_bytes(self, n):
        try:
            n = int(n)
        except Exception:
            return str(n)
        if n < 1024:
            return f"{n} B"
        for unit in ["KB", "MB", "GB", "TB", "PB"]:
            n /= 1024.0
            if abs(n) < 1024.0:
                return f"{n:3.1f} {unit}"
        return f"{n:.1f} PB"

    def _safe_message(self, title, msg):
        self.root.after(0, lambda: messagebox.showinfo(title, msg))


if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("900x600")
    app = Aria2TransmissionStyleApp(root)
    root.mainloop()
