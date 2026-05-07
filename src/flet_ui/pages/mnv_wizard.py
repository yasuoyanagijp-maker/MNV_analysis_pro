import flet as ft
from flet import Colors, Icons, FontWeight
import asyncio
import cv2
import numpy as np
import base64
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_SRC = _PROJECT_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from src.utils.vd_batch_csv import VD_LAYOUT_VSL_DENSITY_ONLY

from src.flet_ui.components.shared import PRIMARY, TEXT_MUTED, AppContext, session_discard
from src.utils.cv2_path import imread_bgr


def _ref_control_value(ref, fallback):
    """Read .value from a Flet control stored on ref.current, if valid."""
    c = getattr(ref, "current", None) if ref is not None else None
    if c is None:
        return fallback
    v = getattr(c, "value", None)
    if v is None or v == "":
        return fallback
    return v


async def get_mnv_view(ctx: AppContext):
    vd_explicit = ctx.page.session.get("vd_analysis_explicit_path")
    vd_explicit_str = (
        vd_explicit.strip().strip("'").strip('"') if isinstance(vd_explicit, str) else ""
    )
    is_vd = bool(vd_explicit_str)

    target_path = ctx.page.session.get("target_path")
    scale_sess = ctx.page.session.get("scale") or 6.0
    roi_bbox = ctx.page.session.get("roi")

    try:
        scale = float(_ref_control_value(ctx.scale_mm_ref, scale_sess))
    except (TypeError, ValueError):
        scale = float(scale_sess)

    scan_path = vd_explicit_str if is_vd else target_path

    target_name = "No scan selected"
    if scan_path and str(scan_path) != "None":
        try:
            target_name = Path(scan_path).name
        except Exception:
            target_name = str(scan_path)

    status_text = ft.Text(
        "Ready to analyze." if scan_path else "Please select an image.",
        color=TEXT_MUTED,
    )
    progress_bar = ft.ProgressBar(width=400, value=0, visible=False)

    async def run_analysis(e=None):
        if not scan_path:
            return
        if e:
            e.control.disabled = True
        else:
            auto_start_btn.disabled = True

        progress_bar.visible = True
        await asyncio.sleep(0.2)
        ctx.page.update()

        roi_mask_b64 = ctx.page.session.get("roi_mask_b64")

        if is_vd:
            await ctx.add_to_console(f"Starting VD (single-image) for {target_name}...", "INFO")
            clean_explicit = vd_explicit_str
            vd_dir = str(Path(clean_explicit).resolve().parent)
            sup_s = str(_ref_control_value(ctx.vd_sup_suffix_ref, "1.tif")).strip() or "1.tif"
            deep_s = str(_ref_control_value(ctx.vd_deep_suffix_ref, "2.tif")).strip() or "2.tif"
            side_s = str(_ref_control_value(ctx.vd_side_ref, "right")).strip() or "right"
            try:
                result = await ctx.client.start_vd_analysis(
                    vd_dir,
                    scale,
                    side=side_s,
                    sup_suffix=sup_s,
                    deep_suffix=deep_s,
                    single_image_mode=True,
                    single_image_explicit_path=clean_explicit,
                )
            except Exception as api_err:
                result = {"error": f"Internal UI/API Connection Crash: {str(api_err)}"}
        else:
            await ctx.add_to_console(
                f"Starting MNV Analysis for {Path(target_path).name}...", "INFO"
            )
            clean_path = str(target_path).strip().strip("'").strip('"')
            try:
                result = await ctx.client.start_mnv_analysis(
                    clean_path,
                    scale,
                    roi=roi_bbox,
                    roi_mask_b64=roi_mask_b64,
                    intelligent_roi=False,
                )
            except Exception as api_err:
                result = {"error": f"Internal UI/API Connection Crash: {str(api_err)}"}

        if "error" in result:
            err_data = result["error"]
            if isinstance(err_data, dict):
                ctx.show_alpha_error(
                    "Analysis Engine Failure",
                    f"The {err_data.get('type', 'Unknown')} failed during processing.",
                    err_data.get("traceback"),
                )
            else:
                ctx.show_alpha_error("Process Interrupted", str(err_data))

            status_text.value = "Analysis failed. See diagnostic report."
            status_text.color = Colors.RED_400
            if e:
                e.control.disabled = False
            else:
                auto_start_btn.disabled = False
        else:
            if is_vd and isinstance(result, dict):
                result = dict(result)
                result["vd_layout"] = VD_LAYOUT_VSL_DENSITY_ONLY
            ctx.page.session.set("last_result", result)
            ctx.page.session.set("is_vd_result", bool(is_vd))
            batch_paths = ctx.page.session.get("mnv_batch_paths")
            if (
                not is_vd
                and batch_paths
                and isinstance(batch_paths, list)
                and len(batch_paths) > 0
            ):
                ctx.page.session.set("mnv_batch_awaiting_qc", True)
                session_discard(ctx.page.session, "batch_results")
                ctx.page.session.set("results_selected_index", 0)
            if is_vd:
                session_discard(ctx.page.session, "vd_analysis_explicit_path")
            await ctx.add_to_console(
                f"Result received — type: {result.get('result_type', 'N/A')}",
                "INFO",
            )
            await asyncio.sleep(0.15)
            ctx.page.go("/results")

        progress_bar.visible = False
        if e:
            e.control.disabled = False
        else:
            auto_start_btn.disabled = False
        ctx.page.update()

    btn_ok = bool(scan_path) and (
        is_vd or ((target_path and target_path != "None"))
    )

    auto_start_btn = ft.ElevatedButton(
        "Confirm & Start Analysis",
        icon=Icons.PLAY_CIRCLE_FILL,
        bgcolor=PRIMARY,
        color=Colors.BLACK,
        disabled=not btn_ok,
        on_click=run_analysis,
    )

    # ----------------------------------------------------
    # Visualize ROI Overlay (MNV only)
    # ----------------------------------------------------
    img_control = ft.Container(height=30)

    if (
        not is_vd
        and target_path
        and target_path != "None"
        and ctx.page.session.get("roi_mask_b64")
    ):
        try:
            clean_path = str(target_path).strip().strip("'").strip('"')
            base_img = imread_bgr(clean_path)
            if base_img is not None:
                mask_bytes = base64.b64decode(ctx.page.session.get("roi_mask_b64"))
                mask_arr = np.frombuffer(mask_bytes, dtype=np.uint8)
                mask_img = cv2.imdecode(mask_arr, cv2.IMREAD_GRAYSCALE)

                if mask_img is not None:
                    h, w = base_img.shape[:2]
                    if mask_img.shape != (h, w):
                        mask_img = cv2.resize(mask_img, (w, h), interpolation=cv2.INTER_NEAREST)

                    overlay = base_img.copy()
                    overlay[mask_img == 255] = [0, 255, 0]
                    blended = cv2.addWeighted(overlay, 0.4, base_img, 0.6, 1.0)

                    _, buf = cv2.imencode(".jpg", blended, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    blended_b64 = base64.b64encode(buf).decode("utf-8")

                    img_control = ft.Container(
                        content=ft.Image(
                            src="",
                            src_base64=blended_b64,
                            fit=ft.ImageFit.CONTAIN,
                            width=300,
                            height=300,
                        ),
                        border=ft.border.all(2, PRIMARY),
                        border_radius=10,
                        padding=10,
                        bgcolor=Colors.BLACK,
                    )
        except Exception as e:
            await ctx.add_to_console(f"Visual overlay failed: {e}", "WARNING")

    if is_vd and scan_path:
        try:
            bgr = imread_bgr(scan_path)
            if bgr is not None:
                _, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
                preview_b64 = base64.b64encode(buf).decode("utf-8")
                img_control = ft.Container(
                    content=ft.Image(
                        src="",
                        src_base64=preview_b64,
                        fit=ft.ImageFit.CONTAIN,
                        width=300,
                        height=300,
                    ),
                    border=ft.border.all(2, Colors.AMBER_400),
                    border_radius=10,
                    padding=10,
                    bgcolor=Colors.BLACK,
                )
        except Exception:
            pass

    batch_paths = ctx.page.session.get("mnv_batch_paths") or []
    batch_idx = int(ctx.page.session.get("mnv_batch_index") or 0)
    batch_hint = ""
    if batch_paths and not is_vd:
        batch_hint = (
            f"MNV folder batch — image {batch_idx + 1} of {len(batch_paths)}. "
        )

    step_title = "VD: Confirm & run pipeline" if is_vd else "MNV: Confirm & Analyze"
    help_line = (
        "Runs VD single-image processing (superficial or deep OCT-A) using suffix settings from the dashboard."
        if is_vd
        else (
            batch_hint
            + "Verify your ROI (green overlay) below, then start the MNV analysis pipeline."
        )
    )

    roi_status_txt = ""
    roi_status_clr = Colors.GREEN_400
    if is_vd:
        roi_status_txt = "VD mode — ROI step skipped"
        roi_status_clr = PRIMARY
    else:
        roi_status_txt = (
            "ROI selected"
            if ctx.page.session.get("roi") or roi_mask_b64
            else "No ROI mask found"
        )
        roi_status_clr = (
            Colors.GREEN_400
            if ctx.page.session.get("roi") or roi_mask_b64
            else Colors.RED_400
        )

    progression = (
        ft.Row(
            [
                ft.Column(
                    [
                        ft.Icon(Icons.UPLOAD_FILE, color=PRIMARY),
                        ft.Text("Setup", size=12),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(width=100, height=2, bgcolor=PRIMARY),
                ft.Column(
                    [
                        ft.Icon(Icons.HUB_ROUNDED, color=PRIMARY),
                        ft.Text("VD pipeline", size=12),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(width=100, height=2, bgcolor=Colors.with_opacity(0.3, PRIMARY)),
                ft.Column(
                    [
                        ft.Icon(Icons.AUTO_AWESOME, color=TEXT_MUTED),
                        ft.Text("Results", size=12),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
        )
        if is_vd
        else ft.Row(
            [
                ft.Column(
                    [
                        ft.Icon(Icons.UPLOAD_FILE, color=PRIMARY),
                        ft.Text("Setup", size=12),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(width=100, height=2, bgcolor=PRIMARY),
                ft.Column(
                    [
                        ft.Icon(Icons.CROP_FREE, color=PRIMARY),
                        ft.Text("ROI", size=12),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(width=100, height=2, bgcolor=Colors.with_opacity(0.3, PRIMARY)),
                ft.Column(
                    [
                        ft.Icon(Icons.AUTO_AWESOME, color=TEXT_MUTED),
                        ft.Text("Processing", size=12),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
        )
    )

    return ft.Container(
        content=ft.Column(
            [
                ft.Text(step_title, size=32, weight=FontWeight.BOLD, color=Colors.WHITE),
                ft.Text(help_line, color=TEXT_MUTED),
                ft.Container(height=20),
                progression,
                ft.Container(height=10),
                ft.Container(
                    content=ft.Column(
                        [
                            img_control,
                            ft.Text(target_name, size=16, color=Colors.WHITE),
                            ft.Text(roi_status_txt, size=12, color=roi_status_clr),
                            ft.Container(height=10),
                            auto_start_btn,
                            status_text,
                            progress_bar,
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=15,
                    ),
                    padding=40,
                    bgcolor=(
                        Colors.with_opacity(0.05, Colors.AMBER_400)
                        if is_vd
                        else Colors.with_opacity(0.05, PRIMARY)
                    ),
                    border=ft.border.all(
                        1,
                        (
                            Colors.with_opacity(0.2, Colors.AMBER_400)
                            if is_vd
                            else Colors.with_opacity(0.2, PRIMARY)
                        ),
                    ),
                    border_radius=20,
                    width=800,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            scroll=ft.ScrollMode.ADAPTIVE,
        ),
        padding=40,
        expand=True,
        opacity=1.0,
    )
