from pathlib import Path
from typing import Dict


def get_vd_metrics_for_file(metrics: Dict, filename: str) -> Dict:
    """Extract per-file VD metrics from VDAnalyzer results.

    Returns a dict with keys: patient_id, faz_area, faz_circularity,
    superficial_whole, deep_whole, superficial_sectors, deep_sectors, index
    """
    if not metrics or not isinstance(metrics, dict) or not metrics.get('patient_ids'):
        return {}

    # determine index
    idx = 0
    try:
        if filename in metrics.get('superficial_files', []):
            idx = metrics.get('superficial_files').index(filename)
        elif filename in metrics.get('deep_files', []):
            idx = metrics.get('deep_files').index(filename)
        else:
            idx = 0
    except Exception:
        idx = 0

    def _get(key, i, default=0.0):
        vals = metrics.get(key, [])
        return vals[i] if i < len(vals) else default

    patient_id = _get('patient_ids', idx, Path(filename).stem)
    faz_area = _get('faz_areas', idx, 0.0)
    faz_circ = _get('faz_circularities', idx, 0.0)
    sup_whole = _get('superficial_whole', idx, 0.0)
    deep_whole = _get('deep_whole', idx, 0.0)

    sup_sectors = {
        'superior': _get('superficial_superior', idx, 0.0),
        'temporal': _get('superficial_temporal', idx, 0.0),
        'nasal': _get('superficial_nasal', idx, 0.0),
        'inferior': _get('superficial_inferior', idx, 0.0)
    }
    deep_sectors = {
        'superior': _get('deep_superior', idx, 0.0),
        'temporal': _get('deep_temporal', idx, 0.0),
        'nasal': _get('deep_nasal', idx, 0.0),
        'inferior': _get('deep_inferior', idx, 0.0)
    }

    return {
        'patient_id': patient_id,
        'faz_area': faz_area,
        'faz_circularity': faz_circ,
        'superficial_whole': sup_whole,
        'deep_whole': deep_whole,
        'superficial_sectors': sup_sectors,
        'deep_sectors': deep_sectors,
        'index': idx
    }


def get_vd_summary_value(metrics: Dict, filename: str):
    """Return the numeric VD value to show in summary (superficial whole % by default)."""
    data = get_vd_metrics_for_file(metrics, filename)
    return data.get('superficial_whole') if data else None
