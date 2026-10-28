import numpy as np
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import get_db
from app.models import User, FaceEmbedding, Department, AuditLog, Shift
from app.schemas import (
    UserOut,
    UserUpdate,
    FaceEnrollRequest,
    DepartmentOut,
    DepartmentCreate,
)
from app.services.vision_engine import get_vision_engine, EmbeddingCache
from app.services.leave_service import LeaveService

router = APIRouter(prefix="/api/v1", tags=["Users & Departments"])


@router.get("/departments", response_model=List[DepartmentOut])
def list_departments(db: Session = Depends(get_db)):
    """List all available departments/shifts."""
    return db.query(Department).all()


@router.post("/departments", response_model=DepartmentOut)
def create_department(
    dept_in: DepartmentCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """Create a new department with shift parameters."""
    existing = db.query(Department).filter(Department.name == dept_in.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Department name already exists")

    dept = Department(
        name=dept_in.name,
        shift_start=dept_in.shift_start,
        shift_end=dept_in.shift_end,
        grace_period_mins=dept_in.grace_period_mins,
    )
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return dept


@router.get("/users", response_model=List[UserOut])
def list_users(
    query: Optional[str] = None,
    department_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Retrieve registered users list with biometric status and effective grace times."""
    q = db.query(User).filter(User.is_active == True)
    if department_id:
        q = q.filter(User.department_id == department_id)
    if query:
        search_filter = f"%{query}%"
        q = q.filter((User.full_name.ilike(search_filter)) | (User.user_code.ilike(search_filter)))

    users = q.order_by(User.id.desc()).all()
    results = []
    for u in users:
        has_bio = len(u.embeddings) > 0
        dept_name = u.department.name if u.department else "General"
        eff_grace = u.grace_period_mins if u.grace_period_mins is not None else (u.department.grace_period_mins if u.department else 15)
        shift_name = u.shift.name if u.shift else (u.department.shift.name if (u.department and u.department.shift) else None)

        results.append(
            UserOut(
                id=u.id,
                user_code=u.user_code,
                full_name=u.full_name,
                email=u.email,
                department_id=u.department_id,
                shift_id=u.shift_id,
                shift_name=shift_name,
                role=u.role,
                designation=u.designation,
                hourly_rate=u.hourly_rate,
                grace_period_mins=u.grace_period_mins,
                effective_grace_mins=eff_grace,
                is_active=u.is_active,
                created_at=u.created_at,
                has_biometric=has_bio,
                department_name=dept_name,
            )
        )
    return results


@router.post("/users/enroll")
def enroll_user(
    enroll_data: FaceEnrollRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """
    Enroll a new user or update biometrics with face images captured from the browser webcam.
    Validates face clarity, extracts 128-d deep embeddings, averages them, and saves to database.
    Supports individual manual grace time configuration.
    """
    # 1. Validation
    user = db.query(User).filter(User.user_code == enroll_data.user_code).first()
    is_new_user = user is None

    if not enroll_data.frames:
        raise HTTPException(status_code=400, detail="No face capture frames provided.")

    vision = get_vision_engine()
    valid_embeddings = []

    # 2. Extract Embeddings across captured frames
    for frame_b64 in enroll_data.frames:
        frame = vision.decode_base64_frame(frame_b64)
        if frame is None:
            continue

        faces = vision.detect_faces(frame)
        if faces is None or len(faces) == 0:
            continue

        primary_face = faces[0]
        emb = vision.extract_embedding(frame, primary_face)
        if emb is not None:
            valid_embeddings.append(emb)

    if not valid_embeddings:
        raise HTTPException(
            status_code=422,
            detail="Could not detect a clear frontal face in the provided images. Please retake photos in good lighting.",
        )

    # 3. Average & L2 Normalize Embeddings
    mean_vector = np.mean(valid_embeddings, axis=0)
    norm = np.linalg.norm(mean_vector)
    if norm > 1e-6:
        mean_vector = mean_vector / norm
    final_vector_list = mean_vector.tolist()

    # 4. Save User & Biometric Record (Transactional)
    try:
        if is_new_user:
            user = User(
                user_code=enroll_data.user_code.strip(),
                full_name=enroll_data.full_name.strip(),
                email=enroll_data.email.strip() if enroll_data.email else None,
                department_id=enroll_data.department_id,
                shift_id=enroll_data.shift_id,
                role=enroll_data.role or "USER",
                designation=enroll_data.designation or "Staff",
                hourly_rate=enroll_data.hourly_rate if enroll_data.hourly_rate is not None else 25.0,
                grace_period_mins=enroll_data.grace_period_mins,
                is_active=True,
            )
            db.add(user)
            db.flush()
        else:
            # Existing user - delete old embeddings and update profile
            db.query(FaceEmbedding).filter(FaceEmbedding.user_id == user.id).delete()
            user.full_name = enroll_data.full_name.strip()
            if enroll_data.email:
                user.email = enroll_data.email.strip()
            if enroll_data.department_id is not None:
                user.department_id = enroll_data.department_id
            if enroll_data.shift_id is not None:
                user.shift_id = enroll_data.shift_id
            if enroll_data.designation:
                user.designation = enroll_data.designation
            if enroll_data.hourly_rate is not None:
                user.hourly_rate = enroll_data.hourly_rate
            if enroll_data.grace_period_mins is not None:
                user.grace_period_mins = enroll_data.grace_period_mins

        face_rec = FaceEmbedding(
            user_id=user.id,
            quality_score=round(len(valid_embeddings) / len(enroll_data.frames), 2),
        )
        face_rec.set_vector(final_vector_list)
        db.add(face_rec)

        # Audit log
        audit_action = "ENROLL_USER" if is_new_user else "UPDATE_BIOMETRIC"
        audit = AuditLog(
            actor=admin.user_code,
            action=audit_action,
            details=f"{audit_action} for {user.full_name} ({user.user_code}) with {len(valid_embeddings)} frames. Grace: {user.grace_period_mins}m.",
        )
        db.add(audit)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to enroll user: {str(e)}")

    # Ensure annual leave balances are provisioned for employee
    try:
        LeaveService.ensure_user_balances(db, user.id)
    except Exception:
        pass

    # Invalidate in-memory embedding cache immediately
    EmbeddingCache.invalidate()

    return {
        "success": True,
        "message": f"User '{user.full_name}' biometric enrolled successfully with {len(valid_embeddings)} frames.",
        "user_id": user.id,
    }


@router.put("/users/{user_id}", response_model=UserOut)
@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    update_data: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """
    Update employee profile details, wage rates, and manual grace time.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    changed_fields = []
    if update_data.full_name is not None:
        user.full_name = update_data.full_name.strip()
        changed_fields.append("full_name")
    if update_data.email is not None:
        user.email = update_data.email.strip() if update_data.email else None
        changed_fields.append("email")
    if update_data.department_id is not None:
        user.department_id = update_data.department_id
        changed_fields.append("department_id")
    if "shift_id" in update_data.model_fields_set:
        user.shift_id = update_data.shift_id
        changed_fields.append("shift_id")
    if update_data.designation is not None:
        user.designation = update_data.designation.strip()
        changed_fields.append("designation")
    if update_data.hourly_rate is not None:
        user.hourly_rate = update_data.hourly_rate
        changed_fields.append("hourly_rate")
    if "grace_period_mins" in update_data.model_fields_set:
        user.grace_period_mins = update_data.grace_period_mins
        changed_fields.append(f"grace_period_mins={update_data.grace_period_mins}")
    if update_data.role is not None:
        user.role = update_data.role
        changed_fields.append("role")
    if update_data.is_active is not None:
        user.is_active = update_data.is_active
        changed_fields.append("is_active")

    audit = AuditLog(
        actor=admin.user_code,
        action="UPDATE_USER",
        details=f"Admin updated user {user.user_code}: {', '.join(changed_fields)}",
    )
    db.add(audit)
    db.commit()
    db.refresh(user)

    # Invalidate biometric cache so active status or details take effect immediately
    EmbeddingCache.invalidate()

    eff_grace = user.grace_period_mins if user.grace_period_mins is not None else (user.department.grace_period_mins if user.department else 15)
    has_bio = len(user.embeddings) > 0
    dept_name = user.department.name if user.department else "General"
    shift_name = user.shift.name if user.shift else (user.department.shift.name if (user.department and user.department.shift) else None)

    return UserOut(
        id=user.id,
        user_code=user.user_code,
        full_name=user.full_name,
        email=user.email,
        department_id=user.department_id,
        shift_id=user.shift_id,
        shift_name=shift_name,
        role=user.role,
        designation=user.designation,
        hourly_rate=user.hourly_rate,
        grace_period_mins=user.grace_period_mins,
        effective_grace_mins=eff_grace,
        is_active=user.is_active,
        created_at=user.created_at,
        has_biometric=has_bio,
        department_name=dept_name,
    )


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """Permanently delete a registered user and their biometric records."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.user_code == admin.user_code:
        raise HTTPException(status_code=400, detail="Cannot delete current logged-in administrator.")

    name = user.full_name
    code = user.user_code
    db.delete(user)

    # Invalidate in-memory embedding cache
    EmbeddingCache.invalidate()

    audit = AuditLog(
        actor=admin.user_code,
        action="DELETE_USER",
        details=f"Deleted user {name} ({code}) and associated face embeddings.",
    )
    db.add(audit)
    db.commit()

    return {"success": True, "message": f"User '{name}' ({code}) deleted successfully."}
