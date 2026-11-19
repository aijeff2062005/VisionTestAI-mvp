from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

import frappe

from smart_hospital.service.face_service import (
    register_without_mask,
    verify_face,
)


def _require_ffmpeg() -> None:
    """CRITICAL: GDU / Milvus / Attu registration cannot run without ffmpeg.

    Desk posts WebM; this module converts to MP4 then calls
    POST /api/v2/face_registration/without_mask. Missing binary → FileNotFoundError
    and the face never reaches Attu.
    """
    if shutil.which("ffmpeg"):
        return
    frappe.throw(
        "CRITICAL: ffmpeg is not installed in the Frappe backend container. "
        "GDU face registration (WebM→MP4 → /api/v2/face_registration/without_mask → Milvus/Attu) "
        "requires ffmpeg in visiontestai-frappe-backend / image visiontestai/frappe:clinic. "
        "Install: apt-get install -y ffmpeg"
    )


def _convert_webm_to_mp4(video_file):
    """
    Convert uploaded WebM video to MP4 using FFmpeg.

    CRITICAL: ffmpeg must be present in the Frappe backend image.

    Input:
        video_file: Uploaded file from Frappe request

    Returns:
        Path to temporary MP4 file
    """
    _require_ffmpeg()

    # Tạo file tạm cho WebM
    webm_file = tempfile.NamedTemporaryFile(
        suffix=".webm",
        delete=False,
    )

    # Tạo file tạm cho MP4
    mp4_file = tempfile.NamedTemporaryFile(
        suffix=".mp4",
        delete=False,
    )

    input_path = webm_file.name
    output_path = mp4_file.name

    # Đóng file handle để FFmpeg có thể truy cập file
    webm_file.close()
    mp4_file.close()

    try:
        # ==========================================
        # 1. Đọc video upload từ Frappe
        # ==========================================

        stream = getattr(video_file, "stream", None)

        if stream:
            content = stream.read()
        else:
            content = video_file.read()

        if not content:
            frappe.throw("Uploaded video is empty.")

        # ==========================================
        # 2. Lưu video WebM tạm
        # ==========================================

        with open(input_path, "wb") as f:
            f.write(content)

        # ==========================================
        # 3. Convert WebM -> MP4 bằng FFmpeg
        # ==========================================

        command = [
            "ffmpeg",
            "-y",
            "-i",
            input_path,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            output_path,
        ]

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # ==========================================
        # 4. Kiểm tra FFmpeg
        # ==========================================

        if result.returncode != 0:

            frappe.log_error(
                title="FFmpeg Video Conversion Failed",
                message=(
                    f"Command:\n"
                    f"{' '.join(command)}\n\n"
                    f"STDOUT:\n"
                    f"{result.stdout}\n\n"
                    f"STDERR:\n"
                    f"{result.stderr}"
                ),
            )

            frappe.throw(
                "Failed to convert webcam video to MP4."
            )

        # Kiểm tra file MP4 có thực sự được tạo không
        if not os.path.exists(output_path):
            frappe.throw(
                "FFmpeg conversion completed but MP4 file was not created."
            )

        # Kiểm tra file MP4 có dữ liệu không
        if os.path.getsize(output_path) == 0:
            frappe.throw(
                "FFmpeg created an empty MP4 file."
            )

        return output_path

    finally:

        # ==========================================
        # 5. Xóa WebM tạm
        # ==========================================

        if os.path.exists(input_path):
            try:
                os.unlink(input_path)
            except Exception:
                pass


@frappe.whitelist()
def register(username, full_name):
    """
    Register a face using webcam video.

    Flow:

    Browser Webcam
        ↓
    WebM
        ↓
    Frappe
        ↓
    FFmpeg
        ↓
    MP4
        ↓
    Face Service Registration
    """

    # ==========================================
    # 1. Validate username
    # ==========================================

    if not username:
        frappe.throw(
            "Username is required."
        )

    # ==========================================
    # 2. Validate full name
    # ==========================================

    if not full_name:
        frappe.throw(
            "Full name is required."
        )

    # ==========================================
    # 3. Get uploaded video
    # ==========================================

    video_file = frappe.request.files.get(
        "video"
    )

    if not video_file:
        frappe.throw(
            "Video file is required."
        )

    # ==========================================
    # 4. Convert WebM -> MP4
    # ==========================================

    video_path = _convert_webm_to_mp4(
        video_file
    )

    try:

        # ==========================================
        # 5. Call Face Service Registration
        # ==========================================

        result = register_without_mask(
            username=username,
            full_name=full_name,
            video_file=video_path,
        )

        # ==========================================
        # 6. Return Face Service response
        # ==========================================

        return result

    finally:

        # ==========================================
        # 7. Xóa MP4 tạm
        # ==========================================

        if os.path.exists(video_path):
            try:
                os.unlink(video_path)
            except Exception:
                pass


@frappe.whitelist()
def verify(username):
    """
    Verify a face using webcam video.

    Flow:

    Browser Webcam
        ↓
    WebM
        ↓
    Frappe
        ↓
    FFmpeg
        ↓
    MP4
        ↓
    Face Service Verification
    """

    # ==========================================
    # 1. Validate username
    # ==========================================

    if not username:
        frappe.throw(
            "Username is required."
        )

    # ==========================================
    # 2. Get uploaded video
    # ==========================================

    video_file = frappe.request.files.get(
        "video"
    )

    if not video_file:
        frappe.throw(
            "Video file is required."
        )

    # ==========================================
    # 3. Convert WebM -> MP4
    # ==========================================

    video_path = _convert_webm_to_mp4(
        video_file
    )

    try:

        # ==========================================
        # 4. Call Face Service Verification
        # ==========================================

        result = verify_face(
            username=username,
            video_file=video_path,
        )

        # ==========================================
        # 5. Return Face Service response
        # ==========================================

        return result

    finally:

        # ==========================================
        # 6. Xóa MP4 tạm
        # ==========================================

        if os.path.exists(video_path):
            try:
                os.unlink(video_path)
            except Exception:
                pass