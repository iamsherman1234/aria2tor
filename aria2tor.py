import subprocess
import aria2p
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
import threading
import os
import sys

# Start aria2c with RPC enabled and secure secret
ARIA2C_PATH = r"C:\Users\chum.layan\AppData\Local\Programs\Python\WPy64-312101\python\Lib\site-packages\aria2c\aria2c.exe"
ARIA2C_COMMAND = [
    ARIA2C_PATH,
    "--enable-rpc",
    "--rpc-listen-all=true",
    "--rpc-allow-origin-all",
    "--rpc-secret=168@Appletree"
]

# Start aria2c daemon
try:
    subprocess.Popen(ARIA2C_COMMAND)
    print("aria2c daemon started successfully")
except FileNotFoundError:
    print(f"Warning: aria2c not found at {ARIA2C_PATH}")
    print("Please ensure aria2c is installed and the path is correct.")
    print("Continuing without starting daemon - assuming aria2c is already running")
except Exception as e:
    print(f"Error starting aria2c daemon: {e}")

REFRESH_INTERVAL_MS = 5000  # 5 seconds
RPC_SECRET = "168@Appletree"


class Aria2TransmissionStyleApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Aria2 — Transmission-style GUI")
        
        # Initialize API connection
        try:
            self.api = aria2p.API(
                aria2p.Client(
                    host="http://localhost", 
                    port=6800, 
                    secret=RPC_SECRET
                )
            )
            print("Successfully connected to aria2 RPC")
        except Exception as e:
            messagebox.showerror("Connection Error", f"Failed to connect to aria2 RPC:\n{e}")
            self.api = None
            print(f"Connection error: {e}")

        # Default settings
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

        # Progress bars for visual progress display
        self._progressbars = {}
        self._is_refreshing = False

        # Setup GUI
        self._setup_toolbar()
        self._setup_main_interface()
        self._setup_context_menu()
        self._start_refresh_loop()

    def _setup_toolbar(self):
        """Create the main toolbar with action buttons"""
        toolbar = ttk.Frame(self.root)
        toolbar.pack(fill="x", padx=6, pady=6)

        # Action buttons
        buttons = [
            ("Add Magnet", self.add_magnet_dialog),
            ("Add Torrent", self.add_torrent_dialog),
            ("Add URL", self.add_url_dialog),
            ("Set Download Location", self.set_download_location),
            ("Download Options", self.configure_download_options),
            ("Start", self.start_selected),
            ("Pause", self.pause_selected),
            ("Remove", self.remove_selected),
            ("Refresh", self.manual_refresh)
        ]

        for text, command in buttons:
            ttk.Button(toolbar, text=text, command=command).pack(side="left", padx=4)

        # Help text
        ttk.Label(toolbar, text="(Double-click a row to toggle Pause/Resume)").pack(side="right")

    def _setup_main_interface(self):
        """Setup the main interface with treeview and details pane"""
        # Main split: treeview above, details below
        main_pane = ttk.Panedwindow(self.root, orient="vertical")
        main_pane.pack(fill="both", expand=True)

        # Downloads treeview
        self._setup_downloads_tree(main_pane)
        
        # Details pane with tabs
        self._setup_details_pane(main_pane)

    def _setup_downloads_tree(self, parent):
        """Setup the main downloads treeview"""
        tree_frame = ttk.Frame(parent)
        
        # Define columns
        columns = ("name", "status", "progress", "speed", "eta")
        self.tree = ttk.Treeview(
            tree_frame, 
            columns=columns,
            show="headings", 
            selectmode="extended"
        )

        # Configure column headers
        headers = {
            "name": "Name",
            "status": "Status", 
            "progress": "Progress",
            "speed": "Speed",
            "eta": "ETA"
        }
        
        column_widths = {
            "name": 420,
            "status": 80,
            "progress": 140,
            "speed": 100,
            "eta": 90
        }

        for col in columns:
            self.tree.heading(col, text=headers[col])
            self.tree.column(
                col, 
                width=column_widths[col], 
                anchor="center" if col != "name" else "w"
            )

        # Scrollbar
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True, side="left")
        
        parent.add(tree_frame, weight=3)

        # Bind events
        self.tree.bind("<Double-1>", self.on_tree_double_click)
        self.tree.bind("<Button-3>", self.on_tree_right_click)
        self.tree.bind("<Configure>", lambda e: self._reposition_all_progressbars())
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.update_details_for_selection())

    def _setup_details_pane(self, parent):
        """Setup the details pane with notebook tabs"""
        details_frame = ttk.Frame(parent)
        nb = ttk.Notebook(details_frame)
        nb.pack(fill="both", expand=True)

        # Info tab
        self.info_text = tk.Text(nb, height=8, state="disabled", wrap=tk.WORD)
        nb.add(self.info_text, text="Info")

        # Files tab
        self.files_tree = ttk.Treeview(
            nb, 
            columns=("path", "size", "progress"), 
            show="headings"
        )
        
        file_headers = {"path": "Path", "size": "Size", "progress": "Progress"}
        file_widths = {"path": 400, "size": 100, "progress": 100}
        
        for col, header in file_headers.items():
            self.files_tree.heading(col, text=header)
            self.files_tree.column(
                col, 
                width=file_widths[col], 
                anchor="center" if col != "path" else "w"
            )
        
        nb.add(self.files_tree, text="Files")

        # Trackers tab
        self.trackers_tree = ttk.Treeview(
            nb, 
            columns=("tracker", "status"), 
            show="headings"
        )
        
        self.trackers_tree.heading("tracker", text="Tracker URL")
        self.trackers_tree.heading("status", text="Status")
        self.trackers_tree.column("tracker", width=440, anchor="w")
        self.trackers_tree.column("status", width=100, anchor="center")
        
        nb.add(self.trackers_tree, text="Trackers")

        parent.add(details_frame, weight=1)

    def _setup_context_menu(self):
        """Setup right-click context menu"""
        self.rc_menu = tk.Menu(self.root, tearoff=0)
        self.rc_menu.add_command(label="Start", command=self.start_selected)
        self.rc_menu.add_command(label="Pause", command=self.pause_selected)
        self.rc_menu.add_separator()
        self.rc_menu.add_command(label="Remove", command=self.remove_selected)
        self.rc_menu.add_command(label="Remove with Files", command=self.remove_selected_with_files)

    def _start_refresh_loop(self):
        """Start the periodic refresh loop"""
        self.root.after(200, self.refresh_loop)

    def configure_download_options(self):
        """Open dialog for configuring download options"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Download Options")
        dialog.resizable(False, False)
        dialog.geometry("+%d+%d" % (
            self.root.winfo_rootx() + 50, 
            self.root.winfo_rooty() + 50
        ))

        options_frame = ttk.Frame(dialog, padding="10 10 10 10")
        options_frame.pack(fill="both", expand=True)

        entries = {}
        row = 0

        # Connection Settings
        ttk.Label(options_frame, text="Connection Settings:", font=("", 10, "bold")).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(0, 5)
        )
        row += 1

        ttk.Label(options_frame, text="Max connections per server:").grid(
            row=row, column=0, sticky="e", padx=5
        )
        entries['max-connection-per-server'] = ttk.Entry(options_frame, width=10)
        entries['max-connection-per-server'].grid(row=row, column=1, sticky="w")
        entries['max-connection-per-server'].insert(
            0, self.default_options['max-connection-per-server']
        )
        row += 1

        # Split Settings
        ttk.Label(options_frame, text="Split Settings:", font=("", 10, "bold")).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(10, 5)
        )
        row += 1

        ttk.Label(options_frame, text="Number of segments to split:").grid(
            row=row, column=0, sticky="e", padx=5
        )
        entries['split'] = ttk.Entry(options_frame, width=10)
        entries['split'].grid(row=row, column=1, sticky="w")
        entries['split'].insert(0, self.default_options['split'])
        row += 1

        ttk.Label(options_frame, text="Minimum split size:").grid(
            row=row, column=0, sticky="e", padx=5
        )
        entries['min-split-size'] = ttk.Entry(options_frame, width=10)
        entries['min-split-size'].grid(row=row, column=1, sticky="w")
        entries['min-split-size'].insert(0, self.default_options['min-split-size'])
        row += 1

        # File Allocation
        ttk.Label(options_frame, text="File Allocation:").grid(
            row=row, column=0, sticky="e", padx=5
        )
        allocation_var = tk.StringVar(value=self.default_options['file-allocation'])
        allocation_menu = ttk.OptionMenu(
            options_frame, 
            allocation_var,
            self.default_options['file-allocation'],
            "none", "prealloc", "trunc", "falloc"
        )
        allocation_menu.grid(row=row, column=1, sticky="w")
        entries['file-allocation'] = allocation_var
        row += 1

        # Speed Limits
        ttk.Label(options_frame, text="Speed Limits:", font=("", 10, "bold")).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(10, 5)
        )
        row += 1

        ttk.Label(options_frame, text="Max overall download limit:").grid(
            row=row, column=0, sticky="e", padx=5
        )
        entries['max-overall-download-limit'] = ttk.Entry(options_frame, width=10)
        entries['max-overall-download-limit'].grid(row=row, column=1, sticky="w")
        entries['max-overall-download-limit'].insert(
            0, self.default_options['max-overall-download-limit']
        )
        ttk.Label(options_frame, text="(0 for unlimited)").grid(
            row=row, column=2, sticky="w"
        )
        row += 1

        ttk.Label(options_frame, text="Max download limit per torrent:").grid(
            row=row, column=0, sticky="e", padx=5
        )
        entries['max-download-limit'] = ttk.Entry(options_frame, width=10)
        entries['max-download-limit'].grid(row=row, column=1, sticky="w")
        entries['max-download-limit'].insert(0, self.default_options['max-download-limit'])
        ttk.Label(options_frame, text="(0 for unlimited)").grid(
            row=row, column=2, sticky="w"
        )
        row += 1

        # Continue downloads checkbox
        continue_var = tk.BooleanVar(value=self.default_options['continue'] == 'true')
        ttk.Checkbutton(
            options_frame, 
            text="Continue interrupted downloads", 
            variable=continue_var
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 0))
        entries['continue'] = continue_var
        row += 1

        def save_options():
            """Save the configured options"""
            for key in entries:
                if key == 'continue':
                    self.default_options[key] = 'true' if entries[key].get() else 'false'
                elif key == 'file-allocation':
                    self.default_options[key] = entries[key].get()
                else:
                    self.default_options[key] = entries[key].get().strip()
            dialog.destroy()
            messagebox.showinfo("Options Saved", "Download options have been updated.")

        # Buttons
        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill="x", padx=10, pady=10)
        ttk.Button(button_frame, text="Save", command=save_options).pack(side="right", padx=5)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side="right", padx=5)

    def set_download_location(self):
        """Set default download location"""
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
        """Add a magnet link dialog"""
        magnet = simpledialog.askstring("Add Magnet", "Paste magnet link:")
        if not magnet:
            return
            
        if not magnet.strip().startswith("magnet:?"):
            messagebox.showerror(
                "Invalid Magnet", 
                "Please paste a valid magnet link starting with 'magnet:?'."
            )
            return

        dl_dir = filedialog.askdirectory(
            title="Select download directory",
            initialdir=self.default_download_dir
        )
        
        options = self.default_options.copy()
        options["dir"] = dl_dir if dl_dir else self.default_download_dir

        def add_thread():
            """Add magnet in separate thread"""
            try:
                if self.api:
                    self.api.add_magnet(magnet.strip(), options=options)
                    self._safe_message(
                        "Added magnet",
                        f"Magnet added to aria2.\n"
                        f"Download location: {options['dir']}"
                    )
                else:
                    self._safe_message("Error", "Not connected to aria2 RPC")
            except Exception as e:
                self._safe_message("Error adding magnet", str(e))
            self.refresh_all()

        threading.Thread(target=add_thread, daemon=True).start()

    def add_torrent_dialog(self):
        """Add a torrent file dialog"""
        torrent_file = filedialog.askopenfilename(
            title="Select Torrent File",
            filetypes=[("Torrent files", "*.torrent"), ("All files", "*.*")]
        )
        
        if not torrent_file:
            return
        
        dl_dir = filedialog.askdirectory(
            title="Select download directory",
            initialdir=self.default_download_dir
        )
        
        options = self.default_options.copy()
        options["dir"] = dl_dir if dl_dir else self.default_download_dir

        def add_thread():
            """Add torrent in separate thread"""
            try:
                if self.api:
                    self.api.add_torrent(torrent_file, options=options)
                    self._safe_message(
                        "Added torrent",
                        f"Torrent added to aria2.\n"
                        f"File: {os.path.basename(torrent_file)}\n"
                        f"Download location: {options['dir']}"
                    )
                else:
                    self._safe_message("Error", "Not connected to aria2 RPC")
            except Exception as e:
                self._safe_message("Error adding torrent", str(e))
            self.refresh_all()

        threading.Thread(target=add_thread, daemon=True).start()

    def add_url_dialog(self):
        """Add a URL download dialog"""
        url = simpledialog.askstring("Add URL", "Enter download URL:")
        if not url:
            return
        
        dl_dir = filedialog.askdirectory(
            title="Select download directory",
            initialdir=self.default_download_dir
        )
        
        options = self.default_options.copy()
        options["dir"] = dl_dir if dl_dir else self.default_download_dir

        def add_thread():
            """Add URL in separate thread"""
            try:
                if self.api:
                    self.api.add_uris([url.strip()], options=options)
                    self._safe_message(
                        "Added URL",
                        f"URL added to aria2.\n"
                        f"URL: {url[:50]}{'...' if len(url) > 50 else ''}\n"
                        f"Download location: {options['dir']}"
                    )
                else:
                    self._safe_message("Error", "Not connected to aria2 RPC")
            except Exception as e:
                self._safe_message("Error adding URL", str(e))
            self.refresh_all()

        threading.Thread(target=add_thread, daemon=True).start()

    def manual_refresh(self):
        """Manual refresh button handler"""
        self.refresh_all()

    def _get_selected_gids(self):
        """Get selected download GIDs"""
        return list(self.tree.selection())

    def start_selected(self):
        """Start/resume selected downloads"""
        gids = self._get_selected_gids()
        if not gids:
            messagebox.showinfo("Start", "No downloads selected.")
            return
            
        if not self.api:
            messagebox.showerror("Error", "Not connected to aria2 RPC")
            return
            
        for gid in gids:
            try:
                self.api.resume(gid)
            except Exception as e:
                print(f"Failed to start {gid}: {e}")
        self.refresh_all()

    def pause_selected(self):
        """Pause selected downloads"""
        gids = self._get_selected_gids()
        if not gids:
            messagebox.showinfo("Pause", "No downloads selected.")
            return
            
        if not self.api:
            messagebox.showerror("Error", "Not connected to aria2 RPC")
            return
            
        for gid in gids:
            try:
                self.api.pause(gid)
            except Exception as e:
                print(f"Failed to pause {gid}: {e}")
        self.refresh_all()

    def remove_selected(self):
        """Remove selected downloads"""
        gids = self._get_selected_gids()
        if not gids:
            messagebox.showinfo("Remove", "No downloads selected.")
            return
            
        if not messagebox.askyesno("Remove", f"Remove {len(gids)} selected download(s)?"):
            return
            
        if not self.api:
            messagebox.showerror("Error", "Not connected to aria2 RPC")
            return
            
        for gid in gids:
            try:
                self.api.remove(gid)
            except Exception as e:
                print(f"Failed to remove {gid}: {e}")
        self.refresh_all()

    def remove_selected_with_files(self):
        """Remove selected downloads and delete files"""
        gids = self._get_selected_gids()
        if not gids:
            messagebox.showinfo("Remove", "No downloads selected.")
            return
            
        if not messagebox.askyesno(
            "Remove with Files", 
            f"Remove {len(gids)} selected download(s) AND DELETE THEIR FILES?\n\n"
            "This action cannot be undone!"
        ):
            return
            
        if not self.api:
            messagebox.showerror("Error", "Not connected to aria2 RPC")
            return
            
        for gid in gids:
            try:
                self.api.remove(gid, force=True)
            except Exception as e:
                print(f"Failed to remove {gid}: {e}")
        self.refresh_all()

    def on_tree_double_click(self, event):
        """Handle double-click on tree item to toggle pause/resume"""
        item = self.tree.identify_row(event.y)
        if not item or not self.api:
            return
            
        try:
            download = self.api.get_download(item)
            if download.is_paused:
                self.api.resume(item)
            else:
                self.api.pause(item)
        except Exception as e:
            print(f"Failed toggling {item}: {e}")
        self.refresh_all()

    def on_tree_right_click(self, event):
        """Handle right-click context menu"""
        iid = self.tree.identify_row(event.y)
        if iid:
            if iid not in self.tree.selection():
                self.tree.selection_set(iid)
            try:
                self.rc_menu.tk_popup(event.x_root, event.y_root)
            finally:
                self.rc_menu.grab_release()

    def refresh_loop(self):
        """Main refresh loop"""
        if not self._is_refreshing:
            self._is_refreshing = True
            try:
                self.refresh_all()
            finally:
                self._is_refreshing = False
        self.root.after(REFRESH_INTERVAL_MS, self.refresh_loop)

    def refresh_all(self):
        """Refresh all downloads and update UI"""
        if not self.api:
            return
            
        try:
            downloads = list(self.api.get_downloads())
        except Exception as e:
            print(f"Could not contact aria2 RPC: {e}")
            downloads = []

        current_gids = set(d.gid for d in downloads)
        existing = set(self.tree.get_children())

        # Remove downloads no longer present
        for gid in existing - current_gids:
            try:
                self.tree.delete(gid)
            except Exception:
                pass
            if gid in self._progressbars:
                pb = self._progressbars.pop(gid)
                pb.destroy()

        # Update or add downloads
        for d in downloads:
            gid = d.gid
            name = d.name or (d.files[0].path if getattr(d, "files", None) else gid)
            status = d.status if hasattr(d, "status") else ("Paused" if d.is_paused else "Active")
            
            # Calculate progress
            try:
                progress = float(d.progress) if hasattr(d, 'progress') else (
                    d.completed_length / d.total_length * 100 
                    if getattr(d, 'total_length', 0) else 0.0
                )
            except Exception:
                progress = 0.0

            progress_text = f"{progress:.1f}%"
            
            # Get speed
            try:
                speed = (d.download_speed_string() 
                        if callable(getattr(d, "download_speed_string", None)) 
                        else getattr(d, "download_speed", "-"))
                if isinstance(speed, (int, float)) and speed > 0:
                    speed = self._fmt_bytes(speed) + "/s"
                elif not speed or speed == "0":
                    speed = "-"
            except Exception:
                speed = "-"

            # Get ETA
            try:
                eta_text = (d.eta_string() 
                           if callable(getattr(d, "eta_string", None)) 
                           else self._calculate_eta(d))
            except Exception:
                eta_text = "-"

            values = (
                name, 
                status, 
                progress_text, 
                speed if speed else "-", 
                eta_text if eta_text else "-"
            )

            # Update or insert item
            if gid in existing:
                self.tree.item(gid, values=values)
            else:
                self.tree.insert("", "end", iid=gid, values=values)

            self._ensure_progressbar_for_row(gid, progress)

        self._reposition_all_progressbars()
        self.update_details_for_selection()

    def _calculate_eta(self, download):
        """Calculate ETA for a download"""
        try:
            if download.status != "active":
                return "-"
            
            speed = getattr(download, "download_speed", 0)
            if not speed or speed == 0:
                return "-"
            
            remaining = download.total_length - download.completed_length
            if remaining <= 0:
                return "-"
            
            seconds = remaining / speed
            if seconds < 60:
                return f"{int(seconds)}s"
            elif seconds < 3600:
                return f"{int(seconds/60)}m {int(seconds%60)}s"
            else:
                hours = int(seconds / 3600)
                minutes = int((seconds % 3600) / 60)
                return f"{hours}h {minutes}m"
        except Exception:
            return "-"

    def _ensure_progressbar_for_row(self, gid, percent):
        """Ensure progress bar exists for the given row"""
        if gid not in self._progressbars:
            pb = ttk.Progressbar(
                self.tree, 
                orient="horizontal", 
                mode="determinate", 
                maximum=100
            )
            pb._gid = gid
            pb.place_forget()
            self._progressbars[gid] = pb
            
        try:
            self._progressbars[gid]['value'] = max(0.0, min(100.0, percent))
        except Exception:
            self._progressbars[gid]['value'] = 0

    def _bbox_for_progress_column(self, item_iid):
        """Get bounding box for progress column of given item"""
        try:
            return self.tree.bbox(item_iid, column="progress")
        except Exception:
            return None

    def _reposition_all_progressbars(self):
        """Reposition all progress bars to match their rows"""
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
        """Update details pane based on current selection"""
        sel = self.tree.selection()
        if not sel or not self.api:
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

        # Build info text
        info_lines = [f"Name: {d.name}", f"GID: {d.gid}"]
        
        try:
            total = getattr(d, "total_length", None)
            completed = getattr(d, "completed_length", None)
            if total and completed is not None:
                info_lines.append(
                    f"Size: {self._fmt_bytes(int(total))} "
                    f"(completed {self._fmt_bytes(int(completed))})"
                )
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
            
        # Add more details
        try:
            if hasattr(d, "download_speed") and d.download_speed:
                info_lines.append(f"Download Speed: {self._fmt_bytes(d.download_speed)}/s")
            if hasattr(d, "upload_speed") and d.upload_speed:
                info_lines.append(f"Upload Speed: {self._fmt_bytes(d.upload_speed)}/s")
            if hasattr(d, "connections") and d.connections:
                info_lines.append(f"Connections: {d.connections}")
            if hasattr(d, "num_seeders"):
                info_lines.append(f"Seeders: {d.num_seeders}")
        except Exception:
            pass
            
        self._set_info_text("\n".join(info_lines))

        # Update files
        files = getattr(d, "files", None)
        file_rows = []
        if files:
            for f in files:
                path = getattr(f, "path", "<unknown>")
                size = getattr(f, "length", getattr(f, "size", 0))
                prog = getattr(f, "completed_length", 0)
                prog_pct = (int(prog) / int(size) * 100) if size and int(size) > 0 else 0
                file_rows.append((
                    path, 
                    self._fmt_bytes(int(size) if size else 0), 
                    f"{prog_pct:.1f}%"
                ))
        self._set_files(file_rows)

        # Update trackers
        tracker_rows = []
        try:
            # Try aria2p trackers attribute first
            trackers = getattr(d, "trackers", None)
            if trackers:
                for t in trackers:
                    tracker_rows.append((
                        getattr(t, "announce", str(t)), 
                        getattr(t, "status", "-")
                    ))
            else:
                # Fallback to direct RPC call for torrents
                if d.status in ["active", "paused", "waiting"]:
                    tlist = self.api.client.call("tellStatus", d.gid, ["announceList"])
                    announce_list = tlist.get("announceList", [])
                    for tier in announce_list:
                        for tracker in tier:
                            tracker_rows.append((tracker.get("announce", ""), "Active"))
        except Exception as e:
            # Not a torrent or no trackers
            pass
            
        self._set_trackers(tracker_rows)

    def _set_info_text(self, text):
        """Update info text widget"""
        self.info_text.configure(state="normal")
        self.info_text.delete("1.0", "end")
        self.info_text.insert("1.0", text)
        self.info_text.configure(state="disabled")

    def _set_files(self, rows):
        """Update files treeview"""
        for r in self.files_tree.get_children():
            self.files_tree.delete(r)
        for path, size, prog in rows:
            self.files_tree.insert("", "end", values=(path, size, prog))

    def _set_trackers(self, rows):
        """Update trackers treeview"""
        for r in self.trackers_tree.get_children():
            self.trackers_tree.delete(r)
        for tr, st in rows:
            self.trackers_tree.insert("", "end", values=(tr, st))

    def _fmt_bytes(self, n):
        """Format bytes as human readable string"""
        try:
            n = int(n)
        except Exception:
            return str(n)
            
        if n < 0:
            return "0 B"
            
        if n < 1024:
            return f"{n} B"
            
        for unit in ["KB", "MB", "GB", "TB", "PB"]:
            n /= 1024.0
            if abs(n) < 1024.0:
                return f"{n:3.1f} {unit}"
        return f"{n:.1f} PB"

    def _safe_message(self, title, msg):
        """Show message box in main thread"""
        self.root.after(0, lambda: messagebox.showinfo(title, msg))


def cleanup_progressbars(app):
    """Cleanup progress bars before closing"""
    try:
        for pb in app._progressbars.values():
            pb.destroy()
    except Exception:
        pass


def main():
    """Main application entry point"""
    try:
        root = tk.Tk()
        root.geometry("900x600")
        root.minsize(800, 500)
        
        # Set window icon (if available)
        try:
            root.iconbitmap(default='aria2.ico')
        except Exception:
            pass
        
        # Create application instance
        app = Aria2TransmissionStyleApp(root)
        
        # Handle window close event
        def on_closing():
            cleanup_progressbars(app)
            root.destroy()
        
        root.protocol("WM_DELETE_WINDOW", on_closing)
        
        # Start main loop
        root.mainloop()
        
    except KeyboardInterrupt:
        print("Application interrupted by user")
    except Exception as e:
        print(f"Application error: {e}")
        import traceback
        traceback.print_exc()
        try:
            messagebox.showerror("Application Error", f"An error occurred:\n{e}")
        except Exception:
            pass


if __name__ == "__main__":
    main()
