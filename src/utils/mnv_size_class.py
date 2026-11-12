"""Choose the MNV reference stratum from the scale screen.

3 mm (Optovue) and 3 mm (Zeiss HD) share the geometric scale 3.0 mm.
Only the Optovue button selects ``optovue_3mm``. Every other 3 mm choice
stays on ``small_3mm`` (Zeiss CIRRUS HD) via the existing pipeline rule.

Windows Flet, Mac Flet, and the API all call these helpers so Network
Complexity Score uses the same criterion on every OS.
"""

from typing import Optional

OPTOVUE_3MM = "optovue_3mm"
SMALL_IMAGE_THRESHOLD = 800


def explicit_mnv_size_class(scale_mm: object, device: object) -> Optional[str]:
    """Return ``optovue_3mm`` when the user picked Optovue at 3 mm.

    ``None`` means the pipeline should keep its scale and image-width rules
    (3 mm → Zeiss HD ``small_3mm``).
    """
    try:
        scale = float(scale_mm)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if abs(scale - 3.0) >= 0.01:
        return None
    token = str(device or "").strip().lower()
    if token in {"optovue", OPTOVUE_3MM}:
        return OPTOVUE_3MM
    return None


def resolve_mnv_complexity_size_class(
    scale_mm: object,
    device: object = None,
    image_width: int = 0,
    small_image_threshold: int = SMALL_IMAGE_THRESHOLD,
) -> str:
    """Pick the Network Complexity Score / morphology reference stratum.

    Same rule on Windows, Intel Mac, and Apple Silicon:

    * 3 mm + Optovue button → ``optovue_3mm``
    * any other 3 mm (Zeiss HD button, numeric 3.0, hand-typed 3 mm) → ``small_3mm``
    * else width > threshold or scale ≥ 6 mm → ``large``
    * else → ``small``
    """
    override = explicit_mnv_size_class(scale_mm, device)
    try:
        scale = float(scale_mm)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        scale = None
    scale_is_3mm = scale is not None and abs(scale - 3.0) < 0.01
    if scale_is_3mm and override == OPTOVUE_3MM:
        return OPTOVUE_3MM
    if scale_is_3mm:
        return "small_3mm"
    try:
        width = int(image_width or 0)
    except (TypeError, ValueError):
        width = 0
    if width > small_image_threshold or (scale is not None and scale >= 6.0):
        return "large"
    return "small"
