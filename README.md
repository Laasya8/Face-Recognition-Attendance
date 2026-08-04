# 👁️ AI Face Recognition Attendance System — Setup & Prerequisites

Welcome! This document outlines all the **prerequisites**, **environment configuration**, and **step-by-step setup** instructions required to install, verify, and run the AI Face Recognition Attendance System on your machine.

---

## 🛠️ 1. System & Hardware Prerequisites

Before installing the software, ensure your environment meets these hardware and system requirements:

1. **Python Environment**:
   - **Recommended Version**: `Python 3.10` or `Python 3.11`.
   - *Note*: Ensure `pip` is upgraded to the latest version.
2. **Camera / Web Biometrics**:
   - A working USB webcam or integrated laptop camera.
   - A modern web browser (e.g., Chrome, Edge, Firefox, Safari) with permissions granted to access the webcam.
3. **Storage & Internet Access**:
   - **Disk Space**: ~500 MB free space (required for the pre-compiled `InsightFace` models and dependencies).
   - **Internet Connection**: Required on the first run of the AI engine to download the **300 MB** face detection and alignment model (`buffalo_l`).

---

## ⚙️ 2. Step-by-Step Installation

Follow these steps to set up a clean, isolated local development environment.

### Step 1: Create a Virtual Environment
Isolate the project dependencies from your system's global Python environment:

**On Windows:**
```powershell
python -m venv .venv
```

**On macOS / Linux:**
```bash
python3 -m venv .venv
```

---

### Step 2: Activate the Virtual Environment
Activate your new virtual environment to configure your shell to use local packages:

**On Windows (PowerShell):**
```powershell
.venv\Scripts\activate
```

**On Windows (Command Prompt):**
```cmd
.venv\Scripts\activate.bat
```

**On macOS / Linux (Terminal):**
```bash
source .venv/bin/activate
```

*(Once activated, you will see `(.venv)` prepended to your command line prompt).*

---

### Step 3: Upgrade Pip
Ensure you have the latest packages builder installed:
```bash
python -m pip install --upgrade pip
```

---

### Step 4: Install Dependencies
This system separates standard dependencies from AI/vision models and testing environments:

1. **Core Web Application Stack** (Flask, SQLalchemy, Waitress):
   ```bash
   pip install -r requirements.txt
   ```

2. **AI Vision & Biometrics Layer** (InsightFace, ONNX Runtime, OpenCV):
   ```bash
   pip install -r requirements-ai.txt
   ```
   > [!NOTE]
   > Unlike legacy toolkits such as `dlib`, the AI vision layer runs on **ONNX Runtime** which is pre-compiled. You do not need to install complex C++ compilers, MSVC build tools, or CMake to compile libraries from source.

3. **Development & Testing Stack** (Optional — for running automated tests):
   ```bash
   pip install -r requirements-dev.txt
   ```

---

## 🔒 3. Configuration Setup (`.env`)

The application reads configuration parameters from environmental variables. 

1. Copy the provided sample environment configuration:
   ```bash
   copy .env.example .env
   ```
   *(Or on Linux/macOS: `cp .env.example .env`)*

2. Open the newly created `.env` file and generate a secure secret key for cryptographic sessions:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
   Copy the output token and set it as your `SECRET_KEY` in the `.env` file:
   ```env
   FLASK_CONFIG=development
   SECRET_KEY=<your_generated_secret_key_here>
   LOG_LEVEL=INFO
   ```

---

## 💾 4. Database Setup & Seeding

The application stores user credentials and biometric face vectors locally in a SQLite database (`instance/attendance.db` or `instance/dev.sqlite` depending on the environment).

1. **Initialize the Database**:
   Create the required tables and insert the default configuration settings:
   ```bash
   python -m flask init-db
   ```

2. **Create the Admin/Operator Account**:
   There is no self-registration page. You must bootstrap your first system operator account via the terminal:
   ```bash
   python -m flask create-admin
   ```
   Follow the prompts to enter:
   - **Username**
   - **Password** (minimum of 8 characters)
   - **Role** (choose `admin` or `operator`)

---

## 🧪 5. Verifying the Setup

Before booting the web server, run these checks to ensure the AI vision engine and database are integrated correctly.

### Check 1: AI Engine Sanity Check
Run the sanity script. This will download the ~300 MB model pack on the first run, load it, and run a fast face-analysis check:
```bash
python scripts/engine_check.py
```
*Expected Output:*
```
Loading FaceAnalysis (downloads model pack on first run)...
Engine ready in X.Xs
Blank frame: 0 face(s) in Xms
decode_image round-trip ok, shape=(480, 640, 3)

Engine check passed. Embedding dim per model spec: 512.
```

### Check 2: Smoke Checks
Verify that the endpoints and database connections respond properly:
```bash
python scripts/smoke_check.py <your_admin_username> <your_admin_password>
```
*Expected Output:*
```
[ok ] health endpoint returns 200
[ok ] health reports database ok
[ok ] anonymous / redirects to login
[ok ] login page renders with CSRF token
[ok ] wrong password rejected with 401
[ok ] login succeeds and dashboard renders
[ok ] dashboard shows stat cards
[ok ] API 404 returns JSON error envelope
[ok ] security headers set

All smoke checks passed.
```

### Check 3: Automated Test Suite
To run all automated unit and integration tests:
```bash
python -m pytest
```

---

## 🚀 6. Running the Application

To start the development web server:
```bash
python run.py
```

Open your browser and navigate to:
👉 **[http://127.0.0.1:5000](http://127.0.0.1:5000)**

Log in with your administrator credentials. Enjoy!

---

## 📖 Related Documentation

- Detailed Tech Stack & Directory Structure: [docs/README.md](file:///f:/data/Laasya/Antigravity-projects/face-detection/docs/README.md)
- Biometric Face Verification Mechanics: [docs/ai_pipeline_explained.md](file:///f:/data/Laasya/Antigravity-projects/face-detection/docs/ai_pipeline_explained.md)
- Database Models & Schema Specifications: [docs/database.md](file:///f:/data/Laasya/Antigravity-projects/face-detection/docs/database.md)
