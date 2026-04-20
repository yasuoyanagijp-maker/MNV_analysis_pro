import flet as ft
from flet import Colors, Icons, FontWeight
import asyncio
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
    
    async def run_mnv_analysis(e):
        if not target_path: return
        e.control.disabled = True
        progress_bar.visible = True
        ctx.add_to_console(f"Starting MNV Analysis for {Path(target_path).name}...", "INFO")
        ctx.page.update()
        
        iroi = ctx.intelligent_roi_ref.current.value if ctx.intelligent_roi_ref.current else True
        roi_mask_b64 = ctx.page.session.get("roi_mask_b64")
        result = await ctx.client.start_mnv_analysis(target_path, scale, roi=roi, roi_mask_b64=roi_mask_b64, intelligent_roi=iroi)
        
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
            e.control.disabled = False
        else:
            status_text.value = "Analysis Success! Loading result metrics..."
            ctx.page.session.set("last_result", result)
            await asyncio.sleep(0.15)
            ctx.page.go("/results")
        
        progress_bar.visible = False
        e.control.disabled = False
        ctx.page.update()

    auto_start_btn = ft.ElevatedButton(
        "Start MNV Pipeline", 
        icon=Icons.PLAY_CIRCLE_FILL, 
        bgcolor=PRIMARY, 
        color=Colors.BLACK,
        disabled=not target_path,
        on_click=run_mnv_analysis
    )

    return ft.Container(
        content=ft.Column([
            ft.Text("MNV Analysis Wizard", size=32, weight=FontWeight.BOLD, color=Colors.WHITE),
            ft.Text("Real-time automated segmentation and feature extraction.", color=TEXT_MUTED),
            ft.Container(height=30),
            
            ft.Row([
                ft.Column([ft.Icon(Icons.UPLOAD_FILE, color=PRIMARY), ft.Text("Setup", size=12)], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Container(width=100, height=2, bgcolor=Colors.with_opacity(0.2, Colors.WHITE)),
                ft.Column([ft.Icon(Icons.AUTO_AWESOME, color=PRIMARY), ft.Text("Processing", size=12)], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Container(width=100, height=2, bgcolor=Colors.with_opacity(0.2, Colors.WHITE)),
                ft.Column([ft.Icon(Icons.QUERY_STATS, color=TEXT_MUTED), ft.Text("Summary", size=12)], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            ], alignment=ft.MainAxisAlignment.CENTER),
            
            ft.Container(
                content=ft.Column([
                    ft.Icon(Icons.FILE_PRESENT_ROUNDED, size=80, color=PRIMARY if target_path else TEXT_MUTED),
                    ft.Text(target_name, size=18, color=Colors.WHITE),
                    ft.Text(target_path if target_path else "Launch from dashboard to select file", size=12, color=TEXT_MUTED),
                    ft.Container(height=10),
                    auto_start_btn,
                    status_text,
                    progress_bar,
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=15),
                padding=60,
                bgcolor=Colors.with_opacity(0.05, PRIMARY),
                border=ft.border.all(1, Colors.with_opacity(0.2, PRIMARY)),
                border_radius=25,
                width=800,
            ),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, scroll=ft.ScrollMode.ADAPTIVE),
        padding=40,
        expand=True,
        opacity=1.0,
    )
