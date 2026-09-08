# Enterprise Face Recognition Attendance System (FRAS)

An enterprise-grade, high-accuracy biometric attendance management system powered by **FastAPI**, **OpenCV Deep Neural Networks (YuNet + SFace)**, **SQLite (SQLAlchemy 2.0 ORM)**, and an elegant **Neomorphic (Soft UI)** interface.

---

## Key Features & Upgrades

- **Deep Metric Learning AI Pipeline**:
  - **YuNet Face Detector (`cv2.FaceDetectorYN`)**: Real-time deep face detector with 5 facial landmarks running at 100+ FPS.
  - **SFace Face Recognizer (`cv2.FaceRecognizerSF`)**: Extracts 128-dimensional normalized facial embeddings (SphereFace/ArcFace family).
  - **Cosine Similarity Matching**: Enforces strict confidence thresholds; rejects strangers as `"Unknown"`.
  - **Passive Anti-Spoofing & Liveness**: Laplacian variance texture analysis and chromatic distribution checks to prevent photo/screen replay attacks.
- **Client-Side Touchless Streaming (No `cv2.imshow()`)**:
  - Completely decouples the camera from the server.
  - Kiosk runs in any modern browser via `navigator.mediaDevices.getUserMedia()` with real-time HTML5 `<canvas>` bounding boxes.
  - Web Audio chime and Web Speech API voice synthesis (*"Attendance marked for [Name]"*).
- **Embedded Relational Database (Replaces Flat CSVs)**:
  - SQLite with Write-Ahead Logging (`WAL` mode) for high-performance concurrent transactions.
  - Full relational schema: `User`, `Department`, `FaceEmbedding`, `AttendanceLog`, and `AuditLog`.
- **Attendance Business Engine**:
  - **Debounce Cooldown (10 Minutes)**: Prevents duplicate punches when standing in front of the camera.
  - **Auto Dual Punch (IN / OUT)**: Automatically logs first punch as `IN`, subsequent punch as `OUT`.
  - **Shift & Late Arrival Tagging**: Compares timestamps against department shifts and grace periods (`ON_TIME` vs `LATE`).
- **Neomorphic (Soft UI) Interface**:
  - Beautiful tactile extruded/inset design system.
  - Kiosk Terminal (`/kiosk`), Admin Dashboard (`/admin`), User Directory (`/admin/users`), and Audit Reports (`/admin/reports`).
- **One-Click Reports**:
  - Instant Excel (`.xlsx`) generation with formatted headers and auto-fit columns.
  - Instant PDF audit report generation.
- **Zero Docker / Pure Native Python**:
  - Self-contained execution via standard Python 3.10+.
  - Automated one-click runners: `run.bat` (Windows) and `run.sh` (Linux/macOS).

---

## System Architecture

```
Client Browser (Edge / Chrome / Mobile / Tablet)
  │
  ├── Touchless Kiosk Mode (/kiosk) ──> getUserMedia() Webcam + Canvas Reticle
  └── Admin Management Portal (/admin) ──> Neomorphic Dashboard, Users, Reports
        │
        ▼ (Async Base64 Frame POST & REST APIs)
FastAPI Backend Server (Uvicorn)
  │
  ├── Auth Service (PBKDF2-HMAC-SHA256 & PyJWT)
  ├── AI Vision Engine (YuNet 5-Point Landmarks + SFace 128-d Embeddings)
  ├── Attendance Engine (10-Min Debounce, Shift Timing, IN/OUT Punching)
  ├── Export Service (OpenPyXL & ReportLab)
  │
  └── Persistent Storage (Embedded SQLite in WAL Mode)
        ├── data/attendance.db
        └── models/ (Auto-downloaded YuNet & SFace ONNX models)
```

---

## Quick Start Guide

### Prerequisites
- **Python 3.10 or higher** installed and added to your `PATH`.
- A webcam or USB camera.

### Method 1: One-Click Startup (Recommended)

#### On Windows:
Double-click `run.bat` or run:
```cmd
run.bat
```

#### On Linux / macOS:
```bash
chmod +x run.sh
./run.sh
```

### Method 2: Manual Python Startup
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start the server
python main.py
```

The application will be available at:
- **Attendance Kiosk Terminal**: [http://127.0.0.1:8000/kiosk](http://127.0.0.1:8000/kiosk)
- **Admin Management Portal**: [http://127.0.0.1:8000/admin](http://127.0.0.1:8000/admin)
- **Interactive Swagger API Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## Default Administrator Credentials

| Field | Value |
|---|---|
| **Username / Admin ID** | `admin` |
| **Password** | `admin123` |

---

## User Manual & Workflow

### 1. Enrolling a New User
1. Log in to the Admin Portal at `http://127.0.0.1:8000/login`.
2. Navigate to **Users** (`/admin/users`) and click **"Enroll New User"**.
3. Enter the student/employee details (Roll ID/Code, Full Name, Email, Department).
4. Look directly at the webcam preview in the modal and click **"Capture & Enroll"**.
5. The system will automatically capture 5 high-quality biometric frames, compute the 128-d normalized embedding vector, and save it to SQLite.

### 2. Marking Attendance (Touchless Kiosk)
1. Open `http://127.0.0.1:8000/kiosk` on any kiosk tablet or laptop at the entrance.
2. Click **Fullscreen** if desired.
3. As registered users approach the camera:
   - Green bounding box appears around the face with name and confidence percentage.
   - Attendance punch (`IN` or `OUT`) is logged with status (`ON TIME` or `LATE`).
   - System chimes and provides voice confirmation.
   - If the user stands in front of the camera, the 10-minute cooldown prevents duplicate punches.

### 3. Generating & Exporting Reports
1. In the Admin Portal, click **Reports** (`/admin/reports`).
2. Filter by date range, department, or student name.
3. Click **"Export Excel (.xlsx)"** or **"Export PDF Report"** for one-click downloads.

---

## Project Directory Structure

```
Face Recognition Based Attendance System/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app entry point & lifespan
│   ├── config.py                # Configuration constants, thresholds, paths
│   ├── database.py              # SQLite engine with WAL mode pragma listeners
│   ├── models.py                # SQLAlchemy models (User, Dept, FaceEmbedding, AttendanceLog)
│   ├── schemas.py               # Pydantic validation schemas
│   ├── auth.py                  # PBKDF2-HMAC password hashing & PyJWT authentication
│   ├── services/
│   │   ├── vision_engine.py     # YuNet FaceDetector + SFace FaceRecognizer + Liveness
│   │   ├── attendance_engine.py # Cooldown debounce, IN/OUT, shift & late marking
│   │   └── export_service.py    # Excel and PDF report generation
│   ├── routers/
│   │   ├── auth_router.py       # Login / Logout REST endpoints
│   │   ├── user_router.py       # User CRUD & multi-frame biometric enrollment
│   │   ├── attendance_router.py # Recognition endpoint, query logs, manual punch, exports
│   │   └── web_router.py        # Jinja2 views (/kiosk, /admin, /login, /users, /reports)
│   ├── static/
│   │   └── css/
│   │       └── neomorphism.css  # Neomorphic (Soft UI) design system
│   └── templates/
│       ├── base.html            # Neomorphic base layout & digital clock
│       ├── kiosk.html           # Fullscreen touchless camera terminal
│       ├── login.html           # Neomorphic login view
│       ├── admin_dashboard.html # Live metrics KPI dashboard
│       ├── admin_users.html     # User directory & webcam enrollment modal
│       └── admin_reports.html   # Attendance filtering & export controls
├── data/                        # SQLite database storage (WAL mode)
├── models/                      # Deep learning ONNX weights (auto-downloaded)
├── tests/
│   └── test_fras.py             # Automated unit tests
├── requirements.txt             # Python dependencies
├── run.bat                      # Windows batch runner
├── run.sh                       # Linux/macOS shell runner
└── README.md                    # Project documentation
```
