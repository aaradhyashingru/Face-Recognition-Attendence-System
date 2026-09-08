import numpy as np
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import get_db
from app.models import User, FaceEmbedding, Department, AuditLog
from app.schemas import (
    UserOut,
    FaceEnrollRequest,
    DepartmentOut,
    DepartmentCreate,
)
from app.services.vision_engine import get_vision_engine

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
    """Retrieve registered users list with biometric status."""
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
        results.append(
            UserOut(
                id=u.id,
                user_code=u.user_code,
                full_name=u.full_name,
                email=u.email,
                department_id=u.department_id,
                role=u.role,
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
    Enroll a new user with face images captured from the browser webcam.
    Validates face clarity, extracts 128-d deep embeddings, averages them, and saves to database.
    """
    # 1. Validation
    existing = db.query(User).filter(User.user_code == enroll_data.user_code).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"User with ID/Roll '{enroll_data.user_code}' already exists.",
        )

    if not enroll_data.frames:
        raise HTTPException(status_code=400, detail="No face capture frames provided.")

    vision = get_vision_engine()
    valid_embeddings = []

    # 2. Extract Embeddings across captured frames
    for idx, frame_b64 in enumerate(enroll_data.frames):
        frame = vision.decode_base64_frame(frame_b64)
        if frame is None:
            continue

        faces = vision.detect_faces(frame)
        if faces is None or len(faces) == 0:
            continue

        # Use highest confidence face
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

    # 4. Save User & Biometric Record
    user = User(
        user_code=enroll_data.user_code.strip(),
        full_name=enroll_data.full_name.strip(),
        email=enroll_data.email.strip() if enroll_data.email else None,
        department_id=enroll_data.department_id,
        role="USER",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    face_rec = FaceEmbedding(
        user_id=user.id,
        quality_score=round(len(valid_embeddings) / len(enroll_data.frames), 2),
    )
    face_rec.set_vector(final_vector_list)
    db.add(face_rec)

    # Audit log
    audit = AuditLog(
        actor=admin.user_code,
        action="ENROLL_USER",
        details=f"Enrolled user {user.full_name} ({user.user_code}) with {len(valid_embeddings)} biometric samples.",
    )
    db.add(audit)
    db.commit()

    return {
        "success": True,
        "message": f"User '{user.full_name}' enrolled successfully with {len(valid_embeddings)} biometric frames.",
        "user_id": user.id,
    }


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

    audit = AuditLog(
        actor=admin.user_code,
        action="DELETE_USER",
        details=f"Deleted user {name} ({code}) and associated face embeddings.",
    )
    db.add(audit)
    db.commit()

    return {"success": True, "message": f"User '{name}' ({code}) deleted successfully."}
