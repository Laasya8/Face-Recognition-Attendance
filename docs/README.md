# AI Face Recognition Attendance System

Welcome to the **AI Face Recognition Attendance System**! This is a modern, responsive, and secure enterprise-ready web application designed to automate student attendance marking using real-time biometric face verification.

---

## 🚀 1. Tech Stack Overview (And Why We Used It)

### 🐍 Backend: Python & Flask
* **Flask** is a lightweight, flexible web framework. Unlike heavy frameworks like Django, Flask is highly modular and gets out of the way, making it incredibly straightforward to integrate custom AI models, process base64 webcam frames, and serve web endpoints quickly.
* **SQLAlchemy & SQLite:** We use SQLite as the database engine with SQLAlchemy as our Object-Relational Mapper (ORM). SQLite is local, serverless, and stores everything in a single file (`instance/dev.sqlite`). It requires zero setup, making it perfect for desktop deployments, local kiosks, and development.

### 👁️ AI Vision Layer: InsightFace (RetinaFace + ArcFace)
This is the core biometric engine.
* **Why not `dlib` / `face_recognition`?**
  * *Legacy packages* like `face_recognition` rely on `dlib`, which requires compiling C++ code using CMake and MSVC. As you might have noticed in your terminal attempts, compiling `dlib` on Windows frequently fails unless you have massive Visual Studio C++ build tools installed.
  * **InsightFace** runs on **ONNX Runtime**, which is pre-compiled, highly optimized, and runs extremely fast on standard CPUs without needing complex compiler chains.
* **The AI Pipeline (End-to-End):**
  1. **Camera Input:** The user's browser captures frames via the webcam and POSTs them to the backend as a base64-encoded string.
  2. **Face Detection (RetinaFace):** Locates all faces in the image and outputs bounding box coordinates (`bbox`).
  3. **Face Alignment (Affine Transform):** Standardizes faces by rotating and scaling them (aligning eyes/nose/mouth) to a uniform `112x112` pixel grid. This ensures recognition works even if the person tilts their head.
  4. **Embedding Generation (ArcFace - `buffalo_l` model):** Passes the aligned face through a deep neural network to extract a **512-dimension floating-point vector** (the face's biometric signature). This vector is normalized.
  5. **Cosine Similarity Matching:** Compares the active vector against the cached database of enrolled student centroids using linear algebra matrix multiplication (`matrix @ query`). Because vectors are normalized, similarity is just a dot product—comfortable for matching thousands of students in milliseconds.
  6. **Identification & Marking:** If similarity matches are above the configured thresholds, attendance is logged.

### 🎨 Frontend: Bootstrap 5, Vanilla JS, & Chart.js
* **Bootstrap 5 (with customized CSS variables):** Allows us to build a gorgeous, premium responsive layout with unified dark/light themes, collapsible sidebar menus, and sleek card interfaces.
* **Vanilla JavaScript:** Drives client-side camera polling loops, raw image canvas drawing, and toast alerts.
* **Chart.js:** A simple and interactive library to render clean graphs (Line charts for daily trends and Donut charts for department counts) directly in your browser.

---

## 📁 2. Directory Structure

Here is how the project files are organized:

```
face-detection/
├── app/                        # Main Application Code
│   ├── blueprints/             # Modular Page Blueprints
│   │   ├── api/                # REST endpoints (/api/v1/recognize, etc.)
│   │   ├── auth/               # Login / Logout authentication controllers
│   │   └── dashboard/          # Dashboard panels, settings, and stats pages
│   ├── models/                 # SQLAlchemy Database Models (SQLite)
│   │   ├── person.py           # Student & Face centroids schema
│   │   ├── session.py          # Attendance sessions & record logs
│   │   └── user.py             # Operator / Administrator accounts
│   ├── services/               # Core business services
│   │   ├── face_engine.py      # InsightFace model wrapper
│   │   ├── enrollment.py       # Quality checks & template creation
│   │   └── matcher.py          # Fast cosine similarity matrix matcher
│   ├── static/                 # Static CSS, JS, and Images
│   │   ├── css/index.css       # Premium custom theme classes
│   │   └── js/                 # Client-side theme, webcam, and kiosk loops
│   └── templates/              # HTML templates rendered by Jinja2
├── docs/                       # Auxiliary documentation (e.g. database schemas)
├── instance/                   # Generated folder containing dev.sqlite
├── migrations/                 # Flask-Migrate database schema history
├── tests/                      # Automated unit/integration test suites
├── config.py                   # Global system config parameters
├── requirements.txt            # Python dependencies list
└── run.py                      # WSGI web entry point
```

---

## 🛠️ 3. Prerequisites

* **Python 3.10 or 3.11** (recommended).
* A modern web browser with camera permissions.

---

## ⚙️ 4. How to Run the Project (Step-by-Step)

### Step 1: Open Terminal & Activate the Virtual Environment
Open your terminal in the project directory, then activate the local virtual environment:
```powershell
.venv\Scripts\activate
```
*(You will see `(.venv)` appear at the start of your command prompt line).*

### Step 2: Initialize & Seed the Database
Create your local database tables and seed configurations:
```powershell
python -m flask init-db
```

### Step 3: Create your Operator/Admin Login Credentials
There is no self-registration page (by security design). Create your first user account via the CLI:
```powershell
python -m flask create-admin
```
Follow the prompts to enter your username, password (min 8 characters), and select a role (e.g., choose `operator` or `admin`).

### Step 4: Run the Development Server
Launch the local web server:
```powershell
python run.py
```
Open your browser and navigate to:
👉 **[http://127.0.0.1:5000](http://127.0.0.1:5000)**

Log in with the username and password you created in Step 3!

---

## 🧪 5. How to Run Tests
To run all 60 automated unit and integration tests:
```powershell
python -m pytest
```
