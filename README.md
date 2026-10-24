# Computer Vision Food Health Checker

A Python desktop app that recognizes food through a webcam, draws detection boxes, and displays a health rating with reference nutrition information. A custom YOLO model identifies eggs, chocolate, bread, pizza, and apples. The app also reads nutrition information aloud and saves annotated camera snapshots.

Built with Ultralytics YOLO, OpenCV, CustomTkinter, and pyttsx3. Camera processing and speech run in background threads while the desktop window displays the latest detection result.

## Contents

- [Features](#features)
- [Installation](#installation)
- [Using the app](#using-the-app)
- [Detection pipeline](#detection-pipeline)
- [Threading and display updates](#threading-and-display-updates)
- [Configuration](#configuration)
- [Nutrition data](#nutrition-data)
- [Project structure](#project-structure)
- [Technology](#technology)
- [Troubleshooting](#troubleshooting)
- [Limitations](#limitations)
- [Project background](#project-background)
- [Future improvements](#future-improvements)
- [License](#license)
- [Sources](#sources)

## Features

- Webcam detection with food names, confidence scores, and bounding boxes.
- Multiple detections per frame; the most confident food supplies the side-panel information.
- Colour-coded detection boxes for the predefined Healthy, Neutral, and Unhealthy ratings.
- Energy and fat, carbohydrate, and protein values per 100 g.
- Separate progress bars for recognition confidence and nutrient amounts.
- Spoken nutrition information when the main detected food changes.
- Voice mute controls and timestamped PNG snapshots.
- Brief retention of previous detections when the model temporarily loses a food.

## Installation

### Requirements

- Python 3.11, a working webcam, and a desktop environment capable of opening a Tk window.
- Windows is the primary development environment. Audio requires an installed system speech engine and a working playback device.
- Internet access for dependency installation and for the first fallback-model download if `best.pt` is absent.

### Set up on Windows

Run these commands individually in PowerShell:

```powershell
git clone https://github.com/aidenzhangg/computer-vision-food-health-checker.git
cd computer-vision-food-health-checker
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install pyttsx3
.\.venv\Scripts\python.exe foodhealthchecker.py
```

The current script imports `pyttsx3`, which is not listed in `requirements.txt`; the additional install command above is required. Ultralytics supplies dependencies including PyTorch, OpenCV (`cv2`), and NumPy. Installation can take several minutes.

Keep `best.pt` beside `foodhealthchecker.py` to use the trained detector. No training notebooks or original training images are needed to run inference.

These commands call the environment's Python directly, so PowerShell environment activation is optional. For an existing local `.venv-yolo` environment, run:

```powershell
.\.venv-yolo\Scripts\python.exe foodhealthchecker.py
```

### VS Code Run button

Open **Python: Select Interpreter** from the command palette and select the Python executable inside your environment, such as `.venv\Scripts\python.exe` or `.venv-yolo\Scripts\python.exe`. Open `foodhealthchecker.py` and choose **Run Python File in Terminal**.

## Using the app

Hold a supported food in view of the webcam. The image is mirrored for display. Each detected food receives a box and confidence label; the side panel follows the detection with the highest confidence.

For example, an apple detected at 91% confidence displays `Apples`, a Healthy rating, 61 calories per 100 g, 0.15 g fat, 14.8 g carbohydrates, and 0.13 g protein. The confidence is illustrative, not a measured accuracy result.

| Control | Behaviour |
|---|---|
| Mute voice | Prevents new announcements and clears speech waiting in the queue. A sentence already playing may finish. |
| Unmute voice | Enables announcements for subsequent changes in the main detected food. |
| Save snapshot | Saves the latest annotated camera frame to `screenshots/food_YYYY-MM-DD_HH-MM-SS.png`. |
| Esc / close window | Stops the camera worker, signals the speech worker, and closes the app. |

Snapshots contain the camera image and detection overlays, not the surrounding app controls. The `screenshots` directory is created when the first image is saved.

## Detection pipeline

```text
Webcam (OpenCV)
    |
    v
Resize to 640 x 480 and mirror
    |
    v
YOLO inference: supported classes, confidence >= 0.50
    |
    v
Normalize food names and sort detections by confidence
    |
    +--> Retain previous detections during brief misses
    |
    +--> Nutrition lookup for the highest-confidence food
    |        |
    |        +--> Side panel
    |        +--> Speech queue when the main food changes
    |
    v
Draw boxes and labels --> Latest result --> CustomTkinter window
```

### Model selection and class filtering

The script resolves model paths relative to its own directory. If `best.pt` exists, it loads that file through `YOLO()`. Otherwise it uses `yolo11n.pt`, preferring a copy in the project directory and downloading the fallback if necessary.

`to_food_name()` normalizes model labels through `NAME_ALIASES`, such as `apple` to `Apples` and `egg` to `Eggs`. `FOOD_CLASS_IDS` limits inference to model classes that match the nutrition table. If no classes match, the script prints the model's class names and exits.

The fallback model recognizes apples and pizza from this project's supported list. It does not replace the custom model for eggs, bread, or chocolate.

### Detection results and persistence

`detect_foods()` returns dictionaries containing `name`, `confidence`, and `box`, where the box is `(x1, y1, x2, y2)` in frame coordinates. Results are sorted by descending confidence.

`process_frame()` retains the previous detection list during up to eight consecutive frames without a supported detection. After that, the panel returns to its waiting state. This is frame retention rather than object tracking: objects have no persistent IDs, and retained boxes are not updated during missed frames.

The model identifies the food class. The health rating and nutrition values come from a separate lookup table; they are not predicted from the image.

## Threading and display updates

| Component | Responsibility |
|---|---|
| Main Tk thread | Builds widgets, handles controls, and displays new results. |
| `CameraWorker` | Captures webcam frames and runs detection and annotation sequentially. |
| `_tts_worker` | Consumes queued announcements and calls the speech engine. |

The camera worker publishes a single latest result protected by `threading.Lock`, with a frame counter identifying updates. The GUI checks for new results using `after(15, ...)` and skips frames it has already displayed. It does not build a queue of every processed camera frame.

The side panel also caches a key containing the food name, rounded confidence, and other-food count to avoid unnecessary widget updates. Before a new speech message is queued, pending messages are cleared so older announcements do not accumulate. This does not interrupt speech already playing.

The 15 ms GUI polling interval is not an inference-time or FPS guarantee. Actual speed depends on the model, CPU/GPU, webcam, and other running applications. This repository does not currently report benchmark results or validation accuracy metrics.

## Configuration

Settings are constants in `foodhealthchecker.py`; there is no settings file or command-line configuration interface.

| Setting | Default | Effect |
|---|---|---|
| `CONFIDENCE_THRESHOLD` | `0.50` | Filters lower-confidence detections. Raising it can reduce weak guesses but may miss foods. |
| `HOLD_FRAMES` | `8` | Number of consecutive missed frames for which previous detections remain visible. |
| `FRAME_W`, `FRAME_H` | `640`, `480` | Frame dimensions used before inference and for display. These are not an explicit YOLO `imgsz` setting. |
| `MACRO_BAR_MAX` | `50.0` | Grams per 100 g that fill a nutrient bar completely. |
| `CUSTOM_MODEL_PATH` | `best.pt` beside the script | Preferred trained model. |
| `PRETRAINED_MODEL` | `yolo11n.pt` | Fallback model. |
| `LOGO_PATH` | `logo.png` beside the script | Optional custom logo; a built-in logo is drawn if absent. |
| `SCREENSHOT_DIR` | `screenshots` beside the script | Destination for saved frames. |

The camera index is set by `cv2.VideoCapture(0)` in `main()`. Change `0` to another index if the intended webcam is not the default device.

## Nutrition data

The following reference values are stored directly in the `food_categorization` Pandas DataFrame:

| Food | Assigned rating | Energy (kcal / 100 g) | Fat (g) | Carbohydrates (g) | Protein (g) |
|---|---|---:|---:|---:|---:|
| Eggs | Healthy | 155 | 11.0 | 1.1 | 13.0 |
| Chocolate | Unhealthy | 598 | 42.6 | 46.4 | 7.8 |
| Bread | Neutral | 265 | 3.2 | 49.0 | 9.0 |
| Pizza | Unhealthy | 266 | 10.0 | 33.0 | 11.0 |
| Apples | Healthy | 61 | 0.15 | 14.8 | 0.13 |

Nutrient bar fill is calculated as `min(grams / 50.0, 1.0)`. These bars are not percentages of daily intake. Confidence bar fill uses the model's detection confidence directly.

Values are approximate references for a fixed 100 g amount. The camera does not measure serving weight, ingredients, or preparation method. Ratings are manually assigned categories in this prototype, not individualized dietary assessments.

## Project structure

```text
computer-vision-food-health-checker/
|-- foodhealthchecker.py   # Detection, nutrition table, speech, and desktop UI
|-- best.pt                # Custom trained YOLO weights
|-- fonts/                 # Barlow fonts and OFL.txt
|-- requirements.txt       # Dependency list
|-- README.md
|-- logo.png               # Optional; user-supplied
`-- screenshots/           # Created at runtime when saving an image
```

The current window loads Barlow font files and uses Georgia for display headings. The older Teachable Machine implementation may be present in local development files, but it is not needed to run this app.

## Technology

| Technology | Role |
|---|---|
| Python 3.11 | Application code |
| Ultralytics YOLO / PyTorch | Model loading and object detection |
| OpenCV | Camera capture, resizing, mirroring, overlays, and PNG output |
| CustomTkinter | Desktop window and controls |
| Pillow | Logo drawing and conversion of camera images for Tk |
| NumPy | Image arrays and numerical operations |
| Pandas | Nutrition lookup table |
| pyttsx3 | Text-to-speech using an installed system speech engine |
| `threading` / `queue` | Background inference, synchronization, and speech messages |

The training workflow used food photos labelled with Roboflow and model training in Google Colab. The runtime loads the resulting weights; it does not retrain the model.

## Troubleshooting

| Symptom | What to check |
|---|---|
| `No module named customtkinter`, `cv2`, or `pyttsx3` | Install dependencies with the same environment's `python.exe` used to launch the app. Install `pyttsx3` separately as shown above. |
| VS Code Run fails while the terminal command works | Select the project environment through **Python: Select Interpreter**. |
| Webcam does not open | Close other camera apps, check Windows camera permissions, and try another `VideoCapture` index. |
| Only apples and pizza are supported | Check that `best.pt` is beside the script and read the model-selection message in the terminal. |
| No model classes match | Compare `model.names` with `NAME_ALIASES` and the nutrition table. |
| Labels alternate between foods | Try clearer lighting, a less cluttered background, or a higher confidence threshold. Frame retention does not smooth conflicting class predictions. |
| Voice is silent | Ensure voice is unmuted, verify the playback device and system speech engine, and check the terminal for `TTS error`. A food must change from the last announced class to trigger another announcement. |
| UI is responsive but video updates slowly | Inference runs separately from the GUI; inspect hardware load and model size. No fixed FPS is promised. |
| Snapshot says there is no camera image | Wait for the first processed frame before saving. |

## Limitations

Recognition is limited to supported classes in the loaded model. Confidence scores are model outputs, not a measured overall accuracy percentage. Similar appearances, occlusion, lighting, and backgrounds can cause misclassification, and the main panel may switch when detections trade confidence rankings.

All inference and nutrition lookup run locally. There is no web server, browser frontend, detection database, persistent tracking, or scan-history feature in the current app. Camera images are saved only when the snapshot control is used. The app requires a desktop session and has not been packaged as a standalone executable.

## Project background

I built this project to explore how computer vision can recognize everyday foods and make basic food information easier to access through a visual panel and spoken feedback.

The first version used Google Teachable Machine and TensorFlow for image classification. The current version uses YOLO object detection, allowing the app to locate foods and identify multiple items in one frame. Nutrition remains supporting information attached to each recognized class.

## Future improvements

- Expand the labelled dataset and supported food categories.
- Evaluate class-level precision, recall, and confusion on a held-out dataset.
- Stabilize changes in the main detected class across successive frames.
- Improve speech reliability and immediate interruption when muted.
- Move reference food data into a separate file with more specific source records.
- Add camera selection and configurable thresholds in the window.
- Package and test installation on a clean machine.

## License

Copyright ? 2026. All rights reserved.

This project is publicly available for portfolio and educational viewing purposes.

No permission is granted to copy, modify, distribute, or reuse the source code.

The Barlow fonts in the `fonts` folder are not covered by this notice. They are licensed under the SIL Open Font License; see `fonts/OFL.txt`. Third-party libraries retain their respective licenses.

## Sources

- Nutrition reference: [USDA FoodData Central](https://fdc.nal.usda.gov/).
- Object detection library: [Ultralytics documentation](https://docs.ultralytics.com/).
- Original classification workflow: [Google Teachable Machine](https://teachablemachine.withgoogle.com/train/image).
- Fonts: [Barlow](https://github.com/jpt/barlow) by Jeremy Tribby; see the bundled font license.
