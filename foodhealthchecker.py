# install libraries required for this classifier (opencv-contrib-python, numpy, tensorflow, h5py, pandas, pyttsx3)

import os

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
import sys
import threading, queue
from collections import deque

import cv2
import h5py # for reading HDF5 files
import numpy as np # for numerical operations
import pandas as pd # for data manipulation
import pyttsx3 # for tts
from keras.models import load_model  # tensorflow is required for Keras to work

# Get the directory where this Python file is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Paths to the model and labels
MODEL_PATH = os.path.join(
    BASE_DIR,
    "converted_keras_food",
    "keras_model.h5"
)

LABELS_PATH = os.path.join(
    BASE_DIR,
    "converted_keras_food",
    "labels.txt"
)

# ---- Tuning ----
CONFIDENCE_THRESHOLD = 0.70  # below this we show "Scanning..." instead of guessing
SMOOTHING_FRAMES = 5         # average predictions over the last few frames so the label doesn't flicker
SCAN_BOX_RATIO = 0.75        # size of the scan box as a fraction of the frame height
FRAME_W, FRAME_H = 640, 480  # camera feed size
PANEL_W = 280                # width of the info panel to the right of the camera feed

# ---- Colours (BGR) ----
WHITE = (245, 245, 245)
MUTED = (165, 165, 165)
DARK_TEXT = (25, 25, 25)
PANEL_BG = (34, 30, 27)
DIVIDER = (75, 70, 65)
BAR_BG = (62, 58, 55)
SCAN_COLOR = (210, 210, 210)

HEALTH_COLORS = {
    "Healthy": (100, 205, 90),     # green
    "Neutral": (40, 185, 250),     # amber
    "Unhealthy": (80, 80, 235),    # red
    "Unknown": (160, 160, 160),    # grey
}

MACRO_COLORS = {
    "Fat (g)": (60, 170, 255),
    "Carbs (g)": (230, 180, 70),
    "Protein (g)": (170, 120, 235),
}
MACRO_BAR_MAX = 50.0  # grams per 100g that fills a macro bar completely

FONT = cv2.FONT_HERSHEY_DUPLEX

# Initialize TTS engine once
tts_engine = pyttsx3.init()

_speech_q = queue.Queue()

def _tts_worker():
    while True:
        text = _speech_q.get()
        if text is None:  # shutdown signal
            break
        try:
            tts_engine.say(text)
            tts_engine.runAndWait()
        except Exception as e:
            print("TTS error:", e)
        finally:
            _speech_q.task_done()

_tts_thread = threading.Thread(target=_tts_worker, daemon=True)
_tts_thread.start()


# disabling scientific notation
np.set_printoptions(suppress=True)


# Developed a computer vision system that identifies food held up to a webcam
# and shows (and reads out) its health status and nutrition per 100g.
# The model was trained on [Teachable Machine](https://teachablemachine.withgoogle.com/train/image) using photos of different foods.

# Model Training

# Used Teachable Machine to train an image classification model on labeled food images.
# Collected varied images for each class.
# Trained with default settings.
# Tested accuracy using new images.


def patch_model_file(path):
    # Teachable Machine exports contain '"groups": 1,' which some Keras versions can't load.
    # Only rewrite the file when that text is actually there, so we don't modify it on every run.
    with h5py.File(path, mode="r") as f:
        model_config_string = f.attrs.get("model_config")

    if model_config_string is None:
        return
    if isinstance(model_config_string, bytes):  # some h5py versions return bytes
        model_config_string = model_config_string.decode("utf-8")
    if '"groups": 1,' not in model_config_string:
        return

    with h5py.File(path, mode="r+") as f:
        f.attrs.modify("model_config", model_config_string.replace('"groups": 1,', ''))


if not os.path.exists(MODEL_PATH):
    print("Model not found at", MODEL_PATH)
    print("Unzip converted_keras_food.zip into a folder called converted_keras_food next to this file.")
    sys.exit()

patch_model_file(MODEL_PATH)

# Load the trained keras model from the specified file path
# 'compile=False' is used here because we only need the model for inference (making predictions) not for further training. This speeds up loading and avoids loading optimizer state.
model = load_model(
    MODEL_PATH,
    compile=False
)

model.summary()  # Display a detailed summary of the model architecture including each layer's name, output shape, and number of parameters.


# Load the list of class labels from the specified text file.
# Each line in this file corresponds to a class index and its name (e.g., "0 Eggs").
with open(LABELS_PATH, "r") as labels_file:
    class_names = [line for line in labels_file.readlines() if line.strip()]

class_list = [] # Create an empty list to store cleaned class names
# Loop through each label in class_names
for x in class_names:
    # Split each entry on the first space to separate the index and the name
    # Take the second part [1], strip leading/trailing spaces
    clean_name = x.split(' ', 1)[1].strip()

    # Append the cleaned name to the new list
    class_list.append(clean_name)

food_categorization = pd.DataFrame(class_list, columns= ['Classification']) # Create a DataFrame from class_list with a single column named "Classification"
food_categorization = food_categorization.set_index('Classification') # Set "Classification" as the index for easier row access

food_categorization['Health Status'] = "Unknown"
food_categorization['Calories (100g)'] = 0
food_categorization['Fat (g)'] = 0.0
food_categorization['Carbs (g)'] = 0.0
food_categorization['Protein (g)'] = 0.0


# Assign realistic macros and health status per 100g of food
# Format: [Health Status, Calories, Fat, Carbs, Protein]
food_categorization.loc['Eggs'] = ['Healthy', 155, 11.0, 1.1, 13.0]
food_categorization.loc['Chocolate'] = ['Unhealthy', 598, 42.6, 46.4, 7.8]
food_categorization.loc['Bread'] = ['Neutral', 265, 3.2, 49.0, 9.0]
food_categorization.loc['Pizza'] = ['Unhealthy', 266, 10.0, 33.0, 11.0]
food_categorization.loc['Apples'] = ['Healthy', 61, 0.15, 14.8, 0.13]

# Set clean index
food_categorization.index = food_categorization.index.str.strip()


def get_center_square(frame):
    # Teachable Machine center-crops webcam images to a square, so we do the same
    # instead of stretching the whole 640x480 frame (which distorts the food's shape).
    h, w = frame.shape[:2]
    side = min(h, w)
    x1 = (w - side) // 2
    y1 = (h - side) // 2
    return frame[y1:y1 + side, x1:x1 + side]


def get_scan_box(frame):
    # The box on screen where the user should hold the food
    h, w = frame.shape[:2]
    side = int(min(h, w) * SCAN_BOX_RATIO)
    x1 = (w - side) // 2
    y1 = (h - side) // 2
    return x1, y1, x1 + side, y1 + side


# Predict using the trained model
def predict_probabilities(model, prediction_image):
    # OpenCV gives frames in BGR order, but the model was trained on RGB images
    image = cv2.cvtColor(prediction_image, cv2.COLOR_BGR2RGB)

    # Resize the image to match the model's expected input size (224x224 pixels)
    image = cv2.resize(image, (224, 224), interpolation=cv2.INTER_AREA)

    # Convert to numpy array, cast to float32, and reshape for the model
    image = np.asarray(image, dtype=np.float32).reshape(1, 224, 224, 3)

    # Normalize pixel values to the range [-1, 1]
    image = (image / 127.5) - 1.0

    # Calling the model directly is faster than model.predict() for a single frame
    # and doesn't print a progress bar every frame
    return model(image, training=False).numpy()[0]


def find_object_box(frame, scan_box):
    """
    Find where the object is inside the scan box using edge detection.
    The Teachable Machine model only says WHAT the food is, not WHERE it is,
    so this draws the box around the biggest group of edges in the scan area.

    Returns (x1, y1, x2, y2) in frame coordinates, or None if nothing was found.
    """
    x1, y1, x2, y2 = scan_box
    roi = frame[y1:y2, x1:x2]
    roi_area = roi.shape[0] * roi.shape[1]

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (7, 7), 0)          # blur to ignore small noise/texture
    edges = cv2.Canny(gray, 30, 90)                   # find outlines
    edges = cv2.dilate(edges, np.ones((5, 5), np.uint8), iterations=2)  # join nearby edges together

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Keep only shapes big enough to be part of the object, then box around all of them
    rects = [cv2.boundingRect(c) for c in contours if cv2.contourArea(c) > 0.01 * roi_area]
    if not rects:
        return None

    bx1 = min(r[0] for r in rects)
    by1 = min(r[1] for r in rects)
    bx2 = max(r[0] + r[2] for r in rects)
    by2 = max(r[1] + r[3] for r in rects)

    if (bx2 - bx1) * (by2 - by1) < 0.05 * roi_area:  # too small, probably noise
        return None

    return x1 + bx1, y1 + by1, x1 + bx2, y1 + by2


def smooth_box(previous, new, alpha=0.35):
    # Move the box part of the way towards the new position each frame so it glides instead of jittering
    if previous is None:
        return new
    return tuple(int(p + alpha * (n - p)) for p, n in zip(previous, new))


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

def speak_nutrition (class_name, info):
    text = (
        f"{class_name}. "
        f"Health status: {info['Health Status']}. "
        f"Calories per 100 grams: {info['Calories (100g)']} kilocalories. "
        f"Fat: {info['Fat (g)']} grams. "
        f"Carbohydrates: {info['Carbs (g)']} grams. "
        f"Protein: {info['Protein (g)']} grams."
    )

    # keep only the latest message so we don't queue old ones
    while not _speech_q.empty():
        try:
            _speech_q.get_nowait()
            _speech_q.task_done()
        except queue.Empty:
            break


    _speech_q.put(text)


# ---- Drawing helpers ----

def put_text(image, text, org, scale=0.6, color=WHITE, thickness=1):
    # LINE_AA gives smooth (anti-aliased) text instead of jagged pixels
    cv2.putText(image, text, org, FONT, scale, color, thickness, cv2.LINE_AA)


def text_width(text, scale=0.6, thickness=1):
    (w, _), _ = cv2.getTextSize(text, FONT, scale, thickness)
    return w


def draw_corner_box(image, box, color, thickness=3, corner_len=28):
    # Draws only the corners of a box, like a camera focus frame
    x1, y1, x2, y2 = box
    length = max(4, min(corner_len, (x2 - x1) // 3, (y2 - y1) // 3))
    for cx, cy, dx, dy in [(x1, y1, 1, 1), (x2, y1, -1, 1), (x1, y2, 1, -1), (x2, y2, -1, -1)]:
        cv2.line(image, (cx, cy), (cx + dx * length, cy), color, thickness, cv2.LINE_AA)
        cv2.line(image, (cx, cy), (cx, cy + dy * length), color, thickness, cv2.LINE_AA)


def draw_detection(image, box, label, color):
    # Thin outline + thick corners around the object, with a coloured name tag on top
    x1, y1, x2, y2 = box
    cv2.rectangle(image, (x1, y1), (x2, y2), color, 1, cv2.LINE_AA)
    draw_corner_box(image, box, color, thickness=4, corner_len=22)

    scale = 0.6
    (tw, th), _ = cv2.getTextSize(label, FONT, scale, 1)
    tag_h = th + 14
    tag_top = y1 - tag_h - 4 if y1 - tag_h - 4 >= 0 else y1 + 4  # put the tag inside the box if there's no room above
    cv2.rectangle(image, (x1, tag_top), (x1 + tw + 16, tag_top + tag_h), color, -1)
    put_text(image, label, (x1 + 8, tag_top + th + 7), scale, DARK_TEXT)


def draw_bar(image, x, y, width, height, fraction, color):
    fraction = float(np.clip(fraction, 0.0, 1.0))
    cv2.rectangle(image, (x, y), (x + width, y + height), BAR_BG, -1)
    if fraction > 0:
        cv2.rectangle(image, (x, y), (x + max(1, int(width * fraction)), y + height), color, -1)


def draw_info_panel(class_name, confidence, info, confident):
    """
    Build the side panel with the food name, health badge, confidence and nutrition.

    Parameters:
        class_name (str): Predicted food name.
        confidence (float): Model confidence between 0 and 1.
        info (dict): Must contain keys:
        'Health Status', 'Calories (100g)', 'Fat (g)', 'Carbs (g)', 'Protein (g)'
        confident (bool): Whether the confidence is above the threshold.

    Returns:
        ndarray: The panel image.
    """
    panel = np.full((FRAME_H, PANEL_W, 3), PANEL_BG, dtype=np.uint8)
    left, right = 20, PANEL_W - 20
    inner_w = right - left

    put_text(panel, "FOOD HEALTH CHECKER", (left, 38), 0.55, MUTED)
    cv2.line(panel, (left, 52), (right, 52), DIVIDER, 1, cv2.LINE_AA)

    if not confident:
        put_text(panel, "Scanning...", (left, 100), 0.9, WHITE)
        put_text(panel, "Hold a food item", (left, 135), 0.55, MUTED)
        put_text(panel, "inside the box", (left, 160), 0.55, MUTED)

        put_text(panel, f"Best guess: {class_name}", (left, 215), 0.5, MUTED)
        draw_bar(panel, left, 228, inner_w, 6, confidence, HEALTH_COLORS["Unknown"])
        put_text(panel, f"{confidence:.0%} (needs {CONFIDENCE_THRESHOLD:.0%})", (left, 255), 0.45, MUTED)

        put_text(panel, "ESC to quit", (left, FRAME_H - 18), 0.45, MUTED)
        return panel

    status = info['Health Status']
    status_color = HEALTH_COLORS.get(status, HEALTH_COLORS["Unknown"])

    # Food name
    put_text(panel, class_name, (left, 98), 1.0, WHITE)

    # Health badge
    badge_text = status.upper()
    badge_w = text_width(badge_text, 0.5) + 20
    cv2.rectangle(panel, (left, 114), (left + badge_w, 140), status_color, -1)
    put_text(panel, badge_text, (left + 10, 133), 0.5, DARK_TEXT)

    # Confidence
    put_text(panel, "Confidence", (left, 172), 0.45, MUTED)
    conf_text = f"{confidence:.0%}"
    put_text(panel, conf_text, (right - text_width(conf_text, 0.45), 172), 0.45, WHITE)
    draw_bar(panel, left, 180, inner_w, 6, confidence, status_color)

    cv2.line(panel, (left, 206), (right, 206), DIVIDER, 1, cv2.LINE_AA)

    # Calories
    put_text(panel, "CALORIES PER 100g", (left, 232), 0.45, MUTED)
    put_text(panel, f"{info['Calories (100g)']}", (left, 270), 1.1, WHITE)
    put_text(panel, "kcal", (left + text_width(f"{info['Calories (100g)']}", 1.1) + 8, 270), 0.55, MUTED)

    # Macros
    put_text(panel, "MACROS PER 100g", (left, 308), 0.45, MUTED)
    y = 336
    for key in ["Fat (g)", "Carbs (g)", "Protein (g)"]:
        name = key.split(" ")[0]
        value_text = f"{info[key]}g"
        put_text(panel, name, (left, y), 0.5, WHITE)
        put_text(panel, value_text, (right - text_width(value_text, 0.5), y), 0.5, WHITE)
        draw_bar(panel, left, y + 8, inner_w, 6, info[key] / MACRO_BAR_MAX, MACRO_COLORS[key])
        y += 40

    put_text(panel, "ESC to quit", (left, FRAME_H - 18), 0.45, MUTED)
    return panel


def process_frame(frame, state):
    """
    Classify one webcam frame and return the annotated image (camera feed + info panel).
    'state' keeps values between frames: recent predictions, the smoothed box, and the last spoken food.
    """
    # Resize frame for display and mirror it so it moves like a mirror
    frame = cv2.resize(frame, (FRAME_W, FRAME_H), interpolation=cv2.INTER_AREA)
    frame = cv2.flip(frame, 1)

    scan_box = get_scan_box(frame)

    # Find the object and classify BEFORE drawing anything, so our drawings don't confuse either step
    object_box = find_object_box(frame, scan_box)
    state["recent"].append(predict_probabilities(model, get_center_square(frame)))

    # Average the last few predictions to stop the label flickering between foods
    probabilities = np.mean(state["recent"], axis=0)
    index = int(np.argmax(probabilities))
    confidence = float(probabilities[index])
    class_name = class_list[index]
    confident = confidence >= CONFIDENCE_THRESHOLD
    info = get_nutrition_info(food_categorization, class_name)

    # Only print and speak when a new food is confidently detected
    if confident and class_name != state["last_spoken"]:
        print(f"Detected: {class_name} ({confidence:.0%})")
        speak_nutrition(class_name, info)
        state["last_spoken"] = class_name

    # Faint scan area guide
    draw_corner_box(frame, scan_box, SCAN_COLOR, thickness=2, corner_len=30)

    if confident:
        target = object_box if object_box is not None else scan_box
        state["box"] = smooth_box(state["box"], target)
        color = HEALTH_COLORS.get(info['Health Status'], HEALTH_COLORS["Unknown"])
        draw_detection(frame, state["box"], f"{class_name}  {confidence:.0%}", color)
    else:
        state["box"] = None
        hint = "Hold food inside the box"
        put_text(frame, hint, ((FRAME_W - text_width(hint, 0.6)) // 2, scan_box[3] + 28), 0.6, SCAN_COLOR)

    panel = draw_info_panel(class_name, confidence, info, confident)
    return np.hstack([frame, panel])


def main():
    camera = cv2.VideoCapture(0)
    if not camera.isOpened():
        print("Could not open webcam. Please check camera connection or index")
        sys.exit()

    window_name = "Food Nutrition Classification Tool"
    cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)

    state = {
        "recent": deque(maxlen=SMOOTHING_FRAMES),  # last few prediction results
        "box": None,                                # smoothed detection box
        "last_spoken": None,                        # keep track of the last spoken food
    }

    while True:
        # Capture frame from webcam
        ret, frame = camera.read()
        if not ret:
            break

        output = process_frame(frame, state)

        # Display annotated frame
        cv2.imshow(window_name, output)

        # Exit on ESC key, or when the window is closed
        if cv2.waitKey(1) == 27:
            break
        if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
            break

    camera.release()
    cv2.destroyAllWindows()

    # stop TTS worker thread cleanly
    _speech_q.put(None)
    _tts_thread.join(timeout=2)


if __name__ == "__main__":
    main()
