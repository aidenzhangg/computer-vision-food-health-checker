# install libraries required for this detector (ultralytics, opencv-python, numpy, pandas, pywin32, customtkinter, pillow)
# Run it with the YOLO environment:  .\.venv-yolo\Scripts\python.exe foodhealthchecker.py
# The older Teachable Machine version is saved as foodhealthchecker_teachable.py

import os
import sys
import tempfile
import threading, queue
from datetime import datetime

import cv2
import numpy as np # for numerical operations
import pandas as pd # for data manipulation
import customtkinter as ctk # for the app window
from PIL import Image, ImageDraw, ImageFont, ImageGrab, ImageTk # for the logo, the fonts, snapshots and showing webcam frames in the window
from ultralytics import YOLO

# Get the directory where this Python file is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Use our own trained model (best.pt) if it's in the project folder,
# otherwise use the ready-made YOLO model, which already knows apples and pizza.
CUSTOM_MODEL_PATH = os.path.join(BASE_DIR, "best.pt")
PRETRAINED_MODEL = "yolo11n.pt"  # downloads automatically the first time; "n" = nano, the fastest
# Use the copy in the project folder if it's there, so it doesn't re-download when run from another folder
if os.path.exists(os.path.join(BASE_DIR, PRETRAINED_MODEL)):
    PRETRAINED_MODEL = os.path.join(BASE_DIR, PRETRAINED_MODEL)

LOGO_PATH = os.path.join(BASE_DIR, "logo.png")             # optional: put your own logo here to replace the built-in one
SCREENSHOT_DIR = os.path.join(BASE_DIR, "screenshots")     # where "Save snapshot" puts images
FONT_DIR = os.path.join(BASE_DIR, "fonts")                 # Barlow font files (free, OFL licence)

# Tuning
CONFIDENCE_THRESHOLD = 0.50  # YOLO detections below this are ignored
HOLD_FRAMES = 8              # keep showing the last food for a few frames if YOLO briefly loses it
FRAME_W, FRAME_H = 640, 480  # camera feed size
PANEL_W = 330                # width of the nutrition label next to the camera

# Colours
# The look is based on a printed Nutrition Facts label: black ink on white, on a pale sage background.
PAPER = "#DCE3D2"      # window background
LABEL = "#FFFFFF"      # nutrition label background
INK = "#000000"        # text and rules
INK_SOFT = "#4A4F45"   # secondary text
TRACK = "#E1E1DC"      # empty part of the confidence bar
BUTTON_HOVER = "#EEF2E8"

# Health colours, like printed ink rather than neon
HEALTH_HEX = {
    "Healthy": "#1E7B3C",     # leaf green
    "Neutral": "#E0A100",     # mustard
    "Unhealthy": "#C62F1D",   # tomato red
    "Unknown": "#6B6B6B",     # grey
}
# Text colour that is readable on top of each health colour
HEALTH_TEXT = {"Healthy": "#FFFFFF", "Neutral": "#000000", "Unhealthy": "#FFFFFF", "Unknown": "#FFFFFF"}


def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def hex_to_bgr(hex_color):
    # OpenCV colours are (blue, green, red)
    return hex_to_rgb(hex_color)[::-1]


# How each macro is written on the label, and its Daily Value (FDA, based on a 2,000 calorie diet)
MACRO_LABELS = {"Fat (g)": "Total fat", "Carbs (g)": "Total carbohydrate", "Protein (g)": "Protein"}
DAILY_VALUES = {"Fat (g)": 78, "Carbs (g)": 275, "Protein (g)": 50}

#Voice 
# Uses the Windows speech engine (SAPI) directly, so a sentence can be cut off part way through when the voice is muted.

_speech_q = queue.Queue()
_stop_speaking = threading.Event()  # set to cut off the sentence being spoken
muted = False  # changed by the Mute button

def _tts_worker():
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        voice = win32com.client.Dispatch("SAPI.SpVoice")
    except Exception as e:
        print("TTS error, voice is off:", e)
        return

    SPEAK_ASYNC = 1  # start speaking and return straight away
    PURGE = 2        # throw away whatever is being spoken

    while True:
        text = _speech_q.get()
        if text is None:  # shutdown signal
            break
        try:
            if muted:
                continue
            _stop_speaking.clear()
            voice.Speak(text, SPEAK_ASYNC)
            # Wait for the sentence to finish, checking every 50ms whether we've been told to stop
            while not voice.WaitUntilDone(50):
                if _stop_speaking.is_set():
                    voice.Speak("", SPEAK_ASYNC | PURGE)  # cut off the current sentence
                    break
        except Exception as e:
            print("TTS error:", e)
        finally:
            _speech_q.task_done()

    pythoncom.CoUninitialize()

_tts_thread = threading.Thread(target=_tts_worker, daemon=True)
_tts_thread.start()


# disabling scientific notation
np.set_printoptions(suppress=True)


# Developed a computer vision system that finds food held up to a webcam
# and shows (and reads out) its health status and nutrition per 100g.
# Uses a YOLO object detection model, which gives both the name of each food and a box around where it is.


# Load the YOLO model
if os.path.exists(CUSTOM_MODEL_PATH):
    model = YOLO(CUSTOM_MODEL_PATH)
    MODEL_LABEL = "Model: your trained best.pt"
    print("Using custom model:", CUSTOM_MODEL_PATH)
else:
    model = YOLO(PRETRAINED_MODEL)
    MODEL_LABEL = "Model: ready-made yolo11n.pt (apples and pizza only)"
    print("best.pt not found, using the ready-made model:", PRETRAINED_MODEL)
    print("It only knows apples and pizza from our food list. Train your own model for all 5 foods.")


# Nutrition table
food_categorization = pd.DataFrame(
    columns=['Health Status', 'Calories (100g)', 'Fat (g)', 'Carbs (g)', 'Protein (g)']
)
food_categorization.index.name = 'Classification'

# Assign realistic macros and health status per 100g of food
# Format: [Health Status, Calories, Fat, Carbs, Protein]
food_categorization.loc['Eggs'] = ['Healthy', 155, 11.0, 1.1, 13.0]
food_categorization.loc['Chocolate'] = ['Unhealthy', 598, 42.6, 46.4, 7.8]
food_categorization.loc['Bread'] = ['Neutral', 265, 3.2, 49.0, 9.0]
food_categorization.loc['Pizza'] = ['Unhealthy', 266, 10.0, 33.0, 11.0]
food_categorization.loc['Apples'] = ['Healthy', 61, 0.15, 14.8, 0.13]


# YOLO class names don't always match our table (the ready-made model says "apple", not "Apples"),
# so this maps lowercase YOLO names to our table names.
NAME_ALIASES = {
    "apple": "Apples",
    "apples": "Apples",
    "egg": "Eggs",
    "eggs": "Eggs",
    "pizza": "Pizza",
    "bread": "Bread",
    "chocolate": "Chocolate",
}


def to_food_name(yolo_name):
    # Turn a YOLO class name into the name used in our nutrition table (or None if it isn't one of our foods)
    key = yolo_name.strip().lower()
    if key in NAME_ALIASES:
        return NAME_ALIASES[key]
    for food in food_categorization.index:
        if food.lower() == key:
            return food
    return None


# Only ask YOLO for the classes that are foods in our table.
# The ready-made model knows 80 things (people, cups, phones...), and we don't want boxes around those.
FOOD_CLASS_IDS = [class_id for class_id, name in model.names.items() if to_food_name(name) is not None]
if not FOOD_CLASS_IDS:
    print("None of the model's classes match the nutrition table:", list(model.names.values()))
    sys.exit()
DETECTING = sorted({to_food_name(model.names[i]) for i in FOOD_CLASS_IDS})
print("Detecting:", DETECTING)


def detect_foods(frame):
    """
    Run YOLO on one frame.

    Returns a list of detections sorted from most to least confident.
    Each detection is a dict with 'name', 'confidence' and 'box' (x1, y1, x2, y2).
    """
    results = model(frame, conf=CONFIDENCE_THRESHOLD, classes=FOOD_CLASS_IDS, verbose=False)[0]

    detections = []
    for box in results.boxes:
        x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
        detections.append({
            "name": to_food_name(model.names[int(box.cls[0])]),
            "confidence": float(box.conf[0]),
            "box": (x1, y1, x2, y2),
        })

    detections.sort(key=lambda d: d["confidence"], reverse=True)
    return detections


_missing_labels = set()  # so the debug message only prints once per label

def get_nutrition_info(food_categorization, class_name):

    default_output = {
        "Health Status": "Unknown",
        "Calories (100g)": 0,
        "Protein (g)": 0.0,
        "Carbs (g)": 0.0,
        "Fat (g)": 0.0
    }
    try:
        info = food_categorization.loc[class_name]
        return {
            "Health Status": info['Health Status'],
            "Calories (100g)": info['Calories (100g)'],
            "Fat (g)": info['Fat (g)'],
            "Carbs (g)": info['Carbs (g)'],
            "Protein (g)": info['Protein (g)']
        }
    except KeyError:
        if class_name not in _missing_labels:
            print("DEBUG: label not found ->", repr(class_name))
            _missing_labels.add(class_name)
        return default_output


def _clear_speech_queue():
    # drop any messages that haven't been spoken yet
    while not _speech_q.empty():
        try:
            _speech_q.get_nowait()
            _speech_q.task_done()
        except queue.Empty:
            break


def stop_speech():
    # Stop talking right away: drop anything waiting and cut off the sentence being spoken
    _clear_speech_queue()
    _stop_speaking.set()


def speak_nutrition (class_name, info):
    if muted:
        return

    text = (
        f"{class_name}. "
        f"Health status: {info['Health Status']}. "
        f"Calories per 100 grams: {info['Calories (100g)']} kilocalories. "
        f"Fat: {info['Fat (g)']} grams. "
        f"Carbohydrates: {info['Carbs (g)']} grams. "
        f"Protein: {info['Protein (g)']} grams."
    )

    # keep only the latest message so we don't queue old ones
    _clear_speech_queue()
    _speech_q.put(text)


# Fonts

def load_app_fonts():
    # Make the Barlow fonts in the fonts folder usable by the window, without installing them on the computer.
    # Must run before the window is created.
    if sys.platform != "win32" or not os.path.isdir(FONT_DIR):
        return
    import ctypes
    FR_PRIVATE = 0x10  # only this program can see the fonts
    for name in os.listdir(FONT_DIR):
        if name.lower().endswith(".ttf"):
            ctypes.windll.gdi32.AddFontResourceExW(os.path.join(FONT_DIR, name), FR_PRIVATE, 0)


def load_tag_font(size=20):
    # Font for the name tags drawn on the camera image
    try:
        return ImageFont.truetype(os.path.join(FONT_DIR, "BarlowCondensed-Bold.ttf"), size)
    except OSError:
        return ImageFont.load_default(size)


TAG_FONT = load_tag_font()


# ---- Drawing on the camera image ----

def draw_detections(frame, detections):
    # Box around each food in its health colour, with a name tag on top.
    # The most confident food gets the thicker box. Less confident ones are drawn first so the main one ends up on top.
    tags = []
    for i, det in reversed(list(enumerate(detections))):
        status = get_nutrition_info(food_categorization, det["name"])['Health Status']
        color = HEALTH_HEX.get(status, HEALTH_HEX["Unknown"])
        x1, y1, x2, y2 = det["box"]
        cv2.rectangle(frame, (x1, y1), (x2, y2), hex_to_bgr(color), 4 if i == 0 else 2)
        tags.append((det, status, color))

    if not tags:
        return frame

    # OpenCV's built-in fonts look rough, so the tags are drawn with Pillow using Barlow
    image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(image)
    for det, status, color in tags:
        x1, y1 = det["box"][:2]
        text = f"{det['name']}  {det['confidence']:.0%}"
        left, top, right, bottom = draw.textbbox((0, 0), text, font=TAG_FONT)
        tag_w, tag_h = right - left + 16, bottom - top + 12
        tag_y = y1 - tag_h if y1 - tag_h >= 0 else y1  # put the tag inside the box if there's no room above
        draw.rectangle((x1, tag_y, x1 + tag_w, tag_y + tag_h), fill=hex_to_rgb(color))
        draw.text((x1 + 8 - left, tag_y + 6 - top), text, font=TAG_FONT, fill=hex_to_rgb(HEALTH_TEXT[status]))

    return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)


def process_frame(frame, state):
    """
    Detect foods in one webcam frame and draw boxes on it.
    'state' keeps values between frames: the last detections, how many frames we've missed, and the last spoken food.

    Returns (annotated frame, main detection or None, number of other foods on screen).
    """
    # Resize frame for display and mirror it so it moves like a mirror
    frame = cv2.resize(frame, (FRAME_W, FRAME_H), interpolation=cv2.INTER_AREA)
    frame = cv2.flip(frame, 1)

    detections = detect_foods(frame)

    # If YOLO loses the food for a frame or two, keep showing the last result so the screen doesn't flicker
    if detections:
        state["detections"] = detections
        state["missed"] = 0
    else:
        state["missed"] += 1
        if state["missed"] > HOLD_FRAMES:
            state["detections"] = []
    detections = state["detections"]

    main = detections[0] if detections else None

    # Only print and speak when the main food changes
    if main is not None and main["name"] != state["last_spoken"]:
        info = get_nutrition_info(food_categorization, main["name"])
        print(f"Detected: {main['name']} ({main['confidence']:.0%})")
        speak_nutrition(main["name"], info)
        state["last_spoken"] = main["name"]

    frame = draw_detections(frame, detections)
    return frame, main, (len(detections) - 1 if detections else 0)


class CameraWorker(threading.Thread):
    """
    Reads the webcam and runs YOLO in the background, so the window stays smooth
    even when detection is slow. The window picks up the newest result.
    """

    def __init__(self, camera):
        super().__init__(daemon=True)
        self.camera = camera
        self.running = True
        self.error = None
        self._lock = threading.Lock()
        self._latest = None   # (frame, main, other_count)
        self._frame_id = 0
        self._state = {
            "detections": [],     # last foods found
            "missed": 0,          # frames in a row with no food found
            "last_spoken": None,  # keep track of the last spoken food
        }

    def run(self):
        try:
            while self.running:
                ret, frame = self.camera.read()
                if not ret:
                    self.error = "Lost connection to the webcam"
                    break
                result = process_frame(frame, self._state)
                with self._lock:
                    self._latest = result
                    self._frame_id += 1
        finally:
            self.camera.release()

    def get_latest(self):
        with self._lock:
            return self._frame_id, self._latest


# logo

def make_logo(size=256):
    """
    -note to self can load logo.png from the project folder if there is one,
    draw a  logo: a white apple with a green check mark on a black square.
    """
    if os.path.exists(LOGO_PATH):
        return Image.open(LOGO_PATH).convert("RGBA").resize((size, size), Image.LANCZOS)

    s = 512  # draw big, then shrink, so the edges come out smooth
    green = hex_to_rgb(HEALTH_HEX["Healthy"]) + (255,)
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=56, fill=(0, 0, 0, 255))

    # apple: two overlapping ovals, a stem and a tilted leaf
    d.ellipse((118, 165, 302, 425), fill="white")
    d.ellipse((210, 165, 394, 425), fill="white")
    d.rounded_rectangle((244, 100, 268, 190), radius=12, fill="white")
    leaf = Image.new("RGBA", (120, 56), (0, 0, 0, 0))
    ImageDraw.Draw(leaf).ellipse((0, 0, 119, 55), fill="white")
    leaf = leaf.rotate(30, expand=True, resample=Image.BICUBIC)
    img.alpha_composite(leaf, (262, 52))

    # check mark on the apple (circles at the points give it rounded ends)
    points = [(190, 300), (238, 348), (322, 256)]
    d.line(points, fill=green, width=36, joint="curve")
    for x, y in points:
        d.ellipse((x - 18, y - 18, x + 18, y + 18), fill=green)

    return img.resize((size, size), Image.LANCZOS)


def set_app_id():
    # On Windows, this makes the taskbar show our icon instead of the Python icon
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("FoodHealthChecker")
    except Exception:
        pass  # not on Windows


def set_window_icon(window, logo):
    # Use the logo in the title bar and taskbar
    try:
        ico_path = os.path.join(tempfile.gettempdir(), "food_health_checker.ico")
        logo.save(ico_path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        window.iconbitmap(ico_path)
    except Exception:
        window._icon_photo = ImageTk.PhotoImage(logo.resize((64, 64)))
        window.iconphoto(True, window._icon_photo)


# window of app

class FoodHealthApp(ctk.CTk):
    def __init__(self, camera):
        super().__init__()
        self.title("Food Health Checker")
        self.configure(fg_color=PAPER)
        self.resizable(False, False)

        self.logo = make_logo()
        set_window_icon(self, self.logo)

        # Barlow Condensed for headings and numbers (like the type on a real nutrition label), Barlow for everything else
        self.fonts = {
            "app_title": ctk.CTkFont(family="Barlow Condensed ExtraBold", size=30),
            "label_title": ctk.CTkFont(family="Barlow Condensed ExtraBold", size=38),
            "food": ctk.CTkFont(family="Barlow Condensed", size=26, weight="bold"),
            "calories": ctk.CTkFont(family="Barlow Condensed ExtraBold", size=30),
            "calories_value": ctk.CTkFont(family="Barlow Condensed ExtraBold", size=40),
            "badge": ctk.CTkFont(family="Barlow Condensed", size=18, weight="bold"),
            "body": ctk.CTkFont(family="Barlow", size=14),
            "body_bold": ctk.CTkFont(family="Barlow", size=14, weight="bold"),
            "small": ctk.CTkFont(family="Barlow", size=12),
            "small_bold": ctk.CTkFont(family="Barlow SemiBold", size=12),
            "button": ctk.CTkFont(family="Barlow SemiBold", size=14),
        }

        self.grid_columnconfigure(0, weight=1)
        self._build_header()
        self._build_body()
        self._build_footer()

        self.bind("<Escape>", lambda event: self.close())
        self.protocol("WM_DELETE_WINDOW", self.close)

        self._shown_frame_id = -1
        self._live = False           # becomes True once the first camera frame is on screen
        self._panel_key = "unset"    # what the label is showing, so we only redraw it when it changes
        self._message_after = None
        self._loop_after = None

        self.worker = None
        if camera is not None and camera.isOpened():
            self.worker = CameraWorker(camera)
            self.worker.start()
            self.set_status("Starting camera", INK_SOFT)
        else:
            if camera is not None:
                camera.release()
            print("Could not open webcam. Please check camera connection or index")
            self.video_label.configure(text="The webcam didn't open.\nCheck it's plugged in and close any other app using it.",
                                       text_color="#FFFFFF")
            self.set_status("No camera", HEALTH_HEX["Unhealthy"])

        self.show_food(None, 0)
        self._loop_after = self.after(15, self.update_loop)

    # -- small building blocks for the nutrition label --

    def _rule(self, parent, thickness, pady=(0, 0)):
        # A black line across the label. Real labels use thin, medium and thick lines to group the information.
        ctk.CTkFrame(parent, height=thickness, fg_color=INK, corner_radius=0).pack(fill="x", pady=pady)

    def _text(self, parent, text, font, color=INK, **kwargs):
        return ctk.CTkLabel(parent, text=text, font=font, text_color=color, anchor="w", **kwargs)

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color=PAPER, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 0))
        header.grid_columnconfigure(1, weight=1)

        self.header_logo = ctk.CTkImage(self.logo, size=(46, 46))
        ctk.CTkLabel(header, image=self.header_logo, text="").grid(row=0, column=0, rowspan=2, padx=(0, 14))
        self._text(header, "Food Health Checker", self.fonts["app_title"], height=32).grid(row=0, column=1, sticky="sw")
        self._text(header, "Hold a food up to the camera to read its label", self.fonts["body"], INK_SOFT,
                   height=20).grid(row=1, column=1, sticky="nw")

        self.status_label = ctk.CTkLabel(header, text="", font=self.fonts["button"])
        self.status_label.grid(row=0, column=2, rowspan=2, sticky="e")

        ctk.CTkFrame(self, height=4, fg_color=INK, corner_radius=0).grid(row=1, column=0, sticky="ew", padx=24, pady=(14, 0))

    def _build_body(self):
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=2, column=0, padx=24, pady=20)

        # Camera feed in a black frame
        video_frame = ctk.CTkFrame(body, fg_color=INK, corner_radius=0)
        video_frame.grid(row=0, column=0, sticky="n")
        self.video_label = ctk.CTkLabel(video_frame, text="Starting camera...", width=FRAME_W, height=FRAME_H,
                                        font=self.fonts["body"], text_color="#FFFFFF")
        self.video_label.pack(padx=4, pady=4)

        # Nutrition label
        label = ctk.CTkFrame(body, width=PANEL_W, height=FRAME_H + 8, fg_color=LABEL,
                             border_color=INK, border_width=3, corner_radius=0)
        label.grid(row=0, column=1, sticky="n", padx=(20, 0))
        label.pack_propagate(False)
        inner = ctk.CTkFrame(label, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=16, pady=(8, 12))

        self._text(inner, "Nutrition Facts", self.fonts["label_title"], height=46).pack(fill="x")
        self._rule(inner, 1, pady=(0, 4))
        self.food_name = self._text(inner, "", self.fonts["food"], height=32)
        self.food_name.pack(fill="x")
        self.serving = self._text(inner, "", self.fonts["body"], height=20)
        self.serving.pack(fill="x")
        self._rule(inner, 10, pady=(6, 4))

        self._text(inner, "Amount per serving", self.fonts["small_bold"], height=16).pack(fill="x")
        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(fill="x")
        self._text(row, "Calories", self.fonts["calories"], height=44).pack(side="left")
        self.cal_value = self._text(row, "", self.fonts["calories_value"], height=44)
        self.cal_value.pack(side="right")
        self._rule(inner, 5, pady=(2, 2))

        ctk.CTkLabel(inner, text="% Daily Value*", font=self.fonts["small_bold"], text_color=INK,
                     height=18, anchor="e").pack(fill="x")

        # Fat, carbs and protein rows: name, grams, and % of the daily value
        self.macro_widgets = {}
        for key in ["Fat (g)", "Carbs (g)", "Protein (g)"]:
            self._rule(inner, 1)
            row = ctk.CTkFrame(inner, fg_color="transparent")
            row.pack(fill="x", pady=2)
            self._text(row, MACRO_LABELS[key], self.fonts["body_bold"], height=24).pack(side="left")
            grams = self._text(row, "", self.fonts["body"], height=24)
            grams.pack(side="left", padx=(6, 0))
            daily = self._text(row, "", self.fonts["body_bold"], height=24)
            daily.pack(side="right")
            self.macro_widgets[key] = (grams, daily)

        self._rule(inner, 10, pady=(2, 8))

        # Health rating and how sure the model is
        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(fill="x")
        self._text(row, "Health rating", self.fonts["body_bold"], height=28).pack(side="left")
        self.badge = ctk.CTkLabel(row, text="", font=self.fonts["badge"], corner_radius=0, width=110, height=28)
        self.badge.pack(side="right")

        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(fill="x", pady=(8, 0))
        self._text(row, "Confidence", self.fonts["body"], height=20).pack(side="left")
        self.conf_value = self._text(row, "", self.fonts["body_bold"], height=20)
        self.conf_value.pack(side="right")
        self.conf_bar = ctk.CTkProgressBar(inner, height=8, corner_radius=0, border_width=0,
                                           fg_color=TRACK, progress_color=INK)
        self.conf_bar.pack(fill="x", pady=(4, 0))

        self.more_label = self._text(inner, "", self.fonts["small"], INK_SOFT, height=18)
        self.more_label.pack(fill="x", pady=(6, 0))

        ctk.CTkLabel(inner, text="*Percent Daily Values are based on a 2,000 calorie diet.",
                     font=self.fonts["small"], text_color=INK_SOFT, anchor="w", justify="left",
                     wraplength=PANEL_W - 40).pack(side="bottom", fill="x")

    def _build_footer(self):
        footer = ctk.CTkFrame(self, fg_color=PAPER, corner_radius=0)
        footer.grid(row=3, column=0, sticky="ew", padx=24, pady=(0, 18))

        self.mute_button = ctk.CTkButton(footer, text="Mute voice", width=130, height=36, corner_radius=3,
                                         font=self.fonts["button"], fg_color=LABEL, hover_color=BUTTON_HOVER,
                                         text_color=INK, border_color=INK, border_width=2, command=self.toggle_mute)
        self.mute_button.pack(side="left", padx=(0, 10))
        ctk.CTkButton(footer, text="Save snapshot", width=140, height=36, corner_radius=3,
                      font=self.fonts["button"], fg_color=INK, hover_color="#2B2B2B", text_color="#FFFFFF",
                      command=self.save_snapshot).pack(side="left")

        self.message_label = self._text(footer, "", self.fonts["body"], INK_SOFT)
        self.message_label.pack(side="left", padx=14)

        self._text(footer, f"{MODEL_LABEL}. Press Esc to quit.", self.fonts["small"], INK_SOFT).pack(side="right")

    def set_status(self, text, color):
        self.status_label.configure(text=f"●  {text}", text_color=color)

    def show_food(self, main, other_count):
        # Update the nutrition label (only when something changed, to keep the window fast)
        key = None if main is None else (main["name"], round(main["confidence"], 2), other_count)
        if key == self._panel_key:
            return
        self._panel_key = key

        if main is None:
            self.food_name.configure(text="No food in view")
            self.serving.configure(text="Hold a food item in front of the camera")
            self.cal_value.configure(text="–")
            for grams, daily in self.macro_widgets.values():
                grams.configure(text="")
                daily.configure(text="–")
            self.badge.configure(text="Waiting", fg_color=TRACK, text_color=INK_SOFT)
            self.conf_value.configure(text="–")
            self.conf_bar.set(0)
            self.more_label.configure(text="")
            return

        info = get_nutrition_info(food_categorization, main["name"])
        status = info['Health Status']

        self.food_name.configure(text=main["name"])
        self.serving.configure(text="Serving size 100g")
        self.cal_value.configure(text=f"{info['Calories (100g)']}")
        for key, (grams, daily) in self.macro_widgets.items():
            grams.configure(text=f"{info[key]}g")
            daily.configure(text=f"{round(info[key] / DAILY_VALUES[key] * 100)}%")
        self.badge.configure(text=status, fg_color=HEALTH_HEX.get(status, HEALTH_HEX["Unknown"]),
                             text_color=HEALTH_TEXT.get(status, "#FFFFFF"))
        self.conf_value.configure(text=f"{main['confidence']:.0%}")
        self.conf_bar.set(main["confidence"])
        if other_count:
            self.more_label.configure(text=f"{other_count} more food{'s' if other_count > 1 else ''} in view")
        else:
            self.more_label.configure(text="")

    def update_loop(self):
        # Show the newest camera frame from the background worker
        if self.worker is not None:
            frame_id, latest = self.worker.get_latest()
            if latest is not None and frame_id != self._shown_frame_id:
                self._shown_frame_id = frame_id
                frame, main, other_count = latest

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                self.video_image = ctk.CTkImage(Image.fromarray(rgb), size=(FRAME_W, FRAME_H))
                self.video_label.configure(image=self.video_image, text="")
                self.show_food(main, other_count)

                if not self._live:  # first frame shown
                    self._live = True
                    self.set_status("Live", HEALTH_HEX["Healthy"])

            if self.worker.error:
                self.set_status("Camera lost", HEALTH_HEX["Unhealthy"])
                self.flash_message(self.worker.error)
                self.worker = None

        self._loop_after = self.after(15, self.update_loop)

    def toggle_mute(self):
        global muted
        muted = not muted
        if muted:
            stop_speech()
        self.mute_button.configure(text="Unmute voice" if muted else "Mute voice")
        self.flash_message("Voice muted" if muted else "Voice unmuted")

    def save_snapshot(self):
        # Clear any footer message first so it doesn't end up in the picture,
        # then wait a moment for the window to redraw before taking it
        if self._message_after is not None:
            self.after_cancel(self._message_after)
            self._message_after = None
        self.message_label.configure(text="")
        self.after(80, self._grab_window)

    def _grab_window(self):
        # Save a picture of the whole app window (camera, nutrition label and all) to the screenshots folder
        self.update_idletasks()
        x, y = self.winfo_rootx(), self.winfo_rooty()
        w, h = self.winfo_width(), self.winfo_height()
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)
        path = os.path.join(SCREENSHOT_DIR, datetime.now().strftime("food_%Y-%m-%d_%H-%M-%S.png"))
        try:
            ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).save(path)
        except Exception as e:
            print("Snapshot error:", e)
            self.flash_message("Couldn't save the snapshot")
            return
        print("Saved snapshot:", path)
        self.flash_message(f"Saved {os.path.basename(path)}")

    def flash_message(self, text, ms=2500):
        # Show a short message in the footer, then clear it
        self.message_label.configure(text=text)
        if self._message_after is not None:
            self.after_cancel(self._message_after)
        self._message_after = self.after(ms, lambda: self.message_label.configure(text=""))

    def close(self):
        if self._loop_after is not None:
            self.after_cancel(self._loop_after)
        if self._message_after is not None:
            self.after_cancel(self._message_after)
        if self.worker is not None:
            self.worker.running = False
            self.worker.join(timeout=2)

        # stop TTS worker thread cleanly
        stop_speech()
        _speech_q.put(None)
        _tts_thread.join(timeout=2)
        self.destroy()


def main():
    set_app_id()
    load_app_fonts()
    ctk.set_appearance_mode("light")
    camera = cv2.VideoCapture(0)
    app = FoodHealthApp(camera)
    app.mainloop()


if __name__ == "__main__":
    main()
