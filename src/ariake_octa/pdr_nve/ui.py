"""
Standalone Flet page for PDR NVE (does not change the MNV app routes).

Launch:
    PYTHONPATH=.:src python -m ariake_octa.pdr_nve.ui
"""

from __future__ import annotations

import traceback
from pathlib import Path

from ._paths import ensure_import_paths

ensure_import_paths()


def main():
    import flet as ft

    from .pipeline import PdrNveConfig, analyze_pair

    def app(page: ft.Page):
        page.title = "ARIAKE PDR NVE (standalone)"
        page.theme_mode = ft.ThemeMode.DARK
        page.bgcolor = "#050510"
        page.padding = 20

        before_tf = ft.TextField(label="Before image", expand=True)
        after_tf = ft.TextField(label="After image", expand=True)
        out_tf = ft.TextField(label="Output directory", value="pdr_nve_output", expand=True)
        case_tf = ft.TextField(label="Case ID", value="case", width=160)
        scan_tf = ft.TextField(label="Scan size (mm)", value="15", width=140)
        um_tf = ft.TextField(label="µm/px (optional)", value="", width=160)
        roi_tf = ft.TextField(label="ROI mask (optional)", expand=True)
        large_tf = ft.TextField(label="Large vessel µm", value="100", width=140)
        status = ft.Text("", color="#8B9BB4", selectable=True)
        log = ft.Text("", color="#CFD8DC", selectable=True, size=12)

        picker = ft.FilePicker()
        page.overlay.append(picker)

        def pick(field: ft.TextField):
            def _on_result(e):
                if e.files:
                    field.value = e.files[0].path
                    page.update()

            picker.on_result = _on_result
            picker.pick_files(allow_multiple=False)

        def run(_e):
            status.value = "Running…"
            log.value = ""
            page.update()
            try:
                um = float(um_tf.value) if um_tf.value.strip() else None
                cfg = PdrNveConfig(
                    case_id=case_tf.value.strip() or "case",
                    scan_size_mm=float(scan_tf.value or 15),
                    um_per_px=um,
                    roi_mask_path=roi_tf.value.strip() or None,
                    large_vessel_um=float(large_tf.value or 100),
                    output_dir=out_tf.value.strip() or "pdr_nve_output",
                )
                result = analyze_pair(before_tf.value.strip(), after_tf.value.strip(), cfg)
                rec = result.record
                status.value = (
                    f"Done. VD {rec['before_vessel_area_density']:.3f} → "
                    f"{rec['after_vessel_area_density']:.3f}  "
                    f"(pct {rec['pct_vessel_area_density']})  "
                    f"CSV: {result.paths.get('metrics_csv')}"
                )
                log.value = "\n".join(
                    f"{k}: {v}" for k, v in result.paths.items() if str(k).endswith("png") or "csv" in k
                )
            except Exception:
                status.value = "Error"
                log.value = traceback.format_exc()
            page.update()

        page.add(
            ft.Column(
                [
                    ft.Text("PDR NVE / NVD — raw metrics (standalone)", size=22, color="#00E5FF"),
                    ft.Text(
                        "Does not use MNV 3×3/6×6 standardized scores. "
                        "Same CLI as python -m ariake_octa.pdr_nve.",
                        color="#8B9BB4",
                    ),
                    ft.Row(
                        [
                            before_tf,
                            ft.ElevatedButton("Browse", on_click=lambda e: pick(before_tf)),
                        ]
                    ),
                    ft.Row(
                        [
                            after_tf,
                            ft.ElevatedButton("Browse", on_click=lambda e: pick(after_tf)),
                        ]
                    ),
                    ft.Row(
                        [
                            roi_tf,
                            ft.ElevatedButton("Browse", on_click=lambda e: pick(roi_tf)),
                        ]
                    ),
                    ft.Row([out_tf, case_tf, scan_tf, um_tf, large_tf]),
                    ft.ElevatedButton("Run analysis", on_click=run, bgcolor="#00B8D4"),
                    status,
                    log,
                ],
                expand=True,
                spacing=12,
            )
        )

    ft.app(target=app)


if __name__ == "__main__":
    main()
