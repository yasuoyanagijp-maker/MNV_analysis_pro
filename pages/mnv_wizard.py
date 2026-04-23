import flet as ft
from flet import Colors, Icons, FontWeight
import asyncio
import cv2
import numpy as np
import base64
from pathlib import Path
from components.shared import PRIMARY, TEXT_MUTED, AppContext

async def get_mnv_view(ctx: AppContext):
    target_path = ctx.page.session.get("target_path")
    scale = ctx.page.session.get("scale") or 6.0
    roi = ctx.page.session.get("roi")
    
    target_name = "No scan selected"
    if target_path and target_path != "None":
        try:
            target_name = Path(target_path).name
        except:
            target_name = str(target_path)

    status_text = ft.Text("Ready to analyze." if target_path else "Please select an image.", color=TEXT_MUTED)
    progress_bar = ft.ProgressBar(width=400, value=0, visible=False)
    
    async def run_mnv_analysis(e=None):
        if not target_path: return
        if e:
            e.control.disabled = True
        else:
            auto_start_btn.disabled = True
        
        progress_bar.visible = True
        # Safety sleep to ensure RenderBox is laid out before update()
        await asyncio.sleep(0.2)
        print(f"DEBUG: Starting MNV Analysis for {target_path}")
        await ctx.add_to_console(f"Starting MNV Analysis for {Path(target_path).name}...", "INFO")
        ctx.page.update()
        
        # Determine Intelligent ROI setting from Ref or Default
        iroi = True
        try:
            if ctx.intelligent_roi_ref and ctx.intelligent_roi_ref.current:
                iroi = ctx.intelligent_roi_ref.current.value
                print(f"DEBUG: Intelligent ROI setting: {iroi}")
        except Exception as e:
            print(f"DEBUG: Error reading intelligent_roi_ref: {e}")
            iroi = True
            
        roi_mask_b64 = ctx.page.session.get("roi_mask_b64")
        print(f"DEBUG: Mask B64 present: {bool(roi_mask_b64)}")
        
        # Clean path before API call
        clean_path = target_path.strip().strip("'").strip('"')
        print("DEBUG: Sending request to API...")
        try:
            result = await ctx.client.start_mnv_analysis(clean_path, scale, roi=roi, roi_mask_b64=roi_mask_b64, intelligent_roi=iroi)
            print(f"DEBUG: API result received: {list(result.keys()) if isinstance(result, dict) else 'non-dict result'}")
        except Exception as api_err:
            print(f"DEBUG: API CALL CRASHED: {api_err}")
            result = {"error": f"Internal UI/API Connection Crash: {str(api_err)}"}
        
        if "error" in result:
            err_data = result["error"]
            if isinstance(err_data, dict):
                ctx.show_alpha_error(
                    "Analysis Engine Failure",
                    f"The {err_data.get('type', 'Unknown')} failed during processing.",
                    err_data.get("traceback")
                )
            else:
                ctx.show_alpha_error("Process Interrupted", str(err_data))
            
            status_text.value = "Analysis failed. See diagnostic report."
            status_text.color = Colors.RED_400
            if e: e.control.disabled = False
            else: auto_start_btn.disabled = False
        else:
            ctx.page.session.set("last_result", result)
            ctx.page.session.set("is_vd_result", False)
            await ctx.add_to_console(f"MNV Result Received - Type: {result.get('result_type', 'N/A')}", "INFO")
            await asyncio.sleep(0.15)
            ctx.page.go("/results")
        
        progress_bar.visible = False
        if e: e.control.disabled = False
        else: auto_start_btn.disabled = False
        ctx.page.update()

    auto_start_btn = ft.ElevatedButton(
        "Confirm & Start Analysis", 
        icon=Icons.PLAY_CIRCLE_FILL, 
        bgcolor=PRIMARY, 
        color=Colors.BLACK,
        disabled=not target_path,
        on_click=run_mnv_analysis
    )

    # ----------------------------------------------------
    # Visualize ROI Overlay
    # ----------------------------------------------------
    img_control = ft.Container(height=30) # Default spacer if no visual
    
    if target_path and target_path != "None" and ctx.page.session.get("roi_mask_b64"):
        try:
            # Clean path just in case
            clean_path = target_path.strip().strip("'").strip('"')
            print(f"DEBUG: MNV Wizard loading overlay from: {clean_path}", flush=True)
            
            # Load original image
            base_img = cv2.imread(clean_path)
            if base_img is not None:
                # Load mask
                mask_bytes = base64.b64decode(ctx.page.session.get("roi_mask_b64"))
                mask_arr = np.frombuffer(mask_bytes, dtype=np.uint8)
                mask_img = cv2.imdecode(mask_arr, cv2.IMREAD_GRAYSCALE)
                
                if mask_img is not None:
                    # Resize mask to match base image if necessary
                    h, w = base_img.shape[:2]
                    if mask_img.shape != (h, w):
                        mask_img = cv2.resize(mask_img, (w, h), interpolation=cv2.INTER_NEAREST)
                    
                    # Create green overlay
                    overlay = base_img.copy()
                    overlay[mask_img == 255] = [0, 255, 0] # BGR
                    blended = cv2.addWeighted(overlay, 0.4, base_img, 0.6, 0)
                    
                    # Encode to B64 for Flet Image
                    _, buf = cv2.imencode('.jpg', blended, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    blended_b64 = base64.b64encode(buf).decode('utf-8')
                    
                    img_control = ft.Container(
                        content=ft.Image(src="", src_base64=blended_b64, fit=ft.ImageFit.CONTAIN, width=300, height=300),
                        border=ft.border.all(2, PRIMARY),
                        border_radius=10,
                        padding=10,
                        bgcolor=Colors.BLACK,
                    )
        except Exception as e:
            await ctx.add_to_console(f"Visual overlay failed: {e}", "WARNING")

    # ----------------------------------------------------
    # UI Layout Construction
    # ----------------------------------------------------
    return ft.Container(
        content=ft.Column([
            ft.Text("Step 2: Confirm & Analyze", size=32, weight=FontWeight.BOLD, color=Colors.WHITE),
            ft.Text("Please verify your selected ROI below and start the automated analysis pipeline.", color=TEXT_MUTED),
            ft.Container(height=20),
            
            ft.Row([
                ft.Column([ft.Icon(Icons.UPLOAD_FILE, color=PRIMARY), ft.Text("Setup", size=12)], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Container(width=100, height=2, bgcolor=PRIMARY),
                ft.Column([ft.Icon(Icons.CROP_FREE, color=PRIMARY), ft.Text("ROI", size=12)], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Container(width=100, height=2, bgcolor=Colors.with_opacity(0.3, PRIMARY)),
                ft.Column([ft.Icon(Icons.AUTO_AWESOME, color=TEXT_MUTED), ft.Text("Processing", size=12)], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            ], alignment=ft.MainAxisAlignment.CENTER),
            
            ft.Container(height=10),
            
            ft.Container(
                content=ft.Column([
                    img_control,
                    ft.Text(target_name, size=16, color=Colors.WHITE),
                    ft.Text("ROI Selected Successfully" if ctx.page.session.get("roi") else "Wait, no ROI found!", size=12, color=Colors.GREEN_400 if ctx.page.session.get("roi") else Colors.RED_400),
                    ft.Container(height=10),
                    auto_start_btn,
                    status_text,
                    progress_bar,
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=15),
                padding=40,
                bgcolor=Colors.with_opacity(0.05, PRIMARY),
                border=ft.border.all(1, Colors.with_opacity(0.2, PRIMARY)),
                border_radius=20,
                width=800,
            ),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, scroll=ft.ScrollMode.ADAPTIVE),
        padding=40,
        expand=True,
        opacity=1.0,
    )
