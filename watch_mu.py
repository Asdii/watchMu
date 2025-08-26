# watch_mu.py
import time, argparse, os, shutil, cv2, numpy as np, psutil, win32gui, win32process, traceback
from threading import Lock
from skimage.metrics import structural_similarity as ssim
import winsound, ctypes

try:
    from windows_capture import WindowsCapture, Frame, InternalCaptureControl
except ImportError:
    print("[ERROR] Falta 'windows-capture'. Instala: pip install windows-capture opencv-python numpy psutil pywin32 scikit-image")
    raise SystemExit(1)

# ==== Utilidades ====
def _msgbox(text, title="Watch MU"):
    try:
        MB_ICONINFO = 0x40
        MB_SETFOREGROUND = 0x00010000
        MB_TOPMOST = 0x00040000
        ctypes.windll.user32.MessageBoxW(None, str(text), str(title), MB_ICONINFO | MB_SETFOREGROUND | MB_TOPMOST)
    except Exception:
        pass

def alert_user(msg="¡Item encontrado!", attacked=False):
    print(attacked)
    try:
        if attacked:
            wav_path = os.path.join(os.path.dirname(__file__), "attacked.wav")
        else:
            wav_path = os.path.join(os.path.dirname(__file__), "alert.wav")
        if os.path.exists(wav_path):
            winsound.PlaySound(wav_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
    except Exception:
        pass
    _msgbox(msg, "Watch MU")

def find_hwnd_by_title(title_contains: str):
    title_contains = title_contains.lower()
    out=[]
    def enum_handler(hwnd,_):
        if not win32gui.IsWindowVisible(hwnd): return
        t=win32gui.GetWindowText(hwnd) or ""
        if title_contains in t.lower(): out.append(hwnd)
    win32gui.EnumWindows(enum_handler, None)
    return out[0] if out else None

def find_hwnd_by_process_name(proc_name_contains:str):
    proc_name_contains=proc_name_contains.lower()
    out=[]
    def enum_handler(hwnd,_):
        if not win32gui.IsWindowVisible(hwnd): return
        try:
            _,pid=win32process.GetWindowThreadProcessId(hwnd)
            p=psutil.Process(pid)
            if proc_name_contains in p.name().lower(): out.append(hwnd)
        except: pass
    win32gui.EnumWindows(enum_handler,None)
    return out[0] if out else None

def parse_scales(s:str):
    try:
        vals=[float(x) for x in s.split(",") if x.strip()]
        return [v for v in vals if 0.5<=v<=2.0] or [1.00]
    except:
        return [1.00]

def make_tpl_and_mask(path: str):
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        return None, None, None
    return img, None, None

def hist_similarity(img1, img2):
    g1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY) if (img1.ndim==3 and img1.shape[2]==3) else img1
    g2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY) if (img2.ndim==3 and img2.shape[2]==3) else img2
    h1 = cv2.calcHist([g1],[0],None,[256],[0,256])
    h2 = cv2.calcHist([g2],[0],None,[256],[0,256])
    cv2.normalize(h1,h1); cv2.normalize(h2,h2)
    return cv2.compareHist(h1,h2,cv2.HISTCMP_CORREL)

# ==== Main ====

def main():
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--title", default="MU")
        ap.add_argument("--proc", default=None)
        ap.add_argument("--template", default=None, help="Plantilla PNG única")
        ap.add_argument("--items", default=None, help="Carpeta con múltiples PNG")
        ap.add_argument("--threshold", type=float, default=0.90)
        ap.add_argument("--fps", type=float, default=1.0)
        ap.add_argument("--hits", default="hits")
        ap.add_argument("--scales", default="1.00")
        ap.add_argument("--window_number", default=1)
        ap.add_argument("--debug", action="store_true")
        args = ap.parse_args()

        # --- Ventana ---
        hwnd = find_hwnd_by_title(args.title) if args.title else None
        if not hwnd and args.proc: hwnd = find_hwnd_by_process_name(args.proc)
        if not hwnd:
            print("No encontré la ventana. Prueba --title 'MU' o --proc 'main.exe'"); return

        try:
            l,t,r,b=win32gui.GetClientRect(hwnd); w,h=r-l,b-t
        except: w=h=-1
        print(f"HWND={hwnd} size={w}x{h if h>=0 else '?'}")

        # --- Plantillas ---
        templates = {}
        if args.template:
            tpl_path = os.path.abspath(args.template)
            if not os.path.exists(tpl_path):
                print("[ERROR] No existe la plantilla única"); return
            g,_,_ = make_tpl_and_mask(tpl_path)
            templates[os.path.basename(tpl_path)] = (g,None,None)
        elif args.items:
            folder = os.path.abspath(args.items)
            if not os.path.isdir(folder):
                print("[ERROR] Carpeta inválida"); return
            for f in os.listdir(folder):
                if f.lower().endswith(".png"):
                    g,_,_ = make_tpl_and_mask(os.path.join(folder,f))
                    if g is not None: templates[f] = (g,None,None)
            if not templates:
                print("[ERROR] No se cargó ninguna plantilla desde /items"); return
        else:
            print("[ERROR] Debes usar --template o --items"); return

        print(f"[INFO] Plantillas cargadas: {list(templates.keys())}")

        scales = parse_scales(args.scales)
        period = 1.0 / max(args.fps, 0.1)
        tmp_png = os.path.abspath(f"_wgc_tmp_{args.window_number}.png")
        os.makedirs(args.hits, exist_ok=True)

        cap = WindowsCapture(cursor_capture=False, monitor_index=None, window_name=win32gui.GetWindowText(hwnd) or args.title)
        
        was_on_hold = False
        last_proc_ts = 0.0
        proc_lock = Lock()
        active_hits = {name: False for name in templates}

        def process_png(path_png: str):
            nonlocal was_on_hold
            nonlocal last_proc_ts
            now = time.time()
            if now - last_proc_ts < period: return
            if not proc_lock.acquire(blocking=False): return
            try:
                last_proc_ts = now
                img = cv2.imread(path_png, cv2.IMREAD_UNCHANGED)
                if img is None: return

                # asegurar BGR (si viene con alpha)
                if img.ndim == 3 and img.shape[2] == 4:
                    frame_color = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                else:
                    frame_color = img

                for name,(tpl_color_base,_,_) in templates.items():
                    best_score, best_loc, best_size = 0.0, None, (0,0)
                    for s in scales:
                        interp = cv2.INTER_AREA if s<1.0 else cv2.INTER_CUBIC
                        tpl_c = cv2.resize(tpl_color_base, None, fx=s, fy=s, interpolation=interp) if s!=1.0 else tpl_color_base
                        th,tw = tpl_c.shape[:2]
                        if th<1 or tw<1 or th>frame_color.shape[0] or tw>frame_color.shape[1]:
                            continue
                        res = cv2.matchTemplate(frame_color, tpl_c, cv2.TM_CCOEFF_NORMED)
                        _, score, _, loc = cv2.minMaxLoc(res)
                        if score > best_score:
                            best_score, best_loc, best_size = score, loc, (tw,th)

                    if best_loc is not None and best_score >= args.threshold:
                        x,y = best_loc
                        roi = frame_color[y:y+best_size[1], x:x+best_size[0]]
                        roi_resized = cv2.resize(roi, (tpl_color_base.shape[1], tpl_color_base.shape[0]))
                        roi_gray = cv2.cvtColor(roi_resized, cv2.COLOR_BGR2GRAY)
                        tpl_gray = cv2.cvtColor(tpl_color_base, cv2.COLOR_BGR2GRAY)
                        ssim_val = ssim(tpl_gray, roi_gray)
                        hist_val = hist_similarity(tpl_color_base, roi_resized)

                        if ssim_val >= 0.85 and hist_val >= 0.5:
                            if not active_hits[name]:
                                if name == "sd.png":
                                    was_on_hold = True
                                if name != "sd.png": print(f"[HIT] {name} score={best_score:.3f}, ssim={ssim_val:.3f}, hist={hist_val:.3f}")
                                ts=time.strftime("%Y%m%d_%H%M%S")
                                out_path=os.path.join(args.hits, f"{name}_{ts}.png")
                                try:
                                    if name != "sd.png": cv2.imwrite(out_path, frame_color)
                                    if name != "sd.png": print(f"[SAVE] {out_path}")
                                except Exception as _:
                                    if args.debug: print(f"[WARN] No pude guardar {out_path}")
                                if name != "sd.png": alert_user(f"{name.replace('.png', '').replace('_', ' ').capitalize()} encontrado en ventana: {args.window_number}", False)
                                active_hits[name]=True
                            else:
                                if args.debug: print(f"[HOLD] {name}")
                        else:
                            if args.debug: print(f"[MISS] {name} score={best_score:.3f}, ssim={ssim_val:.3f}, hist={hist_val:.3f}")
                            active_hits[name]=False
                    else:
                        if args.debug: print(f"[MISS] {name} mejor score={best_score:.3f}")
                        active_hits[name]=False
                        if was_on_hold and name == "sd.png":
                            alert_user(f"¡¡Nos atacan!! Ventana: {args.window_number}", True)
                            was_on_hold = False
            finally:
                try:
                    if os.path.exists(path_png): os.remove(path_png)
                except: pass
                proc_lock.release()

        @cap.event
        def on_frame_arrived(frame: Frame, ctl: InternalCaptureControl):
            try:
                frame.save_as_image(tmp_png)
                process_png(tmp_png)
            except Exception as e:
                if args.debug: print(f"[WARN] {e}")

        @cap.event
        def on_closed():
            print("[INFO] Ventana cerrada. Terminando…"); os._exit(0)

        print("[INFO] Iniciando captura…"); cap.start(); print("[OK] Captura iniciada.")
        while True: time.sleep(1)

    except KeyboardInterrupt:
        pass
    except Exception:
        print("\n[EXCEPTION]"); traceback.print_exc()

if __name__=="__main__":
    main()
