"""页面状态派生：由标注状态重算 images.status。每次标注变更后同事务调用。"""
from sqlalchemy.orm import Session

from ..models import CharAnnotation, Image


def recompute_page_status(db: Session, image_id: int) -> str:
    img = db.get(Image, image_id)
    if img is None:
        return ""
    active = (db.query(CharAnnotation)
              .filter_by(image_id=image_id)
              .filter(CharAnnotation.deleted_at.is_(None))
              .filter(CharAnnotation.status != "rejected"))
    total = active.count()
    if total == 0:
        status = "unannotated"
    else:
        pending = active.filter(CharAnnotation.status == "auto").count()
        status = "auto_labeled" if pending > 0 else "reviewed"
    img.status = status
    db.flush()
    return status
