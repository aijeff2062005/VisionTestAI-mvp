"""Shared clinic Desk constants (no imports from other clinic modules)."""

# Keep workspace names as stable English slugs. Titles are translated separately.
WS_NURSE = "Nurse"
WS_DOCTOR = "Doctor"
WS_ADMIN = "Clinic Admin"

CLINIC_WORKSPACES: tuple[str, ...] = (WS_ADMIN, WS_NURSE, WS_DOCTOR)
