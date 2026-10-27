import os, ast, json, time, random, string, shutil, threading, subprocess, operator
import urllib.request
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

Window.clearcolor = (0.05, 0.05, 0.08, 1)
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
    def __init__(self, handler, banner, **kw):
        super().__init__(orientation="vertical", spacing=dp(4), **kw)
        self.handler, self.hist, self.i = handler, [], 0
        self.lines = [fx(banner)]
        self.out = Label(text="\n".join(self.lines), markup=True,
                         size_hint_y=None, halign="left",
                         valign="top", color=(.6, 1, .6, 1),
                         font_size=dp(14), **FK)
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
        row = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(4))
        self.inp = TextInput(multiline=False, font_size=dp(16),
                             background_color=(.12, .12, .16, 1),
                             foreground_color=((0, 0, 0, 0) if ETHI else (1, 1, 1, 1)),
                             cursor_color=(1, 1, 1, 1), **FK)
        self.inp.bind(on_text_validate=self.submit)
        self.inp.bind(text=lambda i, v: setattr(self.prev, "text", fx(v)))
        row.add_widget(self.inp)
        for t, d in (("Up", -1), ("Dn", 1)):
            b = Button(text=t, size_hint_x=None, width=dp(48))
            b.bind(on_release=lambda _b, d=d: self.recall(d))
            row.add_widget(b)
        self.add_widget(row)

    def write(self, t):
        def f(dt):
            self.lines = (self.lines + [fx(t)])[-300:]
            self.out.text = "\n".join(self.lines)
            self.sv.scroll_y = 0
        Clock.schedule_once(f)

    def recall(self, d):
        if self.hist:
            self.i = max(0, min(len(self.hist) - 1, self.i + d))
            self.inp.text = self.hist[self.i]

    def submit(self, *_):
        line = self.inp.text.strip()
        self.inp.text = ""
        Clock.schedule_once(lambda dt: setattr(self.inp, "focus", True), 0.1)
        if not line:
            return
        self.hist.append(line)
        self.i = len(self.hist)
        self.write("› " + line)
        if line in ("አጽዳ", "clear"):
            self.lines = []
            self.out.text = ""
            return
        def job():
            try:
                self.handler(line, self.write)
            except Exception as e:
                self.write("ERR " + str(e))
        threading.Thread(target=job, daemon=True).start()

# ---------------- ተርሚናል ----------------
class Term:
    def __init__(self):
        self.cwd = START
    def __call__(self, line, w):
        if line == "ወዴት":
            return w(self.cwd)
        if line.split()[0] == "cd":
            p = os.path.expanduser(line[2:].strip() or "~")
            p = os.path.abspath(os.path.join(self.cwd, p))
            if os.path.isdir(p):
                self.cwd = p
                return w(p)
            return w("ERR አቃፊ አልተገኘም")
        r = subprocess.run(line, shell=True, cwd=self.cwd, capture_output=True,
                           text=True, timeout=120)
        w((r.stdout + r.stderr).rstrip()[:6000] or "(ባዶ)")

# ---------------- ፋይሎች ----------------
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

# ---------------- መተግበሪያ ----------------
class HabibShell(App):
    def build(self):
        self.title = "HABIB SHELL"
        root = BoxLayout(orientation="vertical")
        sm = ScreenManager()
        tabs = [("ተርሚናል", "term", Term(), "ማንኛውም sh ትዕዛዝ ይሰራል (ls, cat, python...)"),
                ("ፋይሎች", "files", Files(), "ትዕዛዞች: ፋይሎች አንብብ ቅዳ አንቀሳቅስ ሰርዝ ፈልግ"),
                ("AI", "ai", AI(), "ቁልፍ <ቁልፍ> ብለህ አስገባ · አዲስ · ሞዴል <ስም>"),
                ("ስራ", "tools", Tools, "ሒሳብ · ሰዓት · ይለፍ · ማስታወሻ · ስራ")]
        bar = BoxLayout(size_hint_y=None, height=dp(46))
        for label, name, h, banner in tabs:
            s = Screen(name=name)
            s.add_widget(Console(h, "HABIB SHELL — " + label + "\n" + banner))
            sm.add_widget(s)
            b = Button(text=fx(label), markup=True)
            b.bind(on_release=lambda _b, n=name: setattr(sm, "current", n))
            bar.add_widget(b)
        root.add_widget(bar)
        root.add_widget(sm)
        return root

HabibShell().run()
