# Computer Vision Food Health/Nutritional Analysis System


## Table of Contents

- [Overview](#overview)
- [Demo / Example Output](#demo--example-output)
- [Features](#features)
- [How It Works](#how-it-works)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Nutrition Data](#nutrition-data)
- [Motivation & Background](#motivation--background)
- [Future Improvements](#future-improvements)
- [Installation](#installation)
- [License](#license)
- [Sources](#sources)


## Overview

This personal project is a computer vision-based food health checker that detects everyday food items (eggs, chocolate, bread, pizza and apples) through a webcam and evaluates whether they are healthy, neutral or unhealthy. It also displays key nutritional information per 100 grams, including calories, fat, carbohydrates and protein, laid out like a printed Nutrition Facts label.

The program uses a YOLO object detection model that I trained on my own food photos. Unlike a basic image classifier, which can only say what is in the picture, YOLO also finds where each food is. This lets the program draw a box around the food in the live camera feed and detect several foods at once.

This project also integrates text-to-speech (TTS) so that whenever a new food item is detected, the system reads its nutritional details aloud in real time. For example, the tool will announce: “Apples. Health status: Healthy. Calories per 100 grams: 61 kilocalories. Fat: 0.15 grams. Carbohydrates: 14.8 grams. Protein: 0.13 grams.” This lets users get instant audio feedback while keeping their focus on the food item or camera feed, which could potentially help visually impaired individuals.

This project demonstrates how AI can support health-conscious decision-making and raise awareness about everyday food choices.

> **Project history:** The first version of this project used an image classification model trained with [Google Teachable Machine](https://teachablemachine.withgoogle.com/train/image) and TensorFlow. The current version replaces it with a YOLO object detection model trained on the same photos, and adds a full app window.


## Demo / Example Output

When an apple is held up to the camera, a green box with the tag `Apples 91%` appears around it, and the nutrition label next to the camera feed shows:

```text
Nutrition Facts
Apples
Serving size 100g

Calories                     61
                  % Daily Value*
Total fat 0.15g               0%
Total carbohydrate 14.8g      5%
Protein 0.13g                 0%

Health rating            Healthy
Confidence                   91%
```


## Features

- Live food detection using the webcam and a YOLO object detection model

- Detects Eggs, Chocolate, Bread, Pizza and Apples (more can be added by retraining)

- Draws a box around each detected food, colour-coded by health rating, and can detect several foods at once

- Provides a simplified health rating of Healthy, Neutral or Unhealthy

- Displays a Nutrition Facts-style label with values per 100g:

      - Calories
      - Fat (g)
      - Carbohydrates (g)
      - Protein (g)
      - % Daily Value for fat, carbohydrates and protein (based on a 2,000 calorie diet)

- Shows a confidence score for each detection

- Reads the nutritional information aloud when a new food is detected

- **Mute voice** button, which stops speech immediately, even mid-sentence

- **Save snapshot** button, which saves a picture of the whole app window to a `screenshots` folder


## How It Works

### Model Loading
- The trained YOLO model (`best.pt`) is loaded with Ultralytics
- If `best.pt` is missing, the program falls back to the ready-made `yolo11n.pt` model, which only knows apples and pizza from the food list

### Nutrition Data
- Each food is mapped to a health rating and nutritional data through a Pandas DataFrame
- A lookup table includes:

      - Food Name
      - Health Status: Healthy, Neutral or Unhealthy
      - Calories per 100g
      - Fat (g) per 100g
      - Carbs (g) per 100g
      - Protein (g) per 100g

### Live Detection
- A background thread captures webcam frames and runs them through the YOLO model, so the window stays smooth while detection runs
- Detections below 50% confidence are ignored
- If the model briefly loses a food for a few frames, the last result stays on screen so the display doesn't flicker
- The most confident food is shown on the nutrition label, and each food gets a box on the camera feed

### Text-to-Speech
- When the main detected food changes, its nutrition is read aloud using the Windows speech engine
- Speech runs on its own thread so the camera feed keeps running while it talks


## Tech Stack

- Python 3.11: Main programming language

- Ultralytics YOLO11: Object detection model training and inference

- PyTorch: Deep learning framework used by YOLO

- Roboflow: Labelling the training photos with bounding boxes

- Google Colab: Training the model on a free cloud GPU

- OpenCV: Real-time webcam capture and image processing

- CustomTkinter: The app window

- Pillow: Drawing text on the camera feed, the logo and snapshots

- NumPy: Image and numerical processing

- Pandas: Food categorization and nutritional data management

- pywin32 (Windows SAPI): Offline text-to-speech that can be stopped mid-sentence

- Threading & Queue: Running detection and speech in the background so the window stays responsive

- Barlow and Barlow Condensed fonts: The typefaces used in the app


## Project Structure

```text
computer-vision-food-health-checker/
│
├── foodhealthchecker.py   # the program
├── best.pt                # trained YOLO model
├── fonts/                 # Barlow font files and their licence (OFL.txt)
├── requirements.txt
└── README.md
```


## Nutrition Data

The system maps each recognized food item to nutritional information per 100 grams. The current prototype includes the following foods:

| Food | Health Status | Calories (kcal) | Fat (g) | Carbohydrates (g) | Protein (g) |
|---|---|---:|---:|---:|---:|
| Eggs | Healthy | 155 | 11.0 | 1.1 | 13.0 |
| Chocolate | Unhealthy | 598 | 42.6 | 46.4 | 7.8 |
| Bread | Neutral | 265 | 3.2 | 49.0 | 9.0 |
| Pizza | Unhealthy | 266 | 10.0 | 33.0 | 11.0 |
| Apples | Healthy | 61 | 0.15 | 14.8 | 0.13 |

> **Note:** Nutritional values are approximate and are expressed per 100 grams. Values can vary depending on the specific product, recipe, or preparation method. % Daily Values use the FDA reference amounts of 78g fat, 275g carbohydrates and 50g protein.


## Motivation & Background

Obesity, poor diet, and diet-related diseases are growing public health challenges in Canada and the United States. According to Statistics Canada, in Canada, about 30% of adults are estimated to have obesity as of 2022, a rise over the past decades (9% in 1981 to 27.2% in 2018, and now 30%).

After the COVID-19 pandemic, obesity rates in Canada continued to accelerate: from 25% in 2009 to 30% in 2022, an increase of about 8 percentage points, with it gaining each year.

These trends highlight the urgent need for better public awareness about food quality, daily calorie intake, and nutrition. Many people consume foods without fully understanding their nutrient composition, making it harder to make healthier choices in everyday life.

This project aims to address part of that gap by providing a real-time food identifier + nutrition insight tool. By recognizing common food items (e.g. eggs, chocolate, bread, pizza, apples) and showing their calories and macronutrients per 100g, this system could be a starting point, with more foods and drinks being expanded into the data set. This system could also help users:
- Become more aware of what they are eating
- Quickly judge if the food is relatively healthy
- Use the data to guide better diet decisions

To sum it up, this project uses computer vision and machine learning for nutritional education, with the hope of contributing (small-scale) to better health awareness in our communities.


## Future Improvements

- Expand the model to recognize more food and drink categories
- Improve detection accuracy using a larger and more diverse dataset
- Store nutritional information in an external CSV or database
- Estimate serving sizes instead of displaying only per-100g values
- Keep a daily log of scanned foods and total calories
- Support macOS and Linux for text-to-speech
- Explore further accessibility improvements for visually impaired users


## Installation

### Requirements

- **Python 3.11**
- **Windows** (the text-to-speech and custom fonts use Windows features; on other systems the app runs without speech and in a default font)
- Webcam

### 1. Clone the Repository

```powershell
git clone https://github.com/aidenzhangg/computer-vision-food-health-checker.git
cd computer-vision-food-health-checker
```

### 2. Create a Virtual Environment

Create a Python 3.11 virtual environment:

```powershell
py -3.11 -m venv .venv
```

Activate the virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

When activated, the terminal should display:

```text
(.venv)
```

> **Note:** The virtual environment only needs to be created once. However, it must be activated again whenever a new terminal is opened.

### 3. Install Dependencies

Upgrade `pip`:

```powershell
python -m pip install --upgrade pip
```

Install all required dependencies:

```powershell
python -m pip install -r requirements.txt
```

This installs Ultralytics, which also installs PyTorch and OpenCV, so it can take a few minutes.

### 4. Run the Program

Make sure the virtual environment is activated:

```powershell
.\.venv\Scripts\Activate.ps1
```

Then run:

```powershell
python foodhealthchecker.py
```

The program will:

1. Load the trained YOLO model
2. Open the webcam in the app window
3. Detect food items and draw a box around each one
4. Display the health rating and nutritional information on the nutrition label
5. Read the nutritional information aloud using text-to-speech

### Controls

- **Mute voice / Unmute voice:** turns the speech off and on
- **Save snapshot:** saves a picture of the whole window to the `screenshots` folder
- **Esc** or closing the window: quits the program


## License

Copyright © 2026. All rights reserved.

This project is publicly available for portfolio and educational viewing purposes.

No permission is granted to copy, modify, distribute, or reuse the source code.

The Barlow fonts in the `fonts` folder are not covered by this notice. They are licensed under the SIL Open Font License; see `fonts/OFL.txt`.


## Sources

Research for Motivation & Background: [Statistics Canada](https://www150.statcan.gc.ca/n1/pub/82-003-x/2025002/article/00002-eng.htm)

Calories & Macros for each Food: [USDA FoodData Central](https://fdc.nal.usda.gov/)

Object detection: [Ultralytics YOLO](https://docs.ultralytics.com)

Fonts: [Barlow](https://github.com/jpt/barlow) by Jeremy Tribby, SIL Open Font License
