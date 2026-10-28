import os, ast, json, time, random, string, shutil, threading, subprocess, operator
import urllib.request, signal, glob
from kivy.core.clipboard import Clipboard
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.screenmanager import ScreenManager, Screen

BG = (0.04, 0.05, 0.09, 1)
PANEL = (0.09, 0.11, 0.17, 1)
KEYBG = (0.14, 0.17, 0.26, 1)
ACC = (0.25, 0.65, 1, 1)
OKC = (0.2, 0.75, 0.45, 1)
Window.clearcolor = BG
Window.softinput_mode = "resize"
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("ANDROID_PRIVATE") or os.path.expanduser("~")
STORE = "/storage/emulated/0"
START = STORE if os.path.isdir(STORE) else DATA

from kivy.core.text import LabelBase
from kivy.utils import escape_markup
import re
ETHI = next((f for f in [
    os.path.join(HERE, "ethi.ttf"),
    "/system/fonts/NotoSansEthiopic-VF.ttf",
    "/system/fonts/NotoSansEthiopic-Regular.otf",
    "/system/fonts/NotoSansEthiopic-Regular.ttf"] if os.path.exists(f)), None)
if ETHI:
    LabelBase.register(name="ethi", fn_regular=ETHI)
_ER = re.compile("([\u1200-\u139f\u2d80-\u2ddf\uab00-\uab2f]+)")
def fx(t):
    t = escape_markup(str(t))
    return _ER.sub(r"[font=ethi]\1[/font]", t) if ETHI else t
FK = {}

try:
    from android.permissions import request_permissions, Permission
    request_permissions([Permission.READ_EXTERNAL_STORAGE,
                         Permission.WRITE_EXTERNAL_STORAGE])
except Exception:
    pass

def jload(name, default):
    try:
        return json.load(open(os.path.join(DATA, name), encoding="utf-8"))
    except Exception:
        return default

def jsave(name, obj):
    json.dump(obj, open(os.path.join(DATA, name), "w", encoding="utf-8"),
              ensure_ascii=False)

# ---------------- Console widget ----------------
class Console(BoxLayout):
    def __init__(self, handler, banner, name=None, **kw):
        super().__init__(orientation="vertical", spacing=dp(3), **kw)
        self.handler = handler
        self.name = name
        self.hist = jload("h_%s.json" % name, [])[-200:] if name else []
        self.i = len(self.hist)
        self.lines, self.raw, self.pend = [fx(banner)], [banner], []
        self.sched = False
        self.ctrl = self.alt = False
        self.buf, self.mark, self.last = None, "", ""
        self._skip = False

        self.out = Label(text="\n".join(self.lines), markup=True,
                         size_hint_y=None, halign="left", valign="top",
                         color=(.6, 1, .6, 1), font_size=dp(14))
        self.out.bind(width=lambda w, v: setattr(w, "text_size", (v, None)),
                      texture_size=lambda w, s: setattr(w, "height", s[1]))
        self.sv = ScrollView()
        self.sv.add_widget(self.out)
        self.add_widget(self.sv)

        self.prev = Label(text="", markup=True, size_hint_y=None,
                          height=dp(28), halign="left", valign="middle",
                          color=(1, 1, 1, 1), font_size=dp(16))
        self.prev.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
        self.add_widget(self.prev)

        keys = [("Esc", self.k_esc), ("Tab", self.k_tab),
                ("Ctrl", self.k_ctrl), ("Alt", self.k_alt),
                ("Home", lambda *_: self.mv("cursor_home")),
                ("End", lambda *_: self.mv("cursor_end")),
                ("<-", lambda *_: self.mv("cursor_left")),
                ("->", lambda *_: self.mv("cursor_right")),
                ("Paste", self.k_paste), ("Copy", self.k_copy),
                ("^C", self.k_int), ("Clear", self.k_clear)]
        krow = BoxLayout(size_hint_x=None, width=len(keys) * dp(68),
                         spacing=dp(3))
        self.kb = {}
        for name, cb in keys:
            b = Button(text=name, size_hint_x=None, width=dp(66),
                       font_size=dp(14), background_normal="",
                       background_color=KEYBG)
            b.bind(on_release=cb)
            krow.add_widget(b)
            self.kb[name] = b
        ks = ScrollView(size_hint_y=None, height=dp(42),
                        do_scroll_x=True, do_scroll_y=False)
        ks.add_widget(krow)
        self.add_widget(ks)

        row = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(4))
        self.inp = TextInput(multiline=False, font_size=dp(16),
                             write_tab=False, use_bubble=True,
                             use_handles=True,
                             background_color=PANEL,
                             foreground_color=((0, 0, 0, 0) if ETHI else (1, 1, 1, 1)),
                             cursor_color=(1, 1, 1, 1))
        self.inp.bind(on_text_validate=self.submit)
        self.inp.bind(text=self.on_text)
        row.add_widget(self.inp)
        for t, d in (("Up", -1), ("Dn", 1)):
            b = Button(text=t, size_hint_x=None, width=dp(48),
                       background_normal="", background_color=ACC)
            b.bind(on_release=lambda _b, d=d: self.recall(d))
            row.add_widget(b)
        self.add_widget(row)

    # ---------- ውጤት ----------
    def write(self, t):
        self.pend.append((str(t), fx(t)))
        if not self.sched:
            self.sched = True
            Clock.schedule_once(self.flush, 0.1)

    def flush(self, dt):
        self.sched = False
        p, self.pend = self.pend, []
        self.raw = (self.raw + [a for a, b in p])[-300:]
        self.lines = (self.lines + [b for a, b in p])[-300:]
        self.out.text = "\n".join(self.lines)
        self.sv.scroll_y = 0

    # ---------- ቁልፎች ----------
    def mv(self, action, ctl=False):
        self.inp.do_cursor_movement(action, control=ctl)
        self.inp.focus = True

    def paint(self):
        for n, on in (("Ctrl", self.ctrl), ("Alt", self.alt)):
            self.kb[n].background_color = OKC if on else KEYBG

    def k_esc(self, *_):
        self.buf = None
        self.inp.text = ""

    def k_ctrl(self, *_):
        self.ctrl = not self.ctrl
        self.alt = False
        self.paint()

    def k_alt(self, *_):
        self.alt = not self.alt
        self.ctrl = False
        self.paint()

    def k_tab(self, *_):
        if self.buf:
            return
        t = self.inp.text
        tok = t.split(" ")[-1]
        base = getattr(self.handler, "cwd", START)
        ms = sorted(glob.glob(os.path.join(base, os.path.expanduser(tok)) + "*"))
        if not ms:
            return
        names = []
        for p in ms:
            rel = p if tok.startswith(("/", "~")) else os.path.relpath(p, base)
            names.append(rel + ("/" if os.path.isdir(p) else ""))
        if len(names) == 1:
            new = names[0]
        else:
            new = os.path.commonprefix(names)
            self.write("  ".join(names[:30]))
        self.inp.text = t[:len(t) - len(tok)] + new
        self.mv("cursor_end")

    def k_paste(self, *_):
        t = (Clipboard.paste() or "").replace("\r", "").strip("\n")
        if not t:
            return
        if "\n" in t:
            self.buf = t
            self.mark = "[ተለጠፈ %d መስመሮች - Enter ለማስኬድ]" % (t.count("\n") + 1)
            self.inp.text = self.mark
        else:
            self.inp.insert_text(t)
        self.inp.focus = True

    def k_copy(self, *_):
        Clipboard.copy("\n".join(self.raw)[-20000:])
        self.write("(ተቀድቷል)")

    def k_int(self, *_):
        f = getattr(self.handler, "interrupt", None)
        if f:
            f()
        self.write("^C")

    def k_clear(self, *_):
        self.lines, self.raw, self.pend = [], [], []
        self.out.text = ""

    def recall(self, d):
        if self.hist:
            self.i = max(0, min(len(self.hist) - 1, self.i + d))
            self.inp.text = self.hist[self.i]

    def upd_prev(self, dt):
        self.prev.text = fx(self.inp.text)

    def combo(self, c, ctrl):
        i = self.inp
        if ctrl:
            if c == "c":
                self.k_int()
            elif c == "l":
                self.k_clear()
            elif c == "a":
                self.mv("cursor_home")
            elif c == "e":
                self.mv("cursor_end")
            elif c == "u":
                i.text = ""
            elif c == "k":
                i.text = i.text[:i.cursor_col]
            elif c == "w":
                s = i.text.rstrip()
                i.text = (s.rsplit(" ", 1)[0] + " ") if " " in s else ""
        else:
            if c == "b":
                self.mv("cursor_left", True)
            elif c == "f":
                self.mv("cursor_right", True)

    def on_text(self, inst, v):
        if self._skip:
            self._skip = False
            return
        if self.buf and v != self.mark:
            self.buf = None
        if (self.ctrl or self.alt) and len(v) == len(self.last) + 1:
            c, ctrl = v[-1].lower(), self.ctrl
            self.ctrl = self.alt = False
            self.paint()
            self._skip = True
            self.inp.text = self.last
            self.combo(c, ctrl)
            return
        self.last = v
        Clock.unschedule(self.upd_prev)
        Clock.schedule_once(self.upd_prev, 0.12)

    def submit(self, *_):
        line = self.buf if self.buf else self.inp.text.strip()
        self.buf = None
        self.inp.text = ""
        Clock.schedule_once(lambda dt: setattr(self.inp, "focus", True), 0.1)
        if not line:
            return
        if "\n" not in line:
            self.hist.append(line)
            if self.name:
                jsave("h_%s.json" % self.name, self.hist[-200:])
        self.i = len(self.hist)
        self.write("› " + line)
        if line in ("አጽዳ", "clear"):
            self.k_clear()
            return
        def job():
            try:
                self.handler(line, self.write)
            except Exception as e:
                self.write("ERR " + str(e))
        threading.Thread(target=job, daemon=True).start()

TERM_HELP = """HABIB SHELL v2
help / እርዳታ    ይህ ዝርዝር
py <ኮድ>        Python ማስኬጃ (py 2+3 · py import os; print(os.getcwd()))
get <url>       ድረ-ገጽ ማውረድ (ጽሑፍ)
edit <ፋይል>      በኤዲተር ትር ክፈት
cd · ወዴት        አቃፊ
ሌላ ማንኛውም sh ትዕዛዝ (ls, cat, cp, mv, rm, ping ...)
ብዙ መስመር: Paste ተጫንና Enter"""

class Term:
    def __init__(self):
        self.cwd = START
        self.proc = None
        self.ns = {}

    def run_py(self, code, w):
        import io, contextlib, traceback
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                try:
                    r = eval(compile(code, "<py>", "eval"), self.ns)
                    if r is not None:
                        print(repr(r))
                except SyntaxError:
                    exec(compile(code, "<py>", "exec"), self.ns)
        except Exception:
            buf.write(traceback.format_exc(limit=1))
        w(buf.getvalue().rstrip() or "(ባዶ)")

    def http_get(self, url, w):
        if not url.startswith("http"):
            url = "https://" + url
        req = urllib.request.Request(url, headers={"User-Agent": "HabibShell/2"})
        with urllib.request.urlopen(req, timeout=30) as r:
            w(r.read(4000).decode("utf-8", "ignore"))

    def edit(self, path):
        p = os.path.abspath(os.path.join(self.cwd, os.path.expanduser(path)))
        app = App.get_running_app()
        Clock.schedule_once(lambda dt: app.open_editor(p))

    def interrupt(self):
        p = self.proc
        if p and p.poll() is None:
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
            except Exception:
                p.terminate()

    def __call__(self, line, w):
        one = "\n" not in line
        if one and line == "ወዴት":
            return w(self.cwd)
        if one and line.split()[0] == "cd":
            p = os.path.expanduser(line[2:].strip() or "~")
            p = os.path.abspath(os.path.join(self.cwd, p))
            if os.path.isdir(p):
                self.cwd = p
                return w(p)
            return w("ERR አቃፊ አልተገኘም")
        if one:
            parts = line.split(None, 1)
            arg = parts[1] if len(parts) > 1 else ""
            if parts[0] in ("help", "እርዳታ"):
                return w(TERM_HELP)
            if parts[0] == "py" and arg:
                return self.run_py(arg, w)
            if parts[0] == "get" and arg:
                return self.http_get(arg, w)
            if parts[0] == "edit" and arg:
                return self.edit(arg)
        p = subprocess.Popen(line, shell=True, cwd=self.cwd,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL, text=True,
                             bufsize=1, start_new_session=True)
        self.proc = p
        for ln in p.stdout:
            w(ln.rstrip("\n"))
        p.wait()
        self.proc = None

class Files:
    def __init__(self):
        self.cwd = START
    def p(self, x):
        return os.path.abspath(os.path.join(self.cwd, os.path.expanduser(x)))
    def __call__(self, line, w):
        a = line.split()
        c, r = a[0], a[1:]
        if c == "cd" and r:
            p = self.p(r[0])
            if os.path.isdir(p):
                self.cwd = p
                return w(p)
            return w("ERR አቃፊ የለም")
        if c == "ፋይሎች":
            p = self.p(r[0]) if r else self.cwd
            for n in sorted(os.listdir(p)):
                f = os.path.join(p, n)
                w(("[D] " + n + "/") if os.path.isdir(f)
                  else "[F] %s  %.1fKB" % (n, os.path.getsize(f) / 1024))
        elif c == "አንብብ" and r:
            w(open(self.p(r[0]), encoding="utf-8", errors="ignore").read()[:5000])
        elif c == "ቅዳ" and len(r) == 2:
            s, d = self.p(r[0]), self.p(r[1])
            shutil.copytree(s, d) if os.path.isdir(s) else shutil.copy2(s, d)
            w("OK")
        elif c == "አንቀሳቅስ" and len(r) == 2:
            shutil.move(self.p(r[0]), self.p(r[1]))
            w("OK")
        elif c == "ሰርዝ" and r:
            if r[-1] != "አዎ":
                return w("! ለማረጋገጥ መጨረሻ ላይ 'አዎ' ጨምር: ሰርዝ ፋይል አዎ")
            p = self.p(r[0])
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
            w("OK ተሰርዟል")
        elif c == "አቃፊ" and r:
            os.makedirs(self.p(r[0]), exist_ok=True)
            w("OK")
        elif c == "ጻፍ" and len(r) >= 2:
            open(self.p(r[0]), "w", encoding="utf-8").write(" ".join(r[1:]))
            w("OK ተጽፏል")
        elif c == "ፈልግ" and r:
            n = 0
            for d, _, fs in os.walk(self.cwd):
                for f in fs:
                    if r[0].lower() in f.lower():
                        w(os.path.join(d, f))
                        n += 1
                        if n >= 50:
                            return
            w("ተጠናቀቀ" if n else "ምንም አልተገኘም")
        else:
            w("ትዕዛዞች: cd ፋይሎች አንብብ ቅዳ አንቀሳቅስ ሰርዝ አቃፊ ጻፍ ፈልግ")

# ---------------- AI (Gemini ነጻ ቁልፍ) ----------------
class AI:
    def __init__(self):
        self.model = jload("ai.json", {}).get("model", "gemini-2.0-flash")
        self.key = jload("ai.json", {}).get("key", "")
        self.h = []
    def save(self):
        jsave("ai.json", {"key": self.key, "model": self.model})
    def __call__(self, line, w):
        if line.startswith("ቁልፍ "):
            self.key = line[5:].strip()
            self.save()
            return w("OK ቁልፍ ተቀምጧል")
        if line.startswith("ሞዴል "):
            self.model = line[5:].strip()
            self.save()
            return w("OK " + self.model)
        if line == "አዲስ":
            self.h = []
            return w("OK አዲስ ውይይት")
        if not self.key:
            return w("መጀመሪያ ነጻ ቁልፍ ከ aistudio.google.com አውጥተህ:\nቁልፍ <ቁልፍህ>")
        self.h.append({"role": "user", "parts": [{"text": line}]})
        body = json.dumps({
            "system_instruction": {"parts": [{"text":
                "Reply in the user's language. Be short and correct."}]},
            "contents": self.h[-12:]}).encode()
        url = ("https://generativelanguage.googleapis.com/v1beta/models/%s"
               ":generateContent?key=%s" % (self.model, self.key))
        req = urllib.request.Request(url, body,
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read().decode())
        t = d["candidates"][0]["content"]["parts"][0]["text"].strip()
        self.h.append({"role": "model", "parts": [{"text": t}]})
        w("AI: " + t)

# ---------------- ስራ / መሳሪያዎች ----------------
OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
       ast.Div: operator.truediv, ast.Pow: operator.pow, ast.USub: operator.neg,
       ast.Mod: operator.mod}

def calc(n):
    if isinstance(n, ast.Expression):
        return calc(n.body)
    if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
        return n.value
    if isinstance(n, ast.BinOp) and type(n.op) in OPS:
        return OPS[type(n.op)](calc(n.left), calc(n.right))
    if isinstance(n, ast.UnaryOp) and type(n.op) in OPS:
        return OPS[type(n.op)](calc(n.operand))
    raise ValueError("ያልተፈቀደ")

def Tools(line, w):
    a = line.split(None, 1)
    c, r = a[0], (a[1] if len(a) > 1 else "")
    if c == "ሒሳብ":
        w(calc(ast.parse(r, mode="eval")))
    elif c == "ሰዓት":
        w(time.strftime("%Y-%m-%d %H:%M:%S"))
    elif c == "ይለፍ":
        n = int(r) if r.isdigit() else 14
        s = string.ascii_letters + string.digits + "!@#$%"
        w("".join(random.SystemRandom().choice(s) for _ in range(n)))
    elif c == "ማስታወሻ":
        L = jload("notes.json", [])
        if r:
            L.append(r)
            jsave("notes.json", L)
            w("OK")
        else:
            w("\n".join("%d. %s" % (i + 1, x) for i, x in enumerate(L)) or "ባዶ")
    elif c == "ስራ":
        T = jload("todo.json", [])
        s = r.split(None, 1)
        if s and s[0] == "ጨምር" and len(s) > 1:
            T.append({"t": s[1], "d": False})
            jsave("todo.json", T)
            w("OK")
        elif s and s[0] == "ጨርስ" and len(s) > 1 and s[1].isdigit():
            T[int(s[1]) - 1]["d"] = True
            jsave("todo.json", T)
            w("OK")
        elif s and s[0] == "ሰርዝ" and len(s) > 1 and s[1].isdigit():
            T.pop(int(s[1]) - 1)
            jsave("todo.json", T)
            w("OK")
        else:
            w("\n".join("%d. [%s] %s" % (i + 1, "x" if x["d"] else " ", x["t"])
                        for i, x in enumerate(T)) or "ምንም ስራ የለም")
    else:
        w("ሒሳብ 2+3*4 · ሰዓት · ይለፍ 16 · ማስታወሻ ጽሑፍ · ስራ ጨምር/ጨርስ/ሰርዝ ቁጥር")

# ---------------- ኤዲተር ----------------
class Editor(BoxLayout):
    def __init__(self, **kw):
        super().__init__(orientation="vertical", spacing=dp(4), **kw)
        self.path = TextInput(multiline=False, size_hint_y=None, height=dp(44),
                              font_size=dp(15), background_color=PANEL,
                              foreground_color=(1, 1, 1, 1),
                              cursor_color=(1, 1, 1, 1),
                              text=os.path.join(START, "note.txt"))
        self.add_widget(self.path)
        bar = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
        for t, cb in (("Open", self.open), ("Save", self.save), ("New", self.new)):
            b = Button(text=t, background_normal="",
                       background_color=ACC if t == "Save" else KEYBG)
            b.bind(on_release=cb)
            bar.add_widget(b)
        self.add_widget(bar)
        self.msg = Label(text="", size_hint_y=None, height=dp(24),
                         color=(.6, 1, .6, 1), font_size=dp(13), markup=True,
                         halign="left")
        self.msg.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
        self.add_widget(self.msg)
        self.ed = TextInput(multiline=True, font_size=dp(14),
                            background_color=(.07, .09, .14, 1),
                            foreground_color=(.9, .95, 1, 1),
                            cursor_color=(1, 1, 1, 1), use_bubble=True,
                            use_handles=True)
        self.add_widget(self.ed)

    def say(self, t):
        self.msg.text = fx(t)

    def open(self, *_):
        p = os.path.expanduser(self.path.text.strip())
        try:
            self.ed.text = open(p, encoding="utf-8", errors="ignore").read()
            self.say("OK ተከፍቷል: " + p)
        except Exception as e:
            self.say("ERR " + str(e))

    def save(self, *_):
        p = os.path.expanduser(self.path.text.strip())
        try:
            open(p, "w", encoding="utf-8").write(self.ed.text)
            self.say("OK ተቀምጧል: " + p)
        except Exception as e:
            self.say("ERR " + str(e))

    def new(self, *_):
        self.ed.text = ""
        self.say("አዲስ ፋይል")

# ---------------- መተግበሪያ ----------------
class HabibShell(App):
    def build(self):
        self.title = "HABIB SHELL"
        root = BoxLayout(orientation="vertical", padding=dp(2), spacing=dp(2))
        self.sm = ScreenManager()
        self.tabs = {}
        defs = [("ተርሚናል", "term", Term(), "sh · py ኮድ · get url · edit ፋይል · help"),
                ("ፋይሎች", "files", Files(), "ፋይሎች አንብብ ቅዳ አንቀሳቅስ ሰርዝ ፈልግ"),
                ("AI", "ai", AI(), "ቁልፍ <ቁልፍ> ብለህ አስገባ · አዲስ · ሞዴል <ስም>"),
                ("ስራ", "tools", Tools, "ሒሳብ · ሰዓት · ይለፍ · ማስታወሻ · ስራ")]
        bar = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(3))
        for label, name, h, banner in defs:
            s = Screen(name=name)
            s.add_widget(Console(h, "HABIB SHELL — " + label + "\n" + banner,
                                 name=name))
            self.sm.add_widget(s)
            self.add_tab(bar, label, name)
        s = Screen(name="edit")
        self.editor = Editor()
        s.add_widget(self.editor)
        self.sm.add_widget(s)
        self.add_tab(bar, "ኤዲተር", "edit")
        root.add_widget(bar)
        root.add_widget(self.sm)
        self.select("term")
        return root

    def add_tab(self, bar, label, name):
        b = Button(text=fx(label), markup=True, background_normal="",
                   background_color=KEYBG)
        b.bind(on_release=lambda _b, n=name: self.select(n))
        bar.add_widget(b)
        self.tabs[name] = b

    def select(self, n):
        self.sm.current = n
        for k, b in self.tabs.items():
            b.background_color = ACC if k == n else KEYBG

    def open_editor(self, path):
        self.editor.path.text = path
        self.editor.open()
        self.select("edit")

HabibShell().run()
