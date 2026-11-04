# Computer Vision Food Recognition and Nutritional Analysis System

## Why I built this

I'm interested in nutrition, but keeping track of food is another task to fit around school and everything else. Apps like MyFitnessPal came to mind when I thought about food logging: searching for an item, choosing the right entry, and entering a portion. I wanted to explore whether a camera could make the food lookup step easier.

What if I could just hold food up to a camera instead of typing its name? That question became the starting point for this project. My goal was to recognize a food and bring up its reference nutrition information straight away. I'm not trying to recreate all of MyFitnessPal; I wanted to build and understand this one part of the process.

I started with a simple image classifier, then moved to YOLO11 so I could draw boxes around foods and detect more than one item at once. This project is my first version of that idea: scan a supported food, see the result, and hear its nutrition read aloud.


## About

This is a Python desktop app built with a custom YOLO11 model, OpenCV, and CustomTkinter. I trained the detector on my own food photos. It currently recognizes **eggs, chocolate, bread, pizza, and apples**.

Each detection gets a bounding box and confidence score. The side panel shows nutrition per 100 g and a health rating from a lookup table. The app also includes spoken feedback, a live FPS counter, and a button to save the whole window as a screenshot. Detection runs locally on the computer.

## Screenshots

![Food Health Checker detecting an egg, with its bounding box, confidence score, live FPS, and nutrition panel](docs/images/food-health-checker.png)

*Detecting an egg and showing its nutrition beside the camera feed.*

![Food Health Checker detecting bread on a plate, with a neutral rating and nutrient bars](docs/images/bread-detection.png)

*Detecting bread on a plate. The FPS and confidence shown are from these frames; they are not an average speed or an overall accuracy score.*

## What it does

- Detects supported foods through a webcam and draws colour-coded boxes with names and confidence scores.
- Handles multiple detections; the most confident food is shown in the nutrition panel.
- Displays calories, fat, carbohydrates, protein, and calculated daily-value percentages per 100 g.
- Reads the detected food and its nutrition aloud through Windows text-to-speech.
- Provides mute/unmute controls and saves a picture of the whole app window.
- Displays current processing FPS and prints average throughput every 300 processed frames.

YOLO identifies the food and where it is in the frame. The app then looks up its nutrition and assigned health rating. It does not weigh the food or calculate its nutrition from the image.

## How to run

### Requirements

- **Python 3.11** and **Windows** for the supported speech setup.
- A webcam and a desktop session that can open a Tk window.
- Speakers or headphones for audio feedback.
- Internet access to install dependencies; the fallback model also downloads if needed.

### Windows PowerShell

Run each command on its own line:

```powershell
git clone https://github.com/aidenzhangg/computer-vision-food-health-checker.git
cd computer-vision-food-health-checker
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe foodhealthchecker.py
```

Keep `best.pt` and the `fonts` folder beside `foodhealthchecker.py`. The commands use the virtual environment directly, so activation is optional. Training images and notebooks are not needed to run the app.

If you already use the local `.venv-yolo` environment:

```powershell
.\.venv-yolo\Scripts\python.exe foodhealthchecker.py
```

In VS Code, choose **Python: Select Interpreter** from the command palette, select that environment's `python.exe`, then use **Run Python File in Terminal**.

### Controls

| Control | Action |
|---|---|
| Mute voice | Clears pending announcements and interrupts current speech. |
| Unmute voice | Enables speech and reads the current food if one is displayed. |
| Save snapshot | Saves the whole app window as `screenshots/food_YYYY-MM-DD_HH-MM-SS.png`. |
| Esc / close window | Stops the workers and closes the app. |

Hold one of the supported foods in view to try it. Saving a screenshot creates the `screenshots` folder automatically.

## How it works

![Diagram of the three threads in foodhealthchecker.py: the camera thread captures, preprocesses, detects, holds, draws and publishes each frame; the main Tk thread polls for the newest result, shows the frame and fills the nutrition label; the speech queue and worker read the result aloud](docs/images/how-it-works.svg)

The app runs on three threads. The camera thread does the heavy work, the main Tk thread only draws the window, and the speech thread talks. They pass data in two places: a locked "latest result" slot inside `CameraWorker`, and the `_speech_q` queue.

**Camera thread: `CameraWorker.run()`, steps 1 to 6**

1. **Capture.** `camera.read()` returns a BGR NumPy frame from `cv2.VideoCapture(0)`.
2. **Preprocess.** `process_frame()` resizes the frame to 640 × 480 and mirrors it with `cv2.flip(frame, 1)`. YOLO runs on this mirrored frame, so the boxes line up with what the window shows.
3. **Detect.** `detect_foods()` calls the model with `conf=CONFIDENCE_THRESHOLD` and `classes=FOOD_CLASS_IDS`, so only the five foods in the nutrition table come back, and only above 50% confidence. Each box becomes `{name, confidence, box}`. `to_food_name()` maps the model's label to the table's name, and the list is sorted from most to least confident.
4. **Hold.** If YOLO finds nothing, `state["missed"]` counts up and the previous detections stay on screen until it passes `HOLD_FRAMES` (8). The most confident detection becomes `main`. If `main` is a different food from `state["last_spoken"]`, step 11 runs.
5. **Draw.** `draw_detections()` draws each box in its food's health colour. The main food gets a thicker box, drawn last so it sits on top.
6. **Publish.** The FPS is stamped on the frame. Then `(frame, main, other_count)` is stored in `_latest` under `self._lock`, and `_frame_id` goes up by one.

**Main Tk thread: `update_loop()`, steps 7 to 10**

7. **Poll.** Every 15 ms, `get_latest()` reads `_frame_id` and `_latest` under the same lock. If the id hasn't changed, nothing is redrawn. The window only ever takes the newest result, so a slow frame never builds up a backlog.
8. **Show the frame.** The frame is converted from BGR to RGB and shown as a 640 × 480 `CTkImage`.
9. **Look up nutrition.** `show_food()` passes `main["name"]` to `get_nutrition_info()`, which reads that food's row from the `food_categorization` DataFrame.
10. **Fill the label.** Daily-value percentages are `round(grams / DAILY_VALUES[key] * 100)`. The badge takes its colour from `HEALTH_HEX`, and the confidence bar is set from `main["confidence"]`. The panel is only rebuilt when the food, its rounded confidence, or the number of other foods changes.

**Speech: `_speech_q` and `_tts_worker()`, steps 11 to 13**

11. **Queue.** On the camera thread, `speak_nutrition()` builds one sentence, empties anything still waiting with `_clear_speech_queue()`, and puts the new sentence on `_speech_q`. Only the newest food is ever waiting to be read.
12. **Speak.** `_tts_worker()` takes the sentence off the queue and passes it to Windows SAPI with `SPEAK_ASYNC`, checking every 50 ms whether it has been told to stop. It runs on its own thread, so speaking never pauses detection.
13. **Mute.** On the main thread, `toggle_mute()` calls `stop_speech()`, which empties the queue and sets `_stop_speaking`. The worker then calls `Speak("", SPEAK_ASYNC | PURGE)` to cut off the sentence in progress.

### Model and labels

The app loads `best.pt` from the script directory. If it is missing, it falls back to `yolo11n.pt`; among the five foods in this project, the fallback supports only apples and pizza.

`NAME_ALIASES` normalizes labels such as `apple` to `Apples`. `FOOD_CLASS_IDS` restricts inference to classes that match the nutrition table. `detect_foods()` returns each food's name, confidence, and `(x1, y1, x2, y2)` bounding box.

### Threads and frame retention

`CameraWorker` captures and processes frames in a background thread. It stores the latest result behind a lock, and the main Tk thread checks for updates every 15 ms. A separate speech worker consumes a queue so announcements do not block inference or window controls.

When no food is detected, previous detections remain visible for up to eight missed frames. This reduces brief disappearances, but does not track object IDs or smooth predictions that alternate between classes.

### FPS measurement

Timing uses `time.perf_counter()` before camera capture and after `process_frame()`. The displayed FPS includes capture, YOLO inference, nutrition lookup, and box drawing. Every 300 processed frames, the terminal prints:

```text
Average FPS over 300 processed frames: ...
```

Average FPS is `300 / total elapsed seconds`, including the FPS overlay and result publication. It measures camera-worker throughput, not GUI refresh rate or the duration of background speech playback. Performance varies with hardware, model, and scene; the first batch includes initial inference overhead.

## Configuration

Edit these constants in `foodhealthchecker.py`:

| Setting | Default | Purpose |
|---|---|---|
| `CONFIDENCE_THRESHOLD` | `0.50` | Minimum confidence for accepted detections. |
| `HOLD_FRAMES` | `8` | Number of missed frames that retain the previous detections. |
| `FRAME_W`, `FRAME_H` | `640`, `480` | Frame dimensions before inference and for display. |
| `DAILY_VALUES` | Fat: 78 g; carbs: 275 g; protein: 50 g | Reference amounts used for nutrient percentages and bars. |
| `CUSTOM_MODEL_PATH` | `best.pt` | Preferred model beside the script. |
| `SCREENSHOT_DIR` | `screenshots/` | Saved app-window images. |

The webcam is opened with `cv2.VideoCapture(0)` in `main()`. Try another index if the desired camera is not the default device.

## Nutrition data

Values are stored in the `food_categorization` Pandas DataFrame and expressed per 100 g:

| Food | Assigned rating | Calories (kcal) | Fat (g) | Carbohydrates (g) | Protein (g) |
|---|---|---:|---:|---:|---:|
| Eggs | Healthy | 155 | 11.0 | 1.1 | 13.0 |
| Chocolate | Unhealthy | 598 | 42.6 | 46.4 | 7.8 |
| Bread | Neutral | 265 | 3.2 | 49.0 | 9.0 |
| Pizza | Unhealthy | 266 | 10.0 | 33.0 | 11.0 |
| Apples | Healthy | 61 | 0.15 | 14.8 | 0.13 |

Daily-value percentages are calculated as `round(grams / reference_grams * 100)`. Nutrient bars use the same fraction, capped at a full bar. Small amounts can round to 0%.

These are approximate reference values, not measurements of the food in the image. Recipes, brands, and preparation methods vary. Health ratings are simplified categories in this prototype.

## What I learned

I started with Teachable Machine and TensorFlow, which gave me a label for the image. Switching to YOLO changed what I could build: I could draw a box around the food and detect more than one item at a time. I used Roboflow to label bounding boxes and Google Colab to train the model, then loaded the saved weights in the desktop app.

Getting a prediction was only part of the work. I had to match the model's class names to my nutrition table, decide which food to show when several were visible, and handle frames where nothing was detected. For example, the fallback model calls an apple `apple`, while my table uses `Apples`. Small differences like that need to be handled before the result can appear correctly in the app.

Testing with the webcam also showed me how unstable a prediction can be. I saw the label switch between apples and eggs even with fairly high confidence scores. Keeping the last detection for a few missed frames helps when a box briefly disappears, but it does not fix a wrong label. That made it clear why I need more varied training images and a separate test set before making claims about accuracy.

I also learned how much happens outside the model. The camera, detection, window, and speech all need to work together. I used a camera worker so inference would not hold up the window, and a separate speech queue so reading a result would not pause detection. Clearing old announcements matters too, because the food on screen can change before the voice finishes speaking.

To check speed, I added an FPS counter around capture and frame processing, including YOLO inference and drawing. I also calculate an average over 300 frames. This gives me a way to compare changes instead of judging performance only by how smooth the video looks.

The nutrition panel taught me to be clear about what the app actually knows. Recognizing bread does not tell me its weight, recipe, or exact ingredients. The values shown are references for 100 g, and the health ratings are categories I assigned in the code. A useful next step is to improve and evaluate the detector while keeping those limits clear in the interface.

## Technology and files

| Technology | Role |
|---|---|
| Python 3.11 | Application code |
| Ultralytics YOLO11 / PyTorch | Object detection |
| OpenCV | Webcam capture, preprocessing, and FPS overlay |
| CustomTkinter | Desktop window and controls |
| Pillow | Detection-label rendering, logos, and app-window snapshots |
| Pandas / NumPy | Reference data and image arrays |
| pywin32 / Windows SAPI | Spoken feedback and interruption |
| `threading` / `queue` | Camera and speech workers |

```text
computer-vision-food-health-checker/
|-- foodhealthchecker.py
|-- best.pt
|-- fonts/                 # Barlow fonts and OFL.txt
|-- docs/images/           # README screenshots
|-- requirements.txt
|-- README.md
`-- screenshots/           # Created at runtime
```

Detection runs locally in the Python desktop app.

## Troubleshooting

| Issue | Check |
|---|---|
| Missing Python module | Install `requirements.txt` with the same environment's Python used to run the script. |
| VS Code uses the wrong environment | Choose **Python: Select Interpreter** and select the project's environment. |
| Webcam does not open | Close other camera apps, check Windows camera access, and try another camera index. |
| Only apples and pizza are detected | Check that `best.pt` is beside the script and inspect the startup model message. |
| Speech is silent | Unmute voice, check the playback device, and look for `TTS error` in the terminal. |
| Food labels flicker | Improve lighting and the background, or increase the confidence threshold. |
| Video updates slowly | Check hardware load and the 300-frame FPS average. The GUI polling interval is not an inference speed guarantee. |

## Limitations and next steps

The model is limited to five food categories. It can get confused by unfamiliar appearances, partly hidden foods, and cluttered backgrounds. I have not included a measured test-set accuracy here. The app also does not estimate portions, save a history of detections, or track individual objects between frames.

Next, I want to add more varied food photos and evaluate precision and recall on images kept out of training. I also want to reduce label switching, add camera and confidence controls to the window, and test the setup on another computer.

## License

Copyright © 2026. All rights reserved.

This project is publicly available for portfolio and educational viewing purposes.

No permission is granted to copy, modify, distribute, or reuse the source code.

The Barlow fonts in the `fonts` folder are not covered by this notice. They are licensed under the SIL Open Font License; see `fonts/OFL.txt`. Third-party libraries retain their respective licenses.

## Sources

- Nutrition reference: [USDA FoodData Central](https://fdc.nal.usda.gov/).
- Object detection library: [Ultralytics documentation](https://docs.ultralytics.com/).
- Original classification workflow: [Google Teachable Machine](https://teachablemachine.withgoogle.com/train/image).
- Fonts: [Barlow](https://github.com/jpt/barlow) by Jeremy Tribby; see the bundled font license.
