"""WeChat AI Auto-Reply Bot v16 - Red badge + real click + context"""
import json, time, os, ctypes, re, numpy as np
from datetime import datetime
from pathlib import Path
from collections import OrderedDict
from ctypes import wintypes

WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0201, 0x0202
VK_RETURN, VK_ESCAPE, VK_END, VK_CONTROL = 0x0D, 0x1B, 0x23, 0x11

user32 = ctypes.windll.user32
chat_history, replied = {}, OrderedDict()
reply_count = 0
CONFIG_FILE = Path(__file__).parent / "config.json"
LOG_FILE = Path(__file__).parent / "bot_log.txt"
last_content = {}

def log(msg):
    s = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(s, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(s + "\n")
    except:
        pass

def post_key(hwnd, vk):
    user32.PostMessageW(hwnd, WM_KEYDOWN, vk, 0)
    time.sleep(0.03)
    user32.PostMessageW(hwnd, WM_KEYUP, vk, 0)

DEFAULT_CONFIG = {
    "deepseek_api_key": "sk-YOUR_KEY_HERE", "deepseek_model": "deepseek-chat",
    "deepseek_base_url": "https://api.deepseek.com", "whitelist_contacts": [],
    "blocklist": [], "auto_reply_prefix": "", "scan_interval": 5,
    "cooldown_seconds": 60, "auto_send": True, "max_replies_per_session": 20,
    "system_prompt": "你是友好的微信助手。用简洁自然的中文回复，像朋友聊天一样，每次回复控制在3句话以内。"
}

def load_cfg():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    return DEFAULT_CONFIG.copy()

class WeChatWin:
    def find(self):
        hwnd = [0]
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
        def cb(h, _):
            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(h, cls_buf, 256)
            if cls_buf.value not in ("Qt51514QWindowIcon", "WeChatMainWndForPC", "WeChatMainWnd"):
                return True
            l = user32.GetWindowTextLengthW(h)
            t_buf = ctypes.create_unicode_buffer(l + 1)
            user32.GetWindowTextW(h, t_buf, l + 1)
            if "\u5fae\u4fe1" in t_buf.value:
                rect = wintypes.RECT()
                user32.GetWindowRect(h, ctypes.byref(rect))
                if rect.right - rect.left > 400:
                    hwnd[0] = h
            return True
        user32.EnumWindows(WNDENUMPROC(cb), 0)
        self.hwnd = hwnd[0]
        self._w = self._h = 0
        if self.hwnd:
            rect = wintypes.RECT()
            user32.GetWindowRect(self.hwnd, ctypes.byref(rect))
            self._w = rect.right - rect.left
            self._h = rect.bottom - rect.top
        return self.hwnd != 0

    @property
    def width(self): return self._w
    @property
    def height(self): return self._h

    def capture(self):
        from PIL import ImageGrab
        hwnd = self.hwnd
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)
        user32.ShowWindow(hwnd, 4)
        user32.SetWindowPos(hwnd, -1, 10, 10, 738, 648, 0x0010)
        time.sleep(0.12)
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        self._w = rect.right - rect.left
        self._h = rect.bottom - rect.top
        if self._w <= 0 or self._h <= 0:
            return None
        return ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True)

    def ensure_visible(self):
        if user32.IsIconic(self.hwnd):
            user32.ShowWindow(self.hwnd, 9)
        user32.ShowWindow(self.hwnd, 4)
        user32.SetWindowPos(self.hwnd, -1, 10, 10, 738, 648, 0x0010)
        time.sleep(0.06)

    def restore_zorder(self):
        user32.SetWindowPos(self.hwnd, -2, 0, 0, 0, 0, 0x0002 | 0x0001 | 0x0010)

class OCR:
    def __init__(self):
        import easyocr
        log("Loading EasyOCR...")
        self.reader = easyocr.Reader(["ch_sim", "en"], gpu=False)
        log("EasyOCR ready")

    def read_with_pos(self, img, min_conf=0.1):
        arr = np.array(img)
        if len(arr.shape) == 2: arr = np.stack([arr]*3, axis=-1)
        elif arr.shape[2] == 4: arr = arr[:,:,:3]
        from PIL import Image
        upscaled = Image.fromarray(arr).resize((arr.shape[1]*2, arr.shape[0]*2), Image.LANCZOS)
        results = self.reader.readtext(np.array(upscaled))
        return [(text, (bbox[0][1]+bbox[2][1])/4.0) for bbox, text, conf in results if conf >= min_conf]

class Scanner:
    UI_NOISE = ["WeChat","微信","通讯录","搜索","语音","视频号","小程序","看一看","搜一搜","直播","朋友圈","公众号","通知中心","订阅号"]
    def __init__(self, win, ocr):
        self.win, self.ocr = win, ocr

    def detect_unread_badges(self):
        img = self.win.capture()
        if img is None: return []
        w = self.win.width; h = self.win.height
        list_w = int(w * 0.30)
        crop = img.crop((0, 30, list_w, h - 10))
        arr = np.array(crop)
        red_mask = (arr[:,:,0] > 160) & (arr[:,:,1] < 90) & (arr[:,:,2] < 90)
        if not red_mask.any(): return []
        red_rows = np.sum(red_mask, axis=1)
        unread_rows = np.where(red_rows > 3)[0]
        if len(unread_rows) == 0: return []
        badges = []
        cs = unread_rows[0]
        for i in range(1, len(unread_rows)):
            if unread_rows[i] - unread_rows[i-1] > 5:
                badges.append(int((cs + unread_rows[i-1])//2 + 30))
                cs = unread_rows[i]
        badges.append(int((cs + unread_rows[-1])//2 + 30))
        return badges

    def get_chat_title(self):
        img = self.win.capture()
        if img is None: return ""
        w = self.win.width
        crop = img.crop((int(w*0.05), 3, int(w*0.60), 32))
        items = self.ocr.read_with_pos(crop, min_conf=0.25)
        valid = [t for t,_ in items if len(t)>=1]
        return valid[0] if valid else ""

    def scroll_to_bottom(self):
        import pyautogui
        self.win.ensure_visible()
        # Click message area to ensure focus after chat switch
        rect = wintypes.RECT()
        user32.GetWindowRect(self.win.hwnd, ctypes.byref(rect))
        mx = rect.left + int(self.win.width * 0.6)
        my = rect.top + int(self.win.height * 0.5)
        pyautogui.click(mx, my)
        time.sleep(0.2)
        # Real End key to scroll
        for _ in range(3):
            pyautogui.press("end")
            time.sleep(0.15)
        time.sleep(0.2)

    def try_read_messages(self):
        self.scroll_to_bottom()
        img = self.win.capture()
        if img is None: return []
        w, h = self.win.width, self.win.height
        msg_l, msg_r = int(w*0.32), w-5
        msg_t, msg_b = 35, h-90
        if msg_b <= msg_t: return []
        crop = img.crop((msg_l, msg_t, msg_r, msg_b))
        items = self.ocr.read_with_pos(crop, min_conf=0.15)
        return [t for t,_ in items if not re.match(r"^\d{1,2}[.:]\d{2}$", t) and len(t)>=1]

class Navigator:
    def __init__(self, win): self.win = win
    def goto_chat(self, y_pos):
        import pyautogui
        self.win.ensure_visible()
        user32.SetForegroundWindow(self.win.hwnd)
        time.sleep(0.1)
        rect = wintypes.RECT()
        user32.GetWindowRect(self.win.hwnd, ctypes.byref(rect))
        pyautogui.click(rect.left + int(self.win.width*0.12), rect.top + y_pos)
        time.sleep(0.3)

class Sender:
    def __init__(self, win): self.win = win
    def send(self, text):
        import pyperclip, pyautogui
        self.win.ensure_visible()
        # Force WeChat to foreground by clicking on it
        rect = wintypes.RECT()
        user32.GetWindowRect(self.win.hwnd, ctypes.byref(rect))
        input_x = rect.left + int(self.win.width * 0.5)
        input_y = rect.top + int(self.win.height * 0.88)
        pyautogui.click(input_x, input_y)
        time.sleep(0.15)
        pyautogui.click(input_x, input_y)  # double-click to ensure focus
        time.sleep(0.2)
        pyperclip.copy(text)
        time.sleep(0.05)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.2)
        pyautogui.press("enter")
        time.sleep(0.1)

class DeepSeek:
    def __init__(self, cfg):
        from openai import OpenAI
        self.client = OpenAI(api_key=cfg["deepseek_api_key"], base_url=cfg["deepseek_base_url"])
        self.model = cfg["deepseek_model"]
        self.system = cfg["system_prompt"]
    def reply(self, msg, chat_key):
        msgs = [{"role": "system", "content": self.system}]
        if chat_key in chat_history:
            msgs.extend(chat_history[chat_key][-6:])
        if msg and msg.strip():
            msgs.append({"role": "user", "content": msg})
        else:
            msgs.append({"role": "user", "content": f"（{chat_key}）发来新消息，请简洁回复。"})
        try:
            r = self.client.chat.completions.create(model=self.model, messages=msgs, temperature=0.7, max_tokens=300)
            rep = r.choices[0].message.content.strip()
            if chat_key not in chat_history: chat_history[chat_key] = []
            chat_history[chat_key].extend([{"role":"user","content":msg or "(新消息)"},{"role":"assistant","content":rep}])
            if len(chat_history[chat_key]) > 12: chat_history[chat_key] = chat_history[chat_key][-12:]
            return rep
        except Exception as e:
            log(f"DeepSeek error: {e}")
            return None

class Bot:
    def __init__(self):
        self.cfg = load_cfg()
        self.win = WeChatWin()
        self.active_chat_y = None
        self.active_chat_hash = None
        self.pending_active_hash = None

    def already_replied(self, chat_key):
        import random
        now = time.time()
        cd = random.randint(20, 35)
        return chat_key in replied and (now - replied[chat_key] < cd)

    def run(self):
        global reply_count
        log("="*50)
        log("  WeChat AI Auto-Reply Bot v16")
        log("  Red badge + real click + 6-msg context")
        log("="*50)
        if not self.win.find():
            log("WeChat not found!"); input(); return
        log(f"WeChat: {self.win.width}x{self.win.height}")
        self.ocr = OCR()
        self.scanner = Scanner(self.win, self.ocr)
        self.nav = Navigator(self.win)
        self.sender = Sender(self.win)
        self.ai = DeepSeek(self.cfg)
        auto_send = self.cfg.get("auto_send", True)
        max_replies = self.cfg.get("max_replies_per_session", 20)
        scan_interval = self.cfg.get("scan_interval", 5)
        log(f"AUTO_SEND: {'ON' if auto_send else 'OFF'} | Cooldown: {self.cfg['cooldown_seconds']}s")
        last_heartbeat = last_scan = 0
        try:
            while True:
                if reply_count >= max_replies: break
                now = time.time()
                if now - last_scan < scan_interval: time.sleep(1); continue
                last_scan = now
                badges = self.scanner.detect_unread_badges()
                if now - last_heartbeat > 20:
                    log(f"Heartbeat ({reply_count}/{max_replies}) unread={len(badges)}")
                    last_heartbeat = now

                # Active chat monitoring: require 2-cycle confirmation
                if self.active_chat_y is not None and not badges:
                    try:
                        chat_key = str(self.active_chat_y)
                        if not self.already_replied(chat_key):
                            self.nav.goto_chat(self.active_chat_y)
                            time.sleep(0.6)
                            self.scanner.scroll_to_bottom()
                            img = self.win.capture()
                            if img:
                                import hashlib
                                w, h = self.win.width, self.win.height
                                crop = img.crop((int(w*0.32), max(35,h-250), w-5, h-90))
                                hh = hashlib.md5(np.array(crop).tobytes()).hexdigest()
                                if self.active_chat_hash and hh != self.active_chat_hash:
                                    if self.pending_active_hash == hh:
                                        # Same new hash 2 cycles -> confirmed
                                        self.pending_active_hash = None
                                        self.active_chat_hash = hh
                                        log(f">>> Active chat changed (confirmed)!")
                                        msgs = self.scanner.try_read_messages()
                                        msg_text = msgs[-1] if msgs else ""
                                        if msg_text and msg_text == last_content.get(chat_key, ""):
                                            log(">> Same content, skip")
                                        else:
                                            last_content[chat_key] = msg_text
                                            if msg_text: log(f">>> Content: {msg_text[:60]}")
                                            rep = self.ai.reply(msg_text, chat_key)
                                            if rep:
                                                if auto_send:
                                                    log(f">>> SEND: {rep[:80]}")
                                                    self.sender.send(rep)
                                                else:
                                                    log(f">>> [PREVIEW] {rep[:80]}")
                                                replied[chat_key] = time.time()
                                                reply_count += 1
                                    else:
                                        # First time seeing change -> pending
                                        self.pending_active_hash = hh
                                        log(f">>> Active chat change pending...")
                                else:
                                    self.active_chat_hash = hh
                                    self.pending_active_hash = None
                    except Exception as e:
                        log(f"Active check error: {e}")

                if not badges: continue
                for y in badges:
                    try:
                        if reply_count >= max_replies: break
                        chat_key = str(y)
                        if self.already_replied(chat_key): continue
                        self.nav.goto_chat(y)
                        time.sleep(0.8)
                        # Click message area to ensure chat fully loaded
                        import pyautogui
                        rect = wintypes.RECT()
                        user32.GetWindowRect(self.win.hwnd, ctypes.byref(rect))
                        pyautogui.click(rect.left + int(self.win.width*0.6), rect.top + int(self.win.height*0.5))
                        time.sleep(0.4)
                        title = self.scanner.get_chat_title()
                        display = title if title else chat_key
                        log(f">>> UNREAD [{display}]!")
                        msgs = self.scanner.try_read_messages()
                        msg_text = msgs[-1] if msgs else ""
                        if msg_text:
                            log(f">>> Content: {msg_text[:60]}")
                        # Skip duplicate content
                        if msg_text and msg_text == last_content.get(chat_key, ""):
                            log(f">>> Same content, skip")
                            continue
                        last_content[chat_key] = msg_text
                        rep = self.ai.reply(msg_text, chat_key)
                        if not rep: continue
                        if auto_send:
                            log(f">>> SEND: {rep[:80]}")
                            self.sender.send(rep)
                        else:
                            log(f">>> [PREVIEW] {rep[:80]}")
                        replied[chat_key] = time.time()
                        reply_count += 1
                        self.active_chat_y = y
                        # Take baseline hash of this chat
                        img = self.win.capture()
                        if img:
                            import hashlib
                            w, h = self.win.width, self.win.height
                            crop = img.crop((int(w*0.32), max(35,h-250), w-5, h-90))
                            self.active_chat_hash = hashlib.md5(np.array(crop).tobytes()).hexdigest()
                    except Exception as e:
                        log(f"ERROR: {e}")
                time.sleep(1)
        except KeyboardInterrupt:
            log("Stopped.")
        finally:
            self.win.restore_zorder()
            log(f"Ended. Replies: {reply_count}")

if __name__ == "__main__":
    Bot().run()
    input("\nPress Enter to exit...")
