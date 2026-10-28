# Enterprise Face Recognition Attendance System (FRAS)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com)
[![OpenCV](https://img.shields.io/badge/OpenCV-YuNet%20%7C%20SFace-5C3EE8.svg?logo=opencv)](https://opencv.org)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg?logo=docker)](https://www.docker.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A high-accuracy, real-time biometric attendance and workforce payroll system powered by **FastAPI**, **OpenCV Deep Learning (YuNet + SFace)**, and **SQLAlchemy**. Built for academic institutions and enterprises requiring touchless check-ins, anti-spoofing liveness verification, automated shift rules, and compensation tracking.

---

## 🌟 Key Features

- **Touchless Live Scanning Kiosk**: Fullscreen biometric check-in with precision reticle HUD, scanning laser animation, and synthetic voice feedback (`Web Speech API`).
- **Deep Metric Face Verification**:
  - **YuNet ONNX**: High-speed face detection and 5-point facial landmark alignment.
  - **SFace ONNX**: 128-dimensional L2-normalized deep feature vectors matched via Cosine Similarity.
- **Passive Anti-Spoofing / Liveness Filter**: High-frequency texture analysis (Laplacian variance) and chromatic saturation checks to block screen replays and paper printouts.
- **Debounce Cooldown Engine**: Prevents double-punching (configurable debounce window, default: 10 minutes) with persistent database fallback.
- **In-Memory Biometric Cache**: High-performance RAM cache for 128-d face embeddings, eliminating repetitive database queries on 450ms kiosk frame polls.
- **Custom & Manual Punch IN & OUT**: Admin console allows manually logging custom check-ins, check-outs, or complete shifts with custom past/present timestamps, punctuality status (`ON_TIME`, `LATE`, `HALF_DAY`, `EXCUSED`), and audit notes.
- **Employee-Specific Manual Grace Time**: Flexible punctuality configuration allows setting custom grace periods (in minutes) per employee, cleanly overriding department defaults.
- **Shift & Punctuality Engine**: Department-specific shift schedules, automatic grace period comparison, and `ON_TIME` vs `LATE` categorization.
- **Workforce Payroll & Overtime Engine**: Dynamic tracking of daily hours, overtime hours (1.5x wage rate), late arrival deduction penalties, and downloadable CSV payroll export.
- **Comprehensive Reporting**: Formatted **Excel (.xlsx)** workbooks with styling and landscape **PDF audit reports** generated via ReportLab.
- **Security & RBAC**: PBKDF2-HMAC-SHA256 password hashing (100,000 rounds), PyJWT authentication with secure HTTP-only cookies, and role separation (`SUPER_ADMIN`, `ADMIN`, `HR_MANAGER`, `USER`).

---

## 🏗️ Architecture & Project File Structure

### System Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Client Presentation Layer                       │
│  • Modern Browser Webcam (MediaDevices API / 450ms Canvas polling)     │
│  • Web Speech Synthesis (TTS voice prompt) & Web Audio chime           │
│  • Frosted Glassmorphism Theme (Backdrop-filter blur, Specular border) │
│  • Operator Launchpad & On-Screen Hotkey Reference Guide (<kbd>?</kbd>)│
└───────────────────────────────────▲────────────────────────────────────┘
                                    │ HTTP / JSON / Base64 frames
┌───────────────────────────────────▼────────────────────────────────────┐
│                    FastAPI Enterprise Backend Layer                    │
│  • Routers: auth, attendance, users, leaves, shifts, holidays, web     │
│  • Security: PBKDF2-HMAC-SHA256 (100k rounds), PyJWT HTTP-only cookie │
│  • In-Memory Biometric RAM Cache: Instant 128-d cosine comparisons     │
│  • Transaction Safety: Automatic rollbacks, idempotent error recovery  │
└───────────────────────────┬───────────────────────┬────────────────────┘
                            │                       │
             ┌──────────────▼───┐       ┌───────────▼──────────────────┐
             │ AI Vision Engine │       │       Database Layer         │
             │ • YuNet ONNX     │       │ • SQLAlchemy 2.0 ORM         │
             │ • SFace ONNX     │       │ • SQLite (Safe DELETE mode)  │
             │ • Texture Liveness       │   or PostgreSQL / MySQL      │
             │ • Cosine Matcher │       │ • Automatic PRAGMA migration │
             └──────────────────┘       └──────────────────────────────┘
```

### 📁 Clean Project Directory Structure

```text
Face Recognition Based Attendance System/
├── app/                                 # Main Backend & Frontend Application Package
│   ├── __init__.py                      # Package indicator
│   ├── auth.py                          # PBKDF2-HMAC-SHA256 & JWT Cookie Authentication
│   ├── config.py                        # Centralized Settings & Environment Paths
│   ├── database.py                      # SQLAlchemy Engine, SessionLocal, PRAGMA journal_mode=DELETE
│   ├── main.py                          # FastAPI Lifespan, CORS, Static Files, Auto-Migrations
│   ├── models.py                        # Relational Database Schema (SQLAlchemy ORM)
│   ├── schemas.py                       # Request/Response Validation Models (Pydantic v2)
│   ├── routers/                         # API and Web Route Controllers
│   │   ├── attendance_router.py         # Biometric punch, manual punch, reports, payroll
│   │   ├── auth_router.py               # Login, logout, password change endpoints
│   │   ├── holiday_router.py            # Organization & statutory holiday calendar APIs
│   │   ├── leave_router.py              # Leave quotas, time-off requests, and approvals
│   │   ├── regularization_router.py     # Attendance dispute & missed-punch correction APIs
│   │   ├── shift_router.py              # Multi-shift rostering and staff assignment APIs
│   │   ├── user_router.py               # Biometric enrollment, employee profile management
│   │   └── web_router.py                # Jinja2 template views for Kiosk, Admin, & Portal
│   ├── services/                        # Business Logic & Computational Engines
│   │   ├── attendance_engine.py         # Cooldown debounce, shift punctuality, punch logging
│   │   ├── export_service.py            # Formatted Excel (.xlsx) & PDF report generation
│   │   ├── holiday_service.py           # Holiday schedules & calendar business logic
│   │   ├── leave_service.py             # Balance initialization, quota deductions, date checks
│   │   ├── payroll_service.py           # Work hours, overtime (1.5x), penalties, payroll CSV
│   │   ├── regularization_service.py    # Dispute workflows and log updates
│   │   ├── shift_service.py             # Punctuality evaluation, grace times, night shift rules
│   │   ├── vision_engine.py             # Singleton wrapper for YuNet, SFace & in-memory cache
│   │   └── vision/                      # Multi-stage Deep Learning Vision Pipeline
│   │       ├── base.py                  # Abstract interfaces (Detector, Embedder, Liveness)
│   │       ├── detectors.py             # YuNet ONNX & Haar Cascade fallback
│   │       ├── embedders.py             # SFace ONNX 128-d deep embedding model
│   │       ├── liveness.py              # Passive texture (Laplacian) & color anti-spoofing
│   │       └── pipeline.py              # Pluggable multi-stage vision orchestrator
│   ├── static/                          # Static Frontend Assets
│   │   └── css/
│   │       └── neomorphism.css          # Frosted Glassmorphism Dark UI Design System
│   └── templates/                       # Jinja2 Server-Rendered Frosted Glass Views
│       ├── base.html                    # Base layout, navbar, live clock, operator guide modal
│       ├── kiosk.html                   # High-speed biometric check-in kiosk with HUD & TTS
│       ├── login.html                   # Frosted glass sign-in card with role-based routing
│       ├── admin_dashboard.html         # Admin HUD, 4-card Launchpad, live metrics, audit trail
│       ├── admin_users.html             # Employee roster, multi-frame webcam enrollment, filters
│       ├── admin_reports.html           # Attendance ledger, date presets, Excel/PDF export
│       ├── admin_payroll.html           # Workforce wage calculations, overtime hours, CSV export
│       ├── admin_leaves.html            # Leave approvals, quota adjustments, regularization reviews
│       ├── admin_shifts.html            # Shift rostering, night-shift logic, employee assignments
│       ├── admin_holidays.html          # Corporate holiday calendar & statutory schedule
│       └── portal_dashboard.html        # Employee self-service portal (leaves, logs, pay estimate)
├── data/                                # Database & Persistence Storage
│   └── attendance.db                    # SQLite primary database (or configured PostgreSQL)
├── models/                              # Pre-trained Deep Learning Neural Weights (ONNX)
│   ├── face_detection_yunet_2023mar.onnx
│   └── face_recognition_sface_2021dec.onnx
├── tests/                               # Automated Test Suites
│   ├── test_audit_fixes.py              # Fast unit test suite (shift parsing, debounce, fallback)
│   ├── test_fras.py                     # Integration test suite for core attendance workflow
│   ├── test_phase1_features.py          # Tests for leaves, shifts, holidays, regularization
│   └── test_vision_pipeline.py          # Tests for multi-stage vision components
├── Caddyfile                            # Automatic HTTPS reverse proxy config for webcam SSL
├── Dockerfile                           # Containerized production build
├── docker-compose.yml                   # Docker Compose orchestrator
├── main.py                              # Server bootstrap runner (`python main.py`)
├── manage_admin.py                      # Standalone CLI admin credential manager
├── requirements.txt                     # Pinned project dependencies
├── run.bat                              # 1-Click Windows execution script
└── run.sh                               # 1-Click Linux / macOS execution script
```

---

## 🚀 Quick Start (Local Setup)

### 1. Prerequisites
- Python 3.10, 3.11, or 3.12
- Git
- Web camera connected to client machine

### 2. Clone and Setup Environment

```bash
# Clone the repository
git clone <repo-url>
cd "Face Recognition Based Attendance System"

# Create and activate virtual environment
python3 -m venv venv
# On Linux/macOS:
source venv/bin/activate
# On Windows (Command Prompt):
venv\Scripts\activate.bat
# On Windows (PowerShell):
venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Copy the example environment template:
```bash
cp .env.example .env
```
Open `.env` and verify your settings (a secure random `JWT_SECRET_KEY` is recommended).

### 4. Run the Application

```bash
# Via Python
python main.py

# Or via Uvicorn directly
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

- **Kiosk Mode (Live Scan)**: [http://127.0.0.1:8000/kiosk](http://127.0.0.1:8000/kiosk)
- **Admin Portal**: [http://127.0.0.1:8000/login](http://127.0.0.1:8000/login)
- **Interactive Swagger API Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 🔐 Terminal Administrator Management

FRAS provides a secure backend command-line tool [`manage_admin.py`](file:///mnt/c/Users/aarad/OneDrive/Desktop/Face%20Recognition%20Based%20Attendance%20System/manage_admin.py) to manage administrator accounts, passwords, and security directly from the terminal without web UI dependency.

```bash
# 1. Launch Interactive Security Console (password input is hidden as you type):
python manage_admin.py

# 2. List all current administrators:
python manage_admin.py list

# 3. Create or update a custom administrator account:
python manage_admin.py set --username "my_admin" --name "Lead Administrator" --email "admin@example.com"

# 4. Change an admin's password securely from terminal:
python manage_admin.py change-password --username "my_admin"

# 5. Remove the default 'admin / admin123' account permanently:
python manage_admin.py purge-default
```

All credentials use **PBKDF2-HMAC-SHA256** (100,000 rounds with random 16-byte salt). All credential changes are automatically recorded in the immutable `audit_logs` table.


---

## 🐳 Docker Deployment

The application includes an optimized multi-layer Docker configuration:

```bash
# Build and run using Docker Compose
docker compose up -d --build

# View real-time logs
docker compose logs -f

# Stop containers
docker compose down
```

---

## 🌐 Production Hosting Guide

### Step 1: Deploy on a Linux VPS (Ubuntu / Debian)
1. Provision a VPS (DigitalOcean, AWS Lightsail, Linode, or Oracle Cloud Free Tier).
2. Install Docker & Docker Compose:
   ```bash
   sudo apt update && sudo apt install -y docker.io docker-compose-v2
   ```
3. Clone your repository onto the server and configure `.env`:
   ```bash
   git clone <repo-url> /opt/fras
   cd /opt/fras
   cp .env.example .env
   nano .env  # set JWT_SECRET_KEY, ENVIRONMENT=production, and CORS_ORIGINS
   ```
4. Start the service:
   ```bash
   docker compose up -d
   ```

### Step 2: Configure Automatic HTTPS with Caddy
Modern browsers **require HTTPS** to grant webcam camera access (`navigator.mediaDevices.getUserMedia`). Using Caddy gives you automated SSL:

1. Install Caddy:
   ```bash
   sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
   curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
   curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
   sudo apt update && sudo apt install caddy
   ```
2. Copy the included `Caddyfile` to `/etc/caddy/Caddyfile`, replacing `yourdomain.com` with your domain.
3. Reload Caddy:
   ```bash
   sudo systemctl reload caddy
   ```

---

## ⚙️ Environment Configuration

| Variable | Default | Description |
|---|---|---|
| `ENVIRONMENT` | `development` | `development` or `production` |
| `HOST` | `127.0.0.1` | Network binding host |
| `PORT` | `8000` | Network port |
| `DATABASE_URL` | `sqlite:///data/attendance.db` | SQLAlchemy connection URI (SQLite or PostgreSQL) |
| `JWT_SECRET_KEY` | *(Required in prod)* | Cryptographic key used to sign access tokens |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` (24h) | Token validity duration |
| `CORS_ORIGINS` | `*` | Comma-separated list of allowed origins |
| `KIOSK_API_KEY` | *(Optional)* | Header token required on `/recognize` endpoint |
| `FACE_SIMILARITY_THRESHOLD` | `0.65` | Cosine similarity match threshold |
| `LIVENESS_LAPLACIAN_THRESHOLD` | `30.0` | Laplacian variance threshold for anti-spoofing |
| `PUNCH_COOLDOWN_SECONDS` | `600` (10m) | Cooldown window to prevent double-punches |

---

## 📡 REST API Reference

| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `POST` | `/api/v1/auth/login` | Authenticate and issue JWT cookie/token | No |
| `POST` | `/api/v1/auth/logout` | Clear session cookie | No |
| `POST` | `/api/v1/auth/change-password` | Update current user's password | Yes (JWT) |
| `POST` | `/api/v1/attendance/recognize` | Real-time face recognition and punch | Optional Kiosk Key |
| `GET` | `/api/v1/attendance/today` | List all punches recorded today | No |
| `GET` | `/api/v1/attendance/logs` | Query filtered attendance records | No |
| `POST` | `/api/v1/attendance/manual` | Record manual punch override | Admin |
| `GET` | `/api/v1/attendance/export/excel` | Stream formatted Excel report (.xlsx) | No |
| `GET` | `/api/v1/attendance/export/pdf` | Stream formatted PDF audit report | No |
| `GET` | `/api/v1/attendance/payroll/summary` | Compute payroll and overtime metrics | Admin |
| `GET` | `/api/v1/attendance/payroll/export` | Download payroll CSV | Admin |
| `GET` | `/api/v1/attendance/audit` | View administrative audit logs | Admin |
| `GET` | `/api/v1/users` | List registered staff and biometric status | No |
| `POST` | `/api/v1/users/enroll` | Enroll/update face biometrics from frames | Admin |
| `PUT` | `/api/v1/users/{id}` | Update employee profile & manual grace time | Admin |
| `DELETE` | `/api/v1/users/{id}` | Remove user and associated embeddings | Admin |
| `GET` | `/api/v1/departments` | List all departments and shifts | No |
| `POST` | `/api/v1/departments` | Create new department & shift | Admin |

---

## 🧪 Testing

Run the automated test suite:
```bash
python -m unittest discover tests
```

---

## 📄 License
This project is licensed under the MIT License.
