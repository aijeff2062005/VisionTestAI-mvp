"""Sync face gallery between VectorDB (+ media) and AiFace panel."""

from __future__ import annotations

import base64
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

from ac.face_client import AiFaceClient, FaceClient, STRANGER_ENROLL_ID
from ac.hospital_client import HospitalClient
from ac.media_client import MediaClient
from ac.vector_face_client import FaceRecord, VectorFaceClient

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    attempted: int = 0
    loaded: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)
    loaded_enroll_ids: list[int] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "loaded": self.loaded,
            "skipped": self.skipped,
            "failed": self.failed,
            "errors": self.errors[:20],
            "loaded_enroll_ids": self.loaded_enroll_ids,
        }


def _norm_face_name(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _device_user_rows(face: AiFaceClient) -> list[dict[str, Any]]:
    try:
        ulist = face._api({"cmd": "getuserlist", "stn": True})
    except Exception as exc:  # noqa: BLE001
        logger.debug("getuserlist for sync skip-map failed: %s", exc)
        return []
    rows = ulist.get("record") or []
    return rows if isinstance(rows, list) else []


def _device_face_ids(face: AiFaceClient) -> set[int]:
    """enroll_ids that already have a matchable Face on the panel."""
    out: set[int] = set()
    for row in _device_user_rows(face):
        try:
            if int(row.get("face") or 0) > 0:
                out.add(int(row["id"]))
        except (TypeError, ValueError, KeyError):
            continue
    return out


def _gallery_version(media_get_url: str | None, image_b64: str | None) -> str:
    source = media_get_url or image_b64 or ""
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _gallery_current(
    face: AiFaceClient,
    enroll_id: int,
    name: str,
    version: str,
    rows: list[dict[str, Any]] | None = None,
) -> bool:
    if face.gallery_version(enroll_id) != version:
        return False
    for row in rows if rows is not None else _device_user_rows(face):
        try:
            if int(row.get("id")) != enroll_id:
                continue
            return int(row.get("face") or 0) > 0 and _norm_face_name(row.get("name")) == _norm_face_name(name)
        except (TypeError, ValueError):
            continue
    return False


def _as_jpeg(data: bytes | None) -> bytes | None:
    if not data or len(data) < 100 or data[:2] != b"\xff\xd8":
        return None
    return data


def _resolve_photo_bytes(
    rec: FaceRecord,
    vector: VectorFaceClient,
    media: MediaClient | None,
) -> bytes | None:
    """Always try to get a real JPEG: media → VectorDB image → JPEG template."""
    if media and media.enabled and rec.media_get_url:
        try:
            data = _as_jpeg(media.download_bytes(rec.media_get_url))
            if data:
                return data
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "media download failed enroll_id=%s url=%s: %s",
                rec.enroll_id,
                rec.media_get_url,
                exc,
            )

    # VectorDB local image (GET /v1/faces/{id}/image or image_b64 on get)
    data = _as_jpeg(vector.fetch_image_bytes(rec))
    if data:
        return data

    # Full get often includes image_b64 even when list does not
    try:
        full = vector.get_face(rec.enroll_id)
    except Exception:  # noqa: BLE001
        full = None
    if full is not None:
        data = _as_jpeg(vector.fetch_image_bytes(full))
        if data:
            return data
        if full.image_b64:
            try:
                data = _as_jpeg(base64.b64decode(full.image_b64))
                if data:
                    return data
            except Exception:  # noqa: BLE001
                pass
        tmpl = (full.device_template_b64 or rec.device_template_b64 or "").strip()
    else:
        tmpl = (rec.device_template_b64 or "").strip()

    if tmpl:
        try:
            data = _as_jpeg(base64.b64decode(tmpl))
            if data:
                return data
        except Exception:  # noqa: BLE001
            pass
    return None


def sync_vectordb_to_device(
    vector: VectorFaceClient,
    face: FaceClient,
    *,
    max_faces: int = 500,
    device_face_backupnum: int = 50,
    replace_existing: bool = False,
    media: MediaClient | None = None,
) -> SyncResult:
    """Pull faces from VectorDB (+ images) onto the Face ID panel.

    Always loads the JPEG (media or VectorDB) and pushes it to the panel
    (backupnum 50). Does **not** wipe users that already have Face=1 unless
    ``replace_existing``; still refreshes missing display photos.
    """
    result = SyncResult()
    if not getattr(vector, "enabled", False):
        logger.info("VectorDB sync skipped — gallery client disabled")
        return result
    if not isinstance(face, AiFaceClient) or not face.enabled:
        logger.info("VectorDB sync skipped — AiFace device not enabled")
        return result

    try:
        records = vector.list_faces(limit=max_faces)
    except Exception as exc:  # noqa: BLE001
        msg = f"list_faces failed: {exc}"
        logger.exception(msg)
        result.errors.append(msg)
        return result

    already = _device_face_ids(face)
    logger.info(
        "VectorDB → device sync: %d face(s); device already has Face for %d id(s)",
        len(records),
        len(already),
    )
    for rec in records:
        result.attempted += 1
        try:
            photo = _resolve_photo_bytes(rec, vector, media)
            if not photo:
                result.failed += 1
                err = f"enroll_id={rec.enroll_id}: no JPEG in VectorDB/media"
                result.errors.append(err)
                logger.warning("Sync face failed %s", err)
                continue

            has_face = rec.enroll_id in already and not replace_existing
            if has_face:
                # Keep matchable Face; still push image if display photo missing.
                if face._user_has_face_photo(rec.enroll_id):
                    result.skipped += 1
                    logger.info(
                        "Skip enroll_id=%s — device already has Face + photo",
                        rec.enroll_id,
                    )
                    continue
                pushed = face._push_display_photo(rec.enroll_id, rec.full_name, photo)
                if pushed:
                    result.loaded += 1
                    result.loaded_enroll_ids.append(rec.enroll_id)
                    logger.info(
                        "Refreshed display JPEG on device enroll_id=%s (%d bytes)",
                        rec.enroll_id,
                        len(photo),
                    )
                else:
                    result.failed += 1
                    result.errors.append(f"enroll_id={rec.enroll_id}: photo push failed")
                continue

            ok = _upsert_one(
                face,
                vector,
                rec,
                backupnum=device_face_backupnum,
                replace_existing=bool(replace_existing),
                media=media,
                photo=photo,
            )
            if ok:
                result.loaded += 1
                result.loaded_enroll_ids.append(rec.enroll_id)
            else:
                result.skipped += 1
        except Exception as exc:  # noqa: BLE001
            result.failed += 1
            err = f"enroll_id={rec.enroll_id}: {exc}"
            result.errors.append(err)
            logger.warning("Sync face failed %s", err)

    logger.info(
        "VectorDB sync done loaded=%s skipped=%s failed=%s",
        result.loaded,
        result.skipped,
        result.failed,
    )
    return result


def _upsert_one(
    face: AiFaceClient,
    vector: VectorFaceClient,
    rec: FaceRecord,
    *,
    backupnum: int,
    replace_existing: bool,
    media: MediaClient | None = None,
    photo: bytes | None = None,
) -> bool:
    if rec.enroll_id <= 0 or rec.enroll_id == 99999999:
        logger.warning("Skip invalid enroll_id=%s", rec.enroll_id)
        return False

    template = (rec.device_template_b64 or "").strip()
    photo_bytes = photo if photo is not None else _resolve_photo_bytes(rec, vector, media)

    # Prefer real JPEG onto backupnum 50 (panel avatar / Face photo).
    # If template is itself JPEG, use it as the photo payload.
    tmpl_is_jpeg = False
    if template:
        try:
            tmpl_is_jpeg = base64.b64decode(template)[:2] == b"\xff\xd8"
        except Exception:  # noqa: BLE001
            tmpl_is_jpeg = False
    if tmpl_is_jpeg and not photo_bytes:
        try:
            photo_bytes = base64.b64decode(template)
        except Exception:  # noqa: BLE001
            photo_bytes = None

    if not photo_bytes or not _as_jpeg(photo_bytes):
        logger.warning(
            "Skip enroll_id=%s name=%s — no usable JPEG image to sync "
            "(VectorDB/media empty)",
            rec.enroll_id,
            rec.full_name,
        )
        return False

    logger.info(
        "Syncing enroll_id=%s name=%s image=%d bytes template=%s",
        rec.enroll_id,
        rec.full_name,
        len(photo_bytes),
        "jpeg" if tmpl_is_jpeg else ("yes" if template else "no"),
    )

    return face.upsert_gallery_user(
        enroll_id=rec.enroll_id,
        full_name=rec.full_name,
        # Native non-JPEG template if present; otherwise push JPEG as record.
        device_template_b64=(None if tmpl_is_jpeg else (template or None)),
        photo_bytes=photo_bytes,
        backupnum=backupnum,
        replace_existing=replace_existing,
    )


def _resolve_gallery_photo_bytes(
    *,
    media_get_url: str | None,
    image_b64: str | None,
    media: MediaClient | None,
) -> bytes | None:
    url = (media_get_url or "").strip()
    # Desk enroll fallback stores data:image/jpeg;base64,... on Patient when media upload fails.
    if url.startswith("data:") and "," in url:
        try:
            data = _as_jpeg(base64.b64decode(url.split(",", 1)[1]))
            if data:
                return data
        except Exception as exc:  # noqa: BLE001
            logger.warning("data-URL avatar decode failed: %s", exc)
    elif media and media.enabled and url.startswith("http"):
        try:
            data = _as_jpeg(media.download_bytes(url))
            if data:
                return data
        except Exception as exc:  # noqa: BLE001
            logger.warning("media download failed url=%s: %s", url[:120], exc)
    if image_b64:
        try:
            raw = image_b64
            if raw.startswith("data:") and "," in raw:
                raw = raw.split(",", 1)[1]
            data = _as_jpeg(base64.b64decode(raw))
            if data:
                return data
        except Exception:  # noqa: BLE001
            pass
    return None


def push_one_face_to_device(
    face: FaceClient,
    media: MediaClient | None,
    *,
    enroll_id: int,
    full_name: str,
    media_get_url: str | None = None,
    image_b64: str | None = None,
    backupnum: int = 50,
) -> bool:
    """Push a single desk-enrolled face JPEG onto the AiFace panel."""
    if not isinstance(face, AiFaceClient) or not face.enabled:
        logger.info("push_one skipped — AiFace device not enabled")
        return False
    eid = int(enroll_id)
    if eid <= 0 or eid == STRANGER_ENROLL_ID:
        logger.warning("push_one skipped invalid enroll_id=%s", eid)
        return False
    name = str(full_name or "").strip() or f"user-{eid}"
    version = _gallery_version(media_get_url, image_b64)
    with face.gallery_lock:
        if _gallery_current(face, eid, name, version):
            logger.info("push_one enroll_id=%s already ready; no reload", eid)
            return True
    # Media may be slow; never hold the panel write lock while downloading.
    photo = _resolve_gallery_photo_bytes(
        media_get_url=media_get_url,
        image_b64=image_b64,
        media=media,
    )
    if not photo:
        logger.warning("push_one enroll_id=%s — no usable JPEG", eid)
        return False
    with face.gallery_lock:
        if _gallery_current(face, eid, name, version):
            return True
        ok = face.upsert_gallery_user(
            enroll_id=eid,
            full_name=name,
            photo_bytes=photo,
            backupnum=backupnum,
            replace_existing=True,
        )
        if ok:
            face.set_gallery_version(eid, version)
        return ok


def wipe_device_gallery(
    face: FaceClient,
    *,
    preserve_stranger: bool = True,
) -> dict[str, Any]:
    """Remove all users from the AiFace panel (overnight wipe).

    Preserves stranger enroll_id 99999999 when ``preserve_stranger`` is true.
    """
    if not isinstance(face, AiFaceClient) or not face.enabled:
        logger.info("wipe_device_gallery skipped — AiFace device not enabled")
        return {"deleted": 0, "deleted_ids": [], "skipped": True}
    with face.gallery_lock:
        return _wipe_device_gallery_locked(face, preserve_stranger=preserve_stranger)


def _wipe_device_gallery_locked(face: AiFaceClient, *, preserve_stranger: bool) -> dict[str, Any]:
    deleted: list[int] = []
    try:
        ulist = face._api({"cmd": "getuserlist", "stn": True})
    except Exception as exc:  # noqa: BLE001
        logger.exception("wipe getuserlist failed: %s", exc)
        return {"deleted": 0, "deleted_ids": deleted, "error": str(exc)}
    for row in ulist.get("record") or []:
        try:
            eid = int(row["id"])
        except (TypeError, ValueError, KeyError):
            continue
        if preserve_stranger and eid == STRANGER_ENROLL_ID:
            continue
        try:
            face.delete_user(eid)
            deleted.append(eid)
        except Exception as exc:  # noqa: BLE001
            logger.warning("wipe delete_user enroll_id=%s failed: %s", eid, exc)
    logger.info("wipe_device_gallery deleted %d user(s)", len(deleted))
    return {"deleted": len(deleted), "deleted_ids": deleted}


def sync_today_appointments_to_device(
    hospital: HospitalClient,
    face: FaceClient,
    media: MediaClient | None,
    *,
    max_faces: int = 500,
    device_face_backupnum: int = 50,
    prune_not_in_today: bool = True,
    appointment_type: str | None = None,
) -> SyncResult:
    """Pull today's appointment faces from Frappe onto the AiFace panel."""
    if not isinstance(face, AiFaceClient) or not face.enabled:
        return SyncResult()
    gallery = hospital.list_today_face_gallery(appointment_type=appointment_type)
    if not gallery.get("success"):
        result = SyncResult()
        msg = f"list_today_face_gallery failed: {gallery.get('error') or gallery}"
        logger.warning(msg)
        result.errors.append(msg)
        return result
    # Do not hold the panel's write lock while the Frappe request waits.
    with face.gallery_lock:
        return _sync_today_appointments_locked(
            gallery, face, media, max_faces=max_faces,
            device_face_backupnum=device_face_backupnum,
            prune_not_in_today=prune_not_in_today,
        )


def _sync_today_appointments_locked(
    gallery: dict[str, Any],
    face: AiFaceClient,
    media: MediaClient | None,
    *,
    max_faces: int,
    device_face_backupnum: int,
    prune_not_in_today: bool,
) -> SyncResult:
    result = SyncResult()

    faces = gallery.get("faces") or []
    if max_faces > 0:
        faces = faces[:max_faces]
    today_ids: set[int] = set()
    for row in faces:
        try:
            eid = int(row.get("enroll_id"))
        except (TypeError, ValueError):
            continue
        if eid > 0 and eid != STRANGER_ENROLL_ID:
            today_ids.add(eid)
    for raw_id in gallery.get("protected_enroll_ids") or []:
        try:
            eid = int(raw_id)
        except (TypeError, ValueError):
            continue
        if eid > 0 and eid != STRANGER_ENROLL_ID:
            today_ids.add(eid)

    device_rows = _device_user_rows(face)
    already = {int(row["id"]) for row in device_rows if str(row.get("id", "")).isdigit() and int(row.get("face") or 0) > 0}
    logger.info(
        "Today appointments → device sync: %d face(s); device already has Face for %d id(s)",
        len(faces),
        len(already),
    )

    for row in faces:
        result.attempted += 1
        try:
            eid_raw = row.get("enroll_id")
            if eid_raw in (None, "", 0):
                result.skipped += 1
                continue
            eid = int(eid_raw)
            if eid <= 0 or eid == STRANGER_ENROLL_ID:
                result.skipped += 1
                continue
            media_url = (row.get("media_get_url") or "").strip() or None
            image_b64 = (row.get("image_b64") or "").strip() or None
            if not media_url and not image_b64:
                result.failed += 1
                err = f"enroll_id={eid}: no media_get_url or image_b64"
                result.errors.append(err)
                continue
            name = str(
                row.get("full_name")
                or row.get("patient_name")
                or row.get("patient")
                or f"user-{eid}"
            ).strip()

            if _gallery_current(face, eid, name, _gallery_version(media_url, image_b64), device_rows):
                result.skipped += 1
                continue

            ok = push_one_face_to_device(
                face,
                media,
                enroll_id=eid,
                full_name=name,
                media_get_url=media_url,
                image_b64=image_b64,
                backupnum=device_face_backupnum,
            )
            if ok:
                result.loaded += 1
                result.loaded_enroll_ids.append(eid)
            else:
                result.failed += 1
                result.errors.append(f"enroll_id={eid}: upsert failed")
        except Exception as exc:  # noqa: BLE001
            result.failed += 1
            err = f"face row: {exc}"
            result.errors.append(err)
            logger.warning("Today sync face failed %s", err)

    if prune_not_in_today and today_ids:
        try:
            ulist = face._api({"cmd": "getuserlist", "stn": True})
            for row in ulist.get("record") or []:
                try:
                    eid = int(row["id"])
                except (TypeError, ValueError, KeyError):
                    continue
                if eid == STRANGER_ENROLL_ID:
                    continue
                if eid not in today_ids:
                    if face.delete_user(eid):
                        logger.info("Pruned device user enroll_id=%s (not in today's appointments)", eid)
                    else:
                        result.failed += 1
                        result.errors.append(f"enroll_id={eid}: device delete not confirmed")
        except Exception as exc:  # noqa: BLE001
            msg = f"prune_not_in_today failed: {exc}"
            logger.warning(msg)
            result.errors.append(msg)

    logger.info(
        "Today appointment sync done loaded=%s skipped=%s failed=%s",
        result.loaded,
        result.skipped,
        result.failed,
    )
    return result


def push_device_face_to_vectordb(
    face: FaceClient,
    vector: VectorFaceClient,
    *,
    enroll_id: int,
    full_name: str | None = None,
    patient_id: str | None = None,
    media: MediaClient | None = None,
    session_id: str | None = None,
) -> bool:
    """After on-device register: upload Face JPEG to media + metadata to VectorDB."""
    if not getattr(vector, "enabled", False):
        logger.info("VectorDB push skipped — gallery client disabled")
        return False
    if not isinstance(face, AiFaceClient) or not face.enabled:
        logger.info("VectorDB push skipped — AiFace device not enabled")
        return False

    exported = face.export_gallery_face(int(enroll_id))
    if not exported:
        logger.warning(
            "Cannot push enroll_id=%s to VectorDB — no Face template on device yet",
            enroll_id,
        )
        return False

    name = (full_name or exported.get("full_name") or f"user-{enroll_id}").strip()
    image_b64 = exported.get("image_b64")
    template = exported.get("device_template_b64")
    media_get_url: str | None = None

    # Prefer durable media object for the face JPEG.
    jpeg: bytes | None = None
    if image_b64:
        try:
            jpeg = base64.b64decode(image_b64)
        except Exception:  # noqa: BLE001
            jpeg = None
    if (not jpeg or jpeg[:2] != b"\xff\xd8") and template:
        try:
            raw = base64.b64decode(template)
            if raw[:2] == b"\xff\xd8":
                jpeg = raw
                image_b64 = template
        except Exception:  # noqa: BLE001
            pass

    if media and media.enabled and jpeg and len(jpeg) >= 100:
        try:
            ready = media.upload_bytes(
                jpeg,
                session_id=session_id or f"face-{enroll_id}",
                kind="face_jpeg",
                content_type="image/jpeg",
                filename=f"enroll_{enroll_id}.jpg",
            )
            media_get_url = str(ready.get("get_url") or "") or None
            logger.info(
                "Face JPEG → media enroll_id=%s key=%s",
                enroll_id,
                ready.get("object_key"),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Media upload failed enroll_id=%s: %s (VectorDB still gets b64)", enroll_id, exc)

    try:
        ok = vector.upsert_face(
            enroll_id=int(enroll_id),
            full_name=name,
            patient_id=patient_id,
            device_template_b64=template,
            image_b64=image_b64,
            media_get_url=media_get_url,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("VectorDB push failed enroll_id=%s: %s", enroll_id, exc)
        return False
    logger.info(
        "VectorDB updated enroll_id=%s name=%s media_url=%s ok=%s",
        enroll_id,
        name,
        media_get_url,
        ok,
    )
    return bool(ok)
