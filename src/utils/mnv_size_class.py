"""Choose the MNV reference stratum from the scale screen.

3 mm (Optovue) and 3 mm (Zeiss HD) share the geometric scale 3.0 mm.
Only the Optovue button selects ``optovue_3mm``. Every other 3 mm choice
stays on ``small_3mm`` (Zeiss CIRRUS HD) via the existing pipeline rule.
"""

from typing import Optional

OPTOVUE_3MM = "optovue_3mm"


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
