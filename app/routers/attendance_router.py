from datetime import datetime, date, time, timedelta
from typing import List, Optional
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.config import KIOSK_API_KEY, logger
from app.database import get_db
from app.models import AttendanceLog, FaceEmbedding, User, Department, AuditLog
from app.schemas import (
    FaceRecognizeRequest,
    FaceRecognizeResponse,
    AttendanceLogOut,
    ManualPunchRequest,
)
from app.services.attendance_engine import AttendanceEngine
from app.services.export_service import ExportService
from app.services.payroll_service import PayrollService
from app.services.vision_engine import get_vision_engine, EmbeddingCache

router = APIRouter(prefix="/api/v1/attendance", tags=["Attendance Tracking"])


def parse_custom_datetime(dt_str: Optional[str]) -> datetime:
    """Safely parse custom date and time string from ISO or human formats."""
    if not dt_str:
        return datetime.now()
    dt_str = dt_str.strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            continue
    return datetime.now()


@router.post("/recognize", response_model=FaceRecognizeResponse)
def recognize_and_punch(
    req: FaceRecognizeRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Real-time face recognition and attendance punching endpoint called by Kiosk.
    1. Validates Kiosk API key (if configured)
    2. Decodes client webcam frame
    3. Detects frontal faces & landmarks with YuNet
    4. Runs anti-spoofing / liveness check
    5. Extracts 128-d deep embedding with SFace
    6. Cosine similarity match against high-performance in-memory embedding cache
    7. Applies debounce cooldown and determines IN/OUT status
    """
    # 0. Optional Kiosk Security Verification
    if KIOSK_API_KEY:
        kiosk_header = request.headers.get("X-Kiosk-Key") or request.query_params.get("kiosk_key")
        if kiosk_header != KIOSK_API_KEY:
            logger.warning("Unauthorized kiosk attempt: invalid or missing X-Kiosk-Key")
            return FaceRecognizeResponse(
                status="ERROR",
                message="Unauthorized Kiosk device. Invalid or missing Kiosk API Key.",
            )

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

    # 5. Load Active Embeddings from In-Memory Cache (avoids disk reads on every 450ms frame)
    registered_records = EmbeddingCache.get_embeddings(db)

    if not registered_records:
        return FaceRecognizeResponse(
            status="UNKNOWN",
            bbox=bbox,
            message="No registered users found in system. Please enroll faces first.",
        )

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
    user = db.query(User).filter(User.id == matched_user_id, User.is_active == True).first()
    if not user:
        return FaceRecognizeResponse(status="UNKNOWN", message="User record missing or inactive")

    result_status, log = AttendanceEngine.record_punch(db, user, confidence)

    dept_name = user.department.name if user.department else "General"
    punch_time_str = log.timestamp.strftime("%I:%M:%S %p") if log else datetime.now().strftime("%I:%M:%S %p")
    punch_type = log.punch_type if log else "IN"
    att_status = log.status if log else "ON_TIME"

    if result_status.startswith("COOLDOWN"):
        parts = result_status.split("_")
        remaining_secs = parts[1] if len(parts) > 1 else ""
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
            message=f"Attendance already marked for {user.full_name}. Cooldown active ({remaining_secs})." if remaining_secs else f"Attendance already marked for {user.full_name}. Cooldown active.",
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
    query: Optional[str] = None,
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
    if query:
        search_filter = f"%{query}%"
        q = q.filter((User.full_name.ilike(search_filter)) | (User.user_code.ilike(search_filter)))

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
    query: Optional[str] = None,
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
    if query:
        search_filter = f"%{query}%"
        q = q.filter((User.full_name.ilike(search_filter)) | (User.user_code.ilike(search_filter)))

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
    """
    Manually record custom punch IN, punch OUT, or both (full shift)
    with custom date, time, punctuality status, and audit trail.
    """
    user = db.query(User).filter(User.id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    p_type = req.punch_type.upper().strip()
    in_dt = parse_custom_datetime(req.custom_timestamp)

    if p_type == "BOTH":
        # Record both IN and OUT for a complete shift
        out_dt = parse_custom_datetime(req.out_timestamp) if req.out_timestamp else (in_dt + timedelta(hours=8))
        if out_dt <= in_dt:
            out_dt = in_dt + timedelta(hours=8)

        log_in = AttendanceLog(
            user_id=user.id,
            timestamp=in_dt,
            punch_type="IN",
            status=req.status or "ON_TIME",
            confidence_score=1.0,
            device_id=f"ADMIN-MANUAL-{admin.user_code}",
        )
        log_out = AttendanceLog(
            user_id=user.id,
            timestamp=out_dt,
            punch_type="OUT",
            status="ON_TIME",
            confidence_score=1.0,
            device_id=f"ADMIN-MANUAL-{admin.user_code}",
        )
        db.add(log_in)
        db.add(log_out)

        details_msg = (
            f"Manual full shift: IN at {in_dt.strftime('%Y-%m-%d %I:%M %p')} ({req.status}), "
            f"OUT at {out_dt.strftime('%Y-%m-%d %I:%M %p')}. Note: {req.notes or 'None'}"
        )
        audit = AuditLog(
            actor=admin.user_code,
            action="MANUAL_SHIFT_PUNCH",
            details=f"User {user.full_name} ({user.user_code}): {details_msg}",
            timestamp=datetime.now(),
        )
        db.add(audit)
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("Failed to commit manual full shift punch: %s", e)
            raise HTTPException(status_code=500, detail="Database transaction failed while saving manual shift.")

        return {
            "success": True,
            "message": f"Full shift (IN & OUT) successfully recorded for {user.full_name}!",
        }

    # Single punch (IN or OUT)
    log = AttendanceLog(
        user_id=user.id,
        timestamp=in_dt,
        punch_type=p_type,
        status=req.status or "ON_TIME",
        confidence_score=1.0,
        device_id=f"ADMIN-MANUAL-{admin.user_code}",
    )
    db.add(log)

    audit = AuditLog(
        actor=admin.user_code,
        action=f"MANUAL_PUNCH_{p_type}",
        details=f"Manual {p_type} punch ({req.status}) for {user.full_name} ({user.user_code}) at {in_dt.strftime('%Y-%m-%d %I:%M %p')}. Note: {req.notes or 'None'}",
        timestamp=datetime.now(),
    )
    db.add(audit)
    try:
        db.commit()
        db.refresh(log)
    except Exception as e:
        db.rollback()
        logger.error("Failed to commit manual punch: %s", e)
        raise HTTPException(status_code=500, detail="Database transaction failed while saving manual punch.")

    return {
        "success": True,
        "message": f"Manual {p_type} punch recorded for {user.full_name} at {in_dt.strftime('%d %b %Y, %I:%M %p')}",
    }


@router.get("/payroll/summary")
def get_payroll_summary(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    department_id: Optional[int] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """Compute role-based payroll summary, total hours, and employee payouts."""
    return PayrollService.compute_payroll(
        db,
        start_date=start_date,
        end_date=end_date,
        department_id=department_id,
    )


@router.get("/payroll/export")
def export_payroll(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    department_id: Optional[int] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """Export computed workforce payroll to downloadable CSV."""
    data = PayrollService.compute_payroll(
        db,
        start_date=start_date,
        end_date=end_date,
        department_id=department_id,
    )
    stream = PayrollService.export_payroll_csv(data)
    filename = f"payroll_report_{start_date or 'current'}_{end_date or 'period'}.csv"
    return StreamingResponse(
        stream,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/audit")
def get_audit_logs(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """Retrieve system security & administrative audit trails."""
    logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit).all()
    return [
        {
            "id": l.id,
            "actor": l.actor,
            "action": l.action,
            "details": l.details,
            "timestamp": l.timestamp.strftime("%Y-%m-%d %I:%M:%S %p"),
        }
        for l in logs
    ]
