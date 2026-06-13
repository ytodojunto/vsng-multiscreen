"""
VSNG MultiScreen Replicator
============================
Replica la ventana "External Camera" de Virtual Sailor NG
en hasta 3 monitores adicionales.

Requisitos:
    pip install pywin32 pillow screeninfo

Uso:
    python vsng_multiscreen.py
"""

import sys
import time
import tkinter as tk
from tkinter import ttk, messagebox

try:
    import win32gui
    import win32ui
    import win32con
    from ctypes import windll
except ImportError:
    print("ERROR: ejecutá:  pip install pywin32")
    sys.exit(1)

try:
    from PIL import Image, ImageTk
except ImportError:
    print("ERROR: ejecutá:  pip install pillow")
    sys.exit(1)

try:
    from screeninfo import get_monitors
except ImportError:
    print("ERROR: ejecutá:  pip install screeninfo")
    sys.exit(1)


FPS_TARGET   = 20
FRAME_MS     = 1000 // FPS_TARGET
BORDER_COLOR = "#00aaff"
BG_COLOR     = "#0a0a14"


# ── Captura Win32 ────────────────────────────────────────────────────────────

def capture_hwnd(hwnd):
    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        w = right - left
        h = bottom - top
        if w <= 0 or h <= 0:
            return None

        hwnd_dc = win32gui.GetWindowDC(hwnd)
        mfc_dc  = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()
        bmp     = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(mfc_dc, w, h)
        save_dc.SelectObject(bmp)

        result = windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 3)

        bmp_info = bmp.GetInfo()
        bmp_str  = bmp.GetBitmapBits(True)
        img = Image.frombuffer(
            "RGB",
            (bmp_info["bmWidth"], bmp_info["bmHeight"]),
            bmp_str, "raw", "BGRX", 0, 1
        )

        save_dc.DeleteDC()
        mfc_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwnd_dc)
        win32gui.DeleteObject(bmp.GetHandle())

        return img if result else None
    except Exception:
        return None


def find_vsng_windows():
    """
    Busca TODAS las ventanas visibles de VSNG.
    Prioriza 'External Camera' pero también lista cualquier
    otra ventana del proceso vsng.exe
    """
    results = []

    def _cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return
        title_lower = title.lower()

        # Palabras clave de ventanas VSNG conocidas
        keywords = [
            "external camera", "external screen",
            "radar", "conning", "gps", "chart",
            "virtual sailor", "depth", "instrument"
        ]
        if any(kw in title_lower for kw in keywords):
            rect = win32gui.GetWindowRect(hwnd)
            w = rect[2] - rect[0]
            h = rect[3] - rect[1]
            if w > 100 and h > 100:
                results.append({
                    "hwnd":  hwnd,
                    "title": title,
                    "w": w, "h": h
                })

    win32gui.EnumWindows(_cb, None)
    return results


def get_monitors():
    from screeninfo import get_monitors as _gm
    monitors = []
    for m in _gm():
        monitors.append({
            "x": m.x, "y": m.y,
            "w": m.width, "h": m.height,
            "name": m.name or f"Monitor {len(monitors)+1}"
        })
    return monitors


# ── Ventana replicadora ──────────────────────────────────────────────────────

class ReplicaWindow:
    def __init__(self, master, monitor, hwnd, title, index):
        self.hwnd    = hwnd
        self.running = True

        self.win = tk.Toplevel(master)
        self.win.title(f"VSNG Cam {index+1} │ {title}")
        self.win.configure(bg=BG_COLOR)
        self.win.geometry(
            f"{monitor['w']}x{monitor['h']}+{monitor['x']}+{monitor['y']}"
        )

        # Barra superior
        bar = tk.Frame(self.win, bg=BORDER_COLOR, height=28)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Label(bar, text=f"  ▶  {title}  —  Pantalla {index+1}",
                 bg=BORDER_COLOR, fg="white",
                 font=("Consolas", 10, "bold")).pack(side="left")
        tk.Button(bar, text="✕ Cerrar",
                  bg="#aa0022", fg="white",
                  font=("Consolas", 9), relief="flat",
                  command=self.stop).pack(side="right", padx=4, pady=2)

        # Canvas
        self.canvas = tk.Canvas(self.win, bg="black",
                                highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self._img_ref = None

        # Status
        self.status = tk.StringVar(value="Conectando...")
        tk.Label(self.win, textvariable=self.status,
                 bg="#050510", fg="#4488cc",
                 font=("Consolas", 8), anchor="w").pack(fill="x", padx=4)

        self.win.protocol("WM_DELETE_WINDOW", self.stop)
        self._update()

    def _update(self):
        if not self.running:
            return
        try:
            if not win32gui.IsWindow(self.hwnd):
                self.status.set("⚠  Ventana VSNG cerrada")
            else:
                img = capture_hwnd(self.hwnd)
                if img:
                    cw = self.canvas.winfo_width()
                    ch = self.canvas.winfo_height()
                    if cw > 1 and ch > 1:
                        img = img.resize((cw, ch), Image.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    self.canvas.create_image(0, 0, anchor="nw", image=photo)
                    self._img_ref = photo
                    self.status.set(
                        f"✔  {img.width}×{img.height}  @{FPS_TARGET}fps  "
                        f"{time.strftime('%H:%M:%S')}"
                    )
                else:
                    self.status.set("⚠  Sin imagen — ¿ventana minimizada?")
        except Exception as e:
            self.status.set(f"Error: {e}")

        if self.running:
            self.win.after(FRAME_MS, self._update)

    def stop(self):
        self.running = False
        try:
            self.win.destroy()
        except Exception:
            pass


# ── Panel de control ─────────────────────────────────────────────────────────

class ControlPanel:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("VSNG MultiScreen")
        self.root.configure(bg=BG_COLOR)
        self.root.geometry("620x440")
        self.root.resizable(False, False)

        self._vsng_wins = []
        self._monitors  = []
        self._replicas  = []
        self._rows      = []

        self._build_ui()
        self._refresh()

    def _build_ui(self):
        tk.Label(self.root,
                 text="VSNG  MultiScreen  Replicator",
                 bg=BG_COLOR, fg=BORDER_COLOR,
                 font=("Consolas", 15, "bold")).pack(pady=(14, 2))

        tk.Label(self.root,
                 text="Seleccioná la ventana VSNG y el monitor destino para cada réplica",
                 bg=BG_COLOR, fg="#667788",
                 font=("Consolas", 8)).pack()

        tk.Frame(self.root, bg=BORDER_COLOR, height=1).pack(
            fill="x", padx=20, pady=8)

        grid = tk.Frame(self.root, bg=BG_COLOR)
        grid.pack(fill="x", padx=24)

        for col, txt in enumerate(["#", "Ventana VSNG", "Monitor destino", "Estado"]):
            tk.Label(grid, text=txt, bg=BG_COLOR, fg="#778899",
                     font=("Consolas", 8, "bold")).grid(
                row=0, column=col, padx=6, pady=2, sticky="w")

        for i in range(3):
            win_var = tk.StringVar()
            mon_var = tk.StringVar()

            tk.Label(grid, text=f"  {i+1}", bg=BG_COLOR, fg=BORDER_COLOR,
                     font=("Consolas", 11, "bold")).grid(row=i+1, column=0)

            win_cb = ttk.Combobox(grid, textvariable=win_var,
                                  width=26, state="readonly",
                                  font=("Consolas", 9))
            mon_cb = ttk.Combobox(grid, textvariable=mon_var,
                                  width=20, state="readonly",
                                  font=("Consolas", 9))
            lbl = tk.Label(grid, text="● libre", bg=BG_COLOR, fg="#445555",
                           font=("Consolas", 9))

            win_cb.grid(row=i+1, column=1, padx=6, pady=5, sticky="ew")
            mon_cb.grid(row=i+1, column=2, padx=6, pady=5, sticky="ew")
            lbl.grid   (row=i+1, column=3, padx=6)

            self._rows.append({
                "win_cb": win_cb, "win_var": win_var,
                "mon_cb": mon_cb, "mon_var": mon_var,
                "lbl": lbl
            })

        grid.columnconfigure(1, weight=2)
        grid.columnconfigure(2, weight=1)

        tk.Frame(self.root, bg="#1a2a3a", height=1).pack(
            fill="x", padx=20, pady=10)

        # Botones
        bf = tk.Frame(self.root, bg=BG_COLOR)
        bf.pack()
        s = {"font": ("Consolas", 10, "bold"), "relief": "flat",
             "padx": 16, "pady": 6, "cursor": "hand2"}

        tk.Button(bf, text="⟳  Refrescar",
                  bg="#1a3a55", fg="white",
                  command=self._refresh, **s).pack(side="left", padx=5)
        tk.Button(bf, text="▶  Iniciar",
                  bg="#005533", fg="white",
                  command=self._launch, **s).pack(side="left", padx=5)
        tk.Button(bf, text="■  Detener todo",
                  bg="#550022", fg="white",
                  command=self._stop_all, **s).pack(side="left", padx=5)

        self._status = tk.StringVar(value="Listo.")
        tk.Label(self.root, textvariable=self._status,
                 bg=BG_COLOR, fg="#446688",
                 font=("Consolas", 8)).pack(pady=(8, 4))

        # Tip
        tk.Label(self.root,
                 text="💡  Tip: en VSNG abrí View → External Camera antes de iniciar",
                 bg=BG_COLOR, fg="#334455",
                 font=("Consolas", 8)).pack(pady=(0, 10))

    def _refresh(self):
        self._vsng_wins = find_vsng_windows()
        self._monitors  = get_monitors()

        win_opts = [f"{w['title']}  ({w['w']}×{w['h']})"
                    for w in self._vsng_wins]
        mon_opts = [f"{m['name']}  {m['w']}×{m['h']}  @{m['x']},{m['y']}"
                    for m in self._monitors]

        for i, row in enumerate(self._rows):
            row["win_cb"]["values"] = win_opts or ["— abrí VSNG primero —"]
            row["mon_cb"]["values"] = mon_opts

            # Autoseleccionar "External Camera" si existe
            found = False
            for j, w in enumerate(self._vsng_wins):
                if "external camera" in w["title"].lower():
                    row["win_var"].set(win_opts[j])
                    found = True
                    break
            if not found and win_opts:
                row["win_var"].set(win_opts[0])

            # Autoseleccionar monitor i+1 (evitar el principal)
            if len(mon_opts) > i + 1:
                row["mon_var"].set(mon_opts[i + 1])
            elif mon_opts:
                row["mon_var"].set(mon_opts[0])

        self._status.set(
            f"Detectado: {len(self._vsng_wins)} ventana(s) VSNG  │  "
            f"{len(self._monitors)} monitor(es)"
        )

    def _launch(self):
        self._stop_all()
        launched = 0

        for i, row in enumerate(self._rows):
            wt = row["win_var"].get()
            mt = row["mon_var"].get()
            if not wt or "abrí VSNG" in wt or not mt:
                continue

            opts = list(row["win_cb"]["values"])
            if wt not in opts:
                continue
            wi = opts.index(wt)
            if wi >= len(self._vsng_wins):
                continue

            wd = self._vsng_wins[wi]
            mi = list(row["mon_cb"]["values"]).index(mt)
            md = self._monitors[mi]

            r = ReplicaWindow(self.root, md, wd["hwnd"], wd["title"], i)
            self._replicas.append(r)
            row["lbl"].config(text=f"● activo", fg="#44ff88")
            launched += 1

        if launched:
            self._status.set(f"✔  {launched} réplica(s) activa(s)")
        else:
            messagebox.showwarning(
                "Sin ventanas",
                "No se encontró la ventana 'External Camera' de VSNG.\n\n"
                "Pasos:\n"
                "1. Abrí Virtual Sailor NG\n"
                "2. Cargá el Sakarya\n"
                "3. En el menú: View → External Camera\n"
                "4. Volvé aquí y presioná Refrescar"
            )

    def _stop_all(self):
        for r in self._replicas:
            try:
                r.stop()
            except Exception:
                pass
        self._replicas.clear()
        for row in self._rows:
            row["lbl"].config(text="● libre", fg="#445555")
        self._status.set("Detenido.")

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        self._stop_all()
        self.root.destroy()


if __name__ == "__main__":
    try:
        windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    ControlPanel().run()
