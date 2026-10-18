"""Thread-responsive desktop front end for the experimental viewport pipeline."""
from __future__ import annotations

from dataclasses import asdict
import logging
import queue
import threading

from .settings import AppSettings, default_settings_path, load_settings, save_settings


class WebcamApp:
    def __init__(self, root: tk.Tk, smoke=False):
        self.root = root
        self.smoke = smoke
        self.controller = None
        self.busy = False
        self.closing = False
        self.events = queue.SimpleQueue()
        self.preview_image = None
        self.recording_path = ""
        self.poll_id = None
        settings_error = None
        try:
            self.settings = AppSettings() if smoke else load_settings()
        except (OSError, ValueError) as exc:
            self.settings = AppSettings()
            settings_error = str(exc)
        root.title("Canon CHDK Webcam · Experimental")
        root.geometry("1080x760")
        root.minsize(900, 660)
        root.configure(bg="#10151e")
        self._style()
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        if settings_error:
            self.notice.set(f"Preferences could not be read. Defaults loaded: {settings_error}")
        self._poll()

    def _style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background="#10151e")
        style.configure("Card.TFrame", background="#1b2330")
        style.configure("TLabel", background="#10151e", foreground="#e7edf7", font=("Segoe UI", 10))
        style.configure("Muted.TLabel", foreground="#a7b4c9")
        style.configure("Title.TLabel", font=("Segoe UI", 23, "bold"))
        style.configure("TCheckbutton", background="#10151e", foreground="#e7edf7")
        style.map("TCheckbutton", background=[("active", "#263347")])
        style.configure("TButton", padding=(12, 8), font=("Segoe UI", 10))
        style.configure("TCombobox", padding=5)
        style.configure("TLabelframe", background="#10151e", bordercolor="#344154")
        style.configure("TLabelframe.Label", background="#10151e", foreground="#a7b4c9")

    def _build(self):
        outer = ttk.Frame(self.root, padding=22)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Canon CHDK Webcam", style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text="IXUS 117 HS / ELPH 100 HS · Experimental USB viewport capture",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 12))
        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        sidebar = ttk.Frame(body)
        sidebar.grid(row=0, column=0, sticky="ns", padx=(0, 14))
        settings_canvas = tk.Canvas(sidebar, width=288, bg="#10151e", highlightthickness=0)
        scrollbar = ttk.Scrollbar(sidebar, orient="vertical", command=settings_canvas.yview)
        settings_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        settings_canvas.pack(side="left", fill="y", expand=True)
        controls = ttk.Frame(settings_canvas, padding=(0, 0, 10, 0))
        settings_canvas.create_window((0, 0), window=controls, anchor="nw")
        controls.bind("<Configure>", lambda event: settings_canvas.configure(
            scrollregion=settings_canvas.bbox("all")))
        settings_canvas.bind("<MouseWheel>", lambda event: settings_canvas.yview_scroll(
            -1 if event.delta > 0 else 1, "units"))
        preview = ttk.Frame(body)
        preview.grid(row=0, column=1, sticky="nsew")
        self.variables = {}
        self.editable = []
        self.source = tk.StringVar(value="Simulation (synthetic frames)" if self.settings.mode == "simulate"
                                   else "USB camera (unverified hardware)")
        self._combo(controls, "Capture source", self.source,
                    ("Simulation (synthetic frames)", "USB camera (unverified hardware)"))
        self.resolution = tk.StringVar(value=f"{self.settings.width} × {self.settings.height}")
        self._combo(controls, "Host output resolution", self.resolution,
                    ("640 × 480", "1280 × 720", "1920 × 1080"))
        self.fps = tk.StringVar(value=str(self.settings.fps))
        self._combo(controls, "Host output FPS (target)", self.fps, ("15", "24", "30"))
        self.codec = tk.StringVar(value=self.settings.codec)
        self._combo(controls, "Host recording codec", self.codec, ("h264", "mjpeg"))
        self.bitrate = tk.IntVar(value=self.settings.bitrate)
        bitrate_row = ttk.Frame(controls)
        bitrate_row.pack(fill="x", pady=(9, 0))
        ttk.Label(bitrate_row, text="Target bitrate · Mbps").pack(side="left")
        ttk.Label(bitrate_row, textvariable=self.bitrate).pack(side="right")
        slider = ttk.Scale(controls, from_=2, to=60, variable=self.bitrate,
                           command=lambda value: self.bitrate.set(round(float(value))))
        slider.pack(fill="x", pady=(3, 8))
        self.editable.append((slider, "normal"))
        for name, text in (("virtual_camera", "Output to OBS virtual camera"),
                           ("reconnect", "Reconnect USB automatically"),
                           ("low_latency", "Low latency encoding"),
                           ("debug_logging", "Debug logging")):
            variable = tk.BooleanVar(value=getattr(self.settings, name))
            self.variables[name] = variable
            widget = ttk.Checkbutton(controls, text=text, variable=variable)
            widget.pack(anchor="w", pady=3)
            self.editable.append((widget, "normal"))
        clean = ttk.Checkbutton(controls, text="Clean video · viewport only", variable=tk.BooleanVar(value=True))
        clean.state(["disabled"])
        clean.pack(anchor="w", pady=3)
        advanced = ttk.Labelframe(controls, text="Host encoder / queue", padding=8)
        advanced.pack(fill="x", pady=10)
        self.encoder = tk.StringVar(value=self.settings.encoder)
        self._combo(advanced, "H.264 encoder preference", self.encoder,
                    ("auto", "libx264", "h264_nvenc", "h264_qsv", "h264_amf"))
        self.buffer = tk.StringVar(value=str(self.settings.buffer_size))
        self._combo(advanced, "Maximum queued frames", self.buffer, tuple(str(i) for i in (1, 2, 3, 4, 8)))
        self.rotation = tk.StringVar(value=str(self.settings.rotation))
        self._combo(advanced, "Camera orientation · degrees", self.rotation, ("0", "90", "180", "270"))
        self.record = tk.BooleanVar(value=False)
        widget = ttk.Checkbutton(controls, text="Record to file while capturing", variable=self.record)
        widget.pack(anchor="w", pady=3)
        self.editable.append((widget, "normal"))
        self.file_label = tk.StringVar(value="No recording selected")
        file_button = ttk.Button(controls, text="Choose recording file…", command=self._choose_file)
        file_button.pack(fill="x", pady=4)
        self.editable.append((file_button, "normal"))
        ttk.Label(controls, textvariable=self.file_label, wraplength=245, style="Muted.TLabel").pack(anchor="w")
        self.start_button = ttk.Button(controls, text="Connect & start capture", command=self._start)
        self.start_button.pack(fill="x", pady=(16, 5))
        self.stop_button = ttk.Button(controls, text="Stop & disconnect", command=self._stop, state="disabled")
        self.stop_button.pack(fill="x")
        self.status = tk.StringVar(value="Disconnected")
        ttk.Label(preview, textvariable=self.status, font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(0, 8))
        self.canvas = tk.Canvas(preview, bg="#090d14", highlightthickness=1,
                                highlightbackground="#344154", width=640, height=360)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_text(300, 170, text="Start capture to preview\nSimulation is available without a camera",
                                fill="#a7b4c9", font=("Segoe UI", 13), justify="center", tags="idle")
        ttk.Label(preview, text="Output scaling does not add detail. Native 1080p extraction remains research.\n"
                  "Clean viewport excludes CHDK bitmap overlays; camera-specific overlays need hardware checks.",
                  style="Muted.TLabel", wraplength=650).pack(anchor="w", pady=10)
        self.stats = tk.StringVar(value="Source: —    Output: —    FPS: —")
        ttk.Label(preview, textvariable=self.stats, justify="left", style="Muted.TLabel").pack(anchor="w")
        self.notice = tk.StringVar(value="No physical camera compatibility has been verified. OBS virtual camera must be installed.")
        ttk.Label(outer, textvariable=self.notice, wraplength=1000, foreground="#edc98a").pack(fill="x", pady=(12, 0))

    def _combo(self, parent, label, variable, choices):
        ttk.Label(parent, text=label).pack(anchor="w", pady=(5, 2))
        widget = ttk.Combobox(parent, textvariable=variable, values=choices, state="readonly", width=30)
        widget.pack(fill="x")
        self.editable.append((widget, "readonly"))

    def _choose_file(self):
        path = filedialog.asksaveasfilename(parent=self.root, title="Record host-encoded viewport video",
                                          defaultextension=".mkv", filetypes=[("Matroska video", "*.mkv"),
                                                                                         ("MP4 video", "*.mp4")])
        if path:
            self.recording_path = path
            self.file_label.set(path)
            self.record.set(True)

    def _read_settings(self):
        width, height = (int(value.strip()) for value in self.resolution.get().split("×"))
        return AppSettings(mode="simulate" if self.source.get().startswith("Simulation") else "usb",
                           width=width, height=height, fps=int(self.fps.get()), codec=self.codec.get(),
                           bitrate=self.bitrate.get(), buffer_size=int(self.buffer.get()), rotation=int(self.rotation.get()),
                           encoder=self.encoder.get() if self.codec.get() == "h264" else "auto",
                           **{name: value.get() for name, value in self.variables.items()}).validate()

    def _set_active(self, active):
        for widget, normal in self.editable:
            widget.configure(state="disabled" if active else normal)
        self.start_button.configure(state="disabled" if active else "normal")
        self.stop_button.configure(state="normal" if active else "disabled")

    def _start(self):
        if self.busy or self.controller:
            return
        try:
            settings = self._read_settings()
            if self.record.get() and not self.recording_path:
                self._choose_file()
                if not self.recording_path:
                    return
            self.settings = settings
            if not self.smoke:
                save_settings(settings)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Cannot start capture", str(exc), parent=self.root)
            return
        self.busy = True
        self._set_active(True)
        self.status.set("Connecting…")
        self.notice.set("Initializing capture and output backends…")
        logging.getLogger("canon_webcam").setLevel(logging.DEBUG if settings.debug_logging else logging.INFO)
        # Read Tk variables on the GUI thread only.
        record_path = self.recording_path if self.record.get() else None
        def run():
            controller = None
            try:
                from .runtime import CaptureController, CaptureOptions
                values = asdict(settings)
                values.pop("debug_logging")
                controller = CaptureController(CaptureOptions(**values, recording=record_path))
                controller.start()
                self.events.put(("started", controller))
            except Exception as exc:
                if controller is not None:
                    controller.stop()
                self.events.put(("error", str(exc)))
        threading.Thread(target=run, daemon=True, name="gui-connect").start()

    def _stop(self):
        if self.busy:
            return
        if self.controller is None:
            if self.closing:
                self.root.destroy()
            return
        self.busy = True
        controller = self.controller
        self.controller = None
        self.stop_button.configure(state="disabled")
        self.status.set("Disconnecting…")
        def run():
            try:
                controller.stop()
                self.events.put(("stopped", None))
            except Exception as exc:
                self.events.put(("error", str(exc)))
        threading.Thread(target=run, daemon=True, name="gui-disconnect").start()

    def _poll(self):
        while True:
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            self.busy = False
            if kind == "started":
                self.controller = value
                self.notice.set("Synthetic source active." if self.settings.mode == "simulate" else
                                "USB viewport capture is experimental. Report problems with diagnostic logs.")
                if self.closing:
                    self._stop()
            else:
                self._set_active(False)
                self.status.set("Disconnected" if kind == "stopped" else "Capture failed")
                if kind == "error":
                    self.notice.set(str(value))
                if self.closing:
                    self.root.destroy()
                    return
        if self.controller is not None:
            try:
                info = self.controller.snapshot()
                self.status.set(f"{'SIMULATION · ' if self.settings.mode == 'simulate' else ''}{info.get('state', 'Capturing')}")
                if info.get("error"):
                    self.notice.set(str(info["error"]))
                self.stats.set(
                    f"Actual source: {info.get('source_width', '—')} × {info.get('source_height', '—')}    "
                    f"Output: {info.get('output_width', '—')} × {info.get('output_height', '—')}\n"
                    f"FPS: {info.get('fps', 0):.1f}    Dropped: {info.get('dropped', 0)}    "
                    f"USB payload: {info.get('usb_mbps', 0):.2f} Mbps    Reconnects: {info.get('reconnects', 0)}\n"
                    f"Virtual camera: {info.get('virtual_camera', False)}    Recording: {info.get('recording', False)}\n"
                    f"Encoder: {info.get('encoder', '—')}    Encoded: {info.get('encoded_mbps', 0):.2f} Mbps    "
                    f"Output dropped: {info.get('output_dropped', 0)}\n"
                    f"Firmware: {info.get('firmware', 'Not retrieved')}    Protocol: {info.get('protocol', '—')}\n"
                    f"Encoder fallback: {info.get('encoder_fallback') or 'None'}")
                frame = self.controller.poll_frame()
                if frame is not None:
                    from PIL import Image, ImageTk
                    picture = Image.fromarray(frame.rgb, "RGB")
                    picture.thumbnail((max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())))
                    self.preview_image = ImageTk.PhotoImage(picture)
                    self.canvas.delete("all")
                    self.canvas.create_image(self.canvas.winfo_width() // 2, self.canvas.winfo_height() // 2,
                                             image=self.preview_image, anchor="center")
            except Exception as exc:
                self.notice.set(f"Preview/status error: {exc}")
        self.poll_id = self.root.after(33, self._poll)

    def _close(self):
        if self.closing:
            return
        self.closing = True
        self.notice.set("Stopping capture and finalizing the recording…")
        if not self.busy:
            self._stop()


def _media_self_test():
    """Validate packaged optional imports and both actual host codec paths."""
    import importlib
    import tempfile
    from pathlib import Path
    import av
    import numpy as np
    from .media import EncodingSettings, VideoRecorder
    imports = ("usb.core", "usb.backend.libusb1", "PIL.Image", "PIL.ImageTk", "pyvirtualcam")
    for name in imports:
        importlib.import_module(name)
    # Check the native library loader without initializing a physical USB bus.
    # CI containers can have no USB bus even when the bundled DLL is correct.
    import ctypes
    import libusb_package
    library = libusb_package.find_library("usb-1.0")
    if not library:
        raise RuntimeError("Bundled libusb library could not be located")
    ctypes.CDLL(library)
    reports = {}
    with tempfile.TemporaryDirectory(prefix="canon-webcam-smoke-") as directory:
        for codec in ("h264", "mjpeg"):
            path = Path(directory) / f"synthetic-{codec}.mkv"
            settings = EncodingSettings(width=64, height=48, fps=24, codec=codec, bitrate_mbps=2)
            with VideoRecorder(path, settings) as recorder:
                for index in range(12):
                    image = np.zeros((48, 64, 3), dtype=np.uint8)
                    image[:, index:index + 12] = (230, 80, 30)
                    recorder.write(image, (index * 1_000_000_000 + 23) // 24)
                encoder = recorder.encoder_name
            with av.open(str(path)) as encoded:
                frames = list(encoded.decode(video=0))
            if len(frames) != 12 or any((f.width, f.height) != (64, 48) for f in frames):
                raise RuntimeError(f"{codec} roundtrip returned invalid frame count/dimensions")
            reports[codec] = {"decoded_frames": len(frames), "encoder": encoder, "bytes": path.stat().st_size}
    return {"codecs": reports, "imports": list(imports), "libusb_library": "dynamic link passed; USB bus not initialized",
            "virtual_camera_backend": "import only; no virtual device opened"}


def self_test(report_path):
    """Exercise frozen application imports and synthetic capture without a display."""
    import json
    from pathlib import Path
    import time
    from .runtime import CaptureController, CaptureOptions
    report = {"status": "failed", "source": "synthetic", "hardware_verified": False}
    controller = None
    try:
        controller = CaptureController(CaptureOptions(mode="simulate"))
        controller.start()
        frames = 0
        first_timestamp = last_timestamp = None
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and frames < 12:
            frame = controller.poll_frame()
            if frame is None:
                error = controller.snapshot().get("error")
                if error:
                    raise RuntimeError(error)
                time.sleep(.01)
                continue
            if tuple(frame.rgb.shape) != (frame.height, frame.width, 3):
                raise RuntimeError("Unexpected RGB preview shape")
            if last_timestamp is not None and frame.timestamp_ns <= last_timestamp:
                raise RuntimeError("Non-monotonic capture timestamps")
            first_timestamp = first_timestamp or frame.timestamp_ns
            last_timestamp = frame.timestamp_ns
            frames += 1
        if frames < 12:
            raise RuntimeError(f"Only received {frames} simulated frames")
        report.update(status="passed", simulated_frames=frames,
                      elapsed_seconds=(last_timestamp - first_timestamp) / 1e9,
                      statistics=controller.snapshot(), media=_media_self_test())
    except Exception as exc:
        report["error"] = str(exc)
    finally:
        if controller is not None:
            try:
                controller.stop()
            except Exception as exc:
                report.update(status="failed", error=f"Capture cleanup failed: {exc}")
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["status"] == "passed" else 1


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Experimental Canon CHDK viewport webcam")
    parser.add_argument("--self-test", action="store_true", help="Run headless synthetic capture smoke test")
    parser.add_argument("--gui-smoke", action="store_true", help="Open GUI, run synthetic preview and exit automatically")
    parser.add_argument("--screenshot", help="Optional screenshot PNG path for GUI smoke test")
    parser.add_argument("--report", default="self-test.json", help="Self-test JSON report path")
    args = parser.parse_args(argv)
    from logging.handlers import RotatingFileHandler
    handlers = [logging.StreamHandler()]
    try:
        log_path = default_settings_path().parent / "logs" / "canon-webcam.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=3, encoding="utf-8"))
    except OSError:
        pass  # Logging to stderr remains available when the profile is read-only.
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.self_test:
        return self_test(args.report)
    global tk, filedialog, messagebox, ttk
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    root = tk.Tk()
    app = WebcamApp(root, smoke=args.gui_smoke)
    report = None
    if args.gui_smoke:
        import json
        from pathlib import Path
        import time
        report = {"status": "failed", "source": "synthetic", "hardware_verified": False}
        deadline = time.monotonic() + 12
        def check_preview():
            error = app.controller.snapshot().get("error") if app.controller else None
            if error:
                report["error"] = error
                app._close()
            elif app.controller and app.preview_image is not None and app.controller.snapshot()["frames"] >= 12:
                try:
                    if args.screenshot:
                        from PIL import ImageGrab
                        root.update_idletasks()
                        path = Path(args.screenshot)
                        path.parent.mkdir(parents=True, exist_ok=True)
                        bounds = (root.winfo_rootx(), root.winfo_rooty(),
                                  root.winfo_rootx() + root.winfo_width(),
                                  root.winfo_rooty() + root.winfo_height())
                        ImageGrab.grab(bbox=bounds).save(path)
                    report.update(status="passed", statistics=app.controller.snapshot(), gui_preview=True)
                except Exception as exc:
                    report["error"] = str(exc)
                app._close()
            elif time.monotonic() > deadline:
                report["error"] = app.notice.get() or "GUI preview timed out"
                app._close()
            else:
                root.after(50, check_preview)
        root.after(100, app._start)
        root.after(150, check_preview)
    root.mainloop()
    if report is not None:
        path = Path(args.report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return 0 if report["status"] == "passed" else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
