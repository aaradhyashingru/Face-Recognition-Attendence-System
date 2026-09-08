from datetime import datetime, date, time
from typing import List, Optional
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import get_db
from app.models import AttendanceLog, FaceEmbedding, User, Department
from app.schemas import (
    FaceRecognizeRequest,
    FaceRecognizeResponse,
    AttendanceLogOut,
    ManualPunchRequest,
)
from app.services.attendance_engine import AttendanceEngine
from app.services.export_service import ExportService
from app.services.vision_engine import get_vision_engine

router = APIRouter(prefix="/api/v1/attendance", tags=["Attendance Tracking"])


@router.post("/recognize", response_model=FaceRecognizeResponse)
def recognize_and_punch(
    req: FaceRecognizeRequest,
    db: Session = Depends(get_db),
):
    """
    Real-time face recognition and attendance punching endpoint called by Kiosk.
    1. Decodes client webcam frame
    2. Detects frontal faces & landmarks with YuNet
    3. Runs anti-spoofing / liveness check
    4. Extracts 128-d deep embedding with SFace
    5. Cosine similarity match against database embeddings
    6. Applies debounce cooldown and determines IN/OUT status
    """
    vision = get_vision_engine()

    # 1. Decode Frame
    frame = vision.decode_base64_frame(req.frame)
    if frame is None:
        return FaceRecognizeResponse(status="ERROR", message="Invalid image frame received")

    # 2. Detect Faces
    faces = vision.detect_faces(frame)
    if faces is None or len(faces) == 0:
        return FaceRecognizeResponse(status="NO_FACE", message="No face detected in camera")

    primary_face = faces[0]
    x, y, w, h = map(int, primary_face[0:4])
    bbox = [x, y, w, h]

    # 3. Anti-Spoofing & Liveness Check
    is_live, liveness_score = vision.check_liveness(frame, primary_face)
    if not is_live:
        return FaceRecognizeResponse(
            status="SPOOF_DETECTED",
            confidence=liveness_score,
            bbox=bbox,
            liveness_score=liveness_score,
            message="Spoof alert! Texture/screen reflection failed liveness check.",
        )

    # 4. Extract Query Embedding
    query_vec = vision.extract_embedding(frame, primary_face)
    if query_vec is None:
        return FaceRecognizeResponse(status="NO_FACE", message="Could not extract facial features")

    # 5. Load Active Embeddings
    all_embeddings = (
        db.query(FaceEmbedding)
        .join(User)
        .filter(User.is_active == True)
        .all()
    )

    if not all_embeddings:
        return FaceRecognizeResponse(
            status="UNKNOWN",
            bbox=bbox,
            message="No registered users found in system. Please enroll faces first.",
        )

    registered_records = [
        (emb.user_id, np.array(emb.get_vector(), dtype=np.float32))
        for emb in all_embeddings
    ]

    # 6. Perform Cosine Similarity Match
    matched_user_id, confidence = vision.match_embedding(query_vec, registered_records)

    if matched_user_id is None:
        return FaceRecognizeResponse(
            status="UNKNOWN",
            confidence=confidence,
            bbox=bbox,
            message="Unrecognized face. Access denied.",
        )

    # 7. Record Attendance & Apply Business Rules
    user = db.query(User).filter(User.id == matched_user_id).first()
    if not user:
        return FaceRecognizeResponse(status="UNKNOWN", message="User record missing")

    result_status, log = AttendanceEngine.record_punch(db, user, confidence)

    dept_name = user.department.name if user.department else "General"
    punch_time_str = log.timestamp.strftime("%I:%M:%S %p") if log else datetime.now().strftime("%I:%M:%S %p")
    punch_type = log.punch_type if log else "IN"
    att_status = log.status if log else "ON_TIME"

    if result_status.startswith("COOLDOWN"):
        remaining_secs = result_status.split("_")[1]
        return FaceRecognizeResponse(
            status="COOLDOWN",
            user_code=user.user_code,
            full_name=user.full_name,
            department=dept_name,
            punch_type=punch_type,
            punch_time=punch_time_str,
            attendance_status=att_status,
            confidence=confidence,
            bbox=bbox,
            message=f"Attendance already marked for {user.full_name}. Cooldown active ({remaining_secs}).",
        )

    return FaceRecognizeResponse(
        status="SUCCESS",
        user_code=user.user_code,
        full_name=user.full_name,
        department=dept_name,
        punch_type=punch_type,
        punch_time=punch_time_str,
        attendance_status=att_status,
        confidence=confidence,
        bbox=bbox,
        message=f"Punch recorded: {user.full_name} ({punch_type}) - {att_status}",
    )


@router.get("/today", response_model=List[AttendanceLogOut])
def get_today_attendance(db: Session = Depends(get_db)):
    """Retrieve all attendance punches recorded today."""
    today_start = datetime.combine(date.today(), time.min)
    logs = (
        db.query(AttendanceLog)
        .filter(AttendanceLog.timestamp >= today_start)
        .order_by(AttendanceLog.timestamp.desc())
        .all()
    )

    results = []
    for log in logs:
        dept_name = log.user.department.name if log.user and log.user.department else "General"
        results.append(
            AttendanceLogOut(
                id=log.id,
                user_id=log.user_id,
                user_code=log.user.user_code if log.user else "N/A",
                full_name=log.user.full_name if log.user else "Unknown",
                department_name=dept_name,
                timestamp=log.timestamp,
                punch_type=log.punch_type,
                status=log.status,
                confidence_score=log.confidence_score,
                device_id=log.device_id,
            )
        )
    return results


@router.get("/logs")
def get_attendance_logs(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    department_id: Optional[int] = None,
    query: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Filter attendance records by date range, department, and user keyword."""
    q = db.query(AttendanceLog).join(User)

    if start_date:
        try:
            s_dt = datetime.strptime(start_date, "%Y-%m-%d")
            q = q.filter(AttendanceLog.timestamp >= s_dt)
        except ValueError:
            pass

    if end_date:
        try:
            e_dt = datetime.combine(datetime.strptime(end_date, "%Y-%m-%d"), time.max)
            q = q.filter(AttendanceLog.timestamp <= e_dt)
        except ValueError:
            pass

    if department_id:
        q = q.filter(User.department_id == department_id)

    if query:
        search_filter = f"%{query}%"
        q = q.filter((User.full_name.ilike(search_filter)) | (User.user_code.ilike(search_filter)))

    logs = q.order_by(AttendanceLog.timestamp.desc()).all()

    return [
        {
            "id": l.id,
            "user_code": l.user.user_code if l.user else "N/A",
            "full_name": l.user.full_name if l.user else "Unknown",
            "department": l.user.department.name if l.user and l.user.department else "General",
            "date": l.timestamp.strftime("%Y-%m-%d"),
            "time": l.timestamp.strftime("%I:%M:%S %p"),
            "punch_type": l.punch_type,
            "status": l.status,
            "confidence": l.confidence_score,
        }
        for l in logs
    ]


@router.get("/export/excel")
def export_excel(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    department_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Stream formatted Excel (.xlsx) file download."""
    q = db.query(AttendanceLog).join(User)
    if start_date:
        try:
            s_dt = datetime.strptime(start_date, "%Y-%m-%d")
            q = q.filter(AttendanceLog.timestamp >= s_dt)
        except ValueError:
            pass
    if end_date:
        try:
            e_dt = datetime.combine(datetime.strptime(end_date, "%Y-%m-%d"), time.max)
            q = q.filter(AttendanceLog.timestamp <= e_dt)
        except ValueError:
            pass
    if department_id:
        q = q.filter(User.department_id == department_id)

    logs = q.order_by(AttendanceLog.timestamp.asc()).all()
    stream = ExportService.generate_excel(logs)

    filename = f"attendance_report_{date.today().strftime('%Y_%m_%d')}.xlsx"
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/export/pdf")
def export_pdf(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    department_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Stream formatted PDF audit report download."""
    q = db.query(AttendanceLog).join(User)
    if start_date:
        try:
            s_dt = datetime.strptime(start_date, "%Y-%m-%d")
            q = q.filter(AttendanceLog.timestamp >= s_dt)
        except ValueError:
            pass
    if end_date:
        try:
            e_dt = datetime.combine(datetime.strptime(end_date, "%Y-%m-%d"), time.max)
            q = q.filter(AttendanceLog.timestamp <= e_dt)
        except ValueError:
            pass
    if department_id:
        q = q.filter(User.department_id == department_id)

    logs = q.order_by(AttendanceLog.timestamp.asc()).all()
    stream = ExportService.generate_pdf(logs)

    filename = f"attendance_report_{date.today().strftime('%Y_%m_%d')}.pdf"
    return StreamingResponse(
        stream,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/manual")
def manual_punch(
    req: ManualPunchRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """Manually record a punch for a student/employee by Admin."""
    user = db.query(User).filter(User.id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    log = AttendanceLog(
        user_id=user.id,
        timestamp=datetime.now(),
        punch_type=req.punch_type,
        status=req.status,
        confidence_score=1.0,
        device_id=f"ADMIN-OVERRIDE-{admin.user_code}",
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    return {"success": True, "message": f"Manual punch added for {user.full_name}"}
