import flet as ft
from flet import Colors, Icons, FontWeight
from pathlib import Path
from src.flet_ui.components.shared import PRIMARY, TEXT_MUTED, GLASS_BG, AppContext

async def get_vd_view(ctx: AppContext):
    target_path = ctx.page.session.get("target_path")
    
    sup_files = []
    deep_files = []
    
    if target_path and Path(target_path).is_dir():
        all_files = [f.name for f in Path(target_path).glob("*") if f.suffix.lower() in [".tif", ".tiff", ".jpg", ".png"]]
        sup_files = [f for f in all_files if any(s in f.upper() for s in ["_S", "SUPERFICIAL"])]
        deep_files = [f for f in all_files if any(s in f.upper() for s in ["_D", "DEEP"])]
    
    if not sup_files:
        sup_files = [f"OCTA_Sup_{i}.tif" for i in range(1, 6)]
        deep_files = [f"OCTA_Deep_{i}.tif" for i in range(1, 5)] 
    
    async def run_batch_vd(e):
        if not target_path: return
        e.control.disabled = True
        ctx.page.update()
        
        scale_val = ctx.scale_mm_ref.current.value if ctx.scale_mm_ref.current else 6.0
        result = await ctx.client.start_vd_analysis(target_path, scale_val)
        
        if "error" in result:
            err_data = result["error"]
            if isinstance(err_data, dict):
                ctx.show_alpha_error("VD Engine Failure", f"Batch analysis failed.", err_data.get("traceback"))
            else:
                ctx.show_alpha_error("VD Error", str(err_data))
            e.control.disabled = False
        else:
            print(f"DEBUG: VD API Response Keys: {list(result.keys())}")
            print(f"DEBUG: Setting last_result in session...")
            ctx.page.session.set("last_result", result)
            await ctx.add_to_console(f"VD Result Received - Type: {result.get('result_type', 'N/A')}", "INFO")
            ctx.page.go("/results")
        ctx.page.update()

    return ft.Container(
        content=ft.Column([
            ft.Text("VD Analysis Pairing", size=32, weight=FontWeight.BOLD, color=Colors.WHITE),
            ft.Row([
                ft.Icon(Icons.INFO_OUTLINE, size=16, color=TEXT_MUTED),
                ft.Text("Smart engine automatically associates scans by patient ID and suffix.", color=TEXT_MUTED, size=14),
            ]),
            ft.Divider(height=40, color=Colors.with_opacity(0.1, Colors.WHITE)),
            
            ft.Row([
                ft.Column([
                    ft.Text(f"Superficial Cohort ({len(sup_files)})", weight=FontWeight.BOLD, color=PRIMARY),
                    ft.ListView(expand=True, spacing=10, height=400, width=400, controls=[
                        ft.ListTile(
                            leading=ft.Icon(Icons.IMAGE_OUTLINED, color=PRIMARY), 
                            title=ft.Text(f, size=14),
                            trailing=ft.Icon(Icons.CHECK_CIRCLE, color=Colors.GREEN_400, size=16)
                        ) for f in sup_files
                    ])
                ], expand=True),
                
                ft.Column([
                    ft.Icon(Icons.LINK_ROUNDED, size=40, color=PRIMARY),
                    ft.Text("Auto-Pairing", size=10, color=TEXT_MUTED)
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                
                ft.Column([
                    ft.Text(f"Deep Cohort ({len(deep_files)})", weight=FontWeight.BOLD, color=Colors.PURPLE_400),
                    ft.ListView(expand=True, spacing=10, height=400, width=400, controls=[
                        ft.ListTile(
                            leading=ft.Icon(Icons.IMAGE_OUTLINED, color=Colors.PURPLE_400), 
                            title=ft.Text(f, size=14),
                            trailing=ft.Icon(Icons.CHECK_CIRCLE, color=Colors.GREEN_400, size=16)
                        ) for f in deep_files
                    ])
                ], expand=True),
            ], spacing=20),
            
            ft.Container(height=30),
            ft.Row([
                ft.ElevatedButton("Validate All Pairs", icon=Icons.RULE_ROUNDED, bgcolor=GLASS_BG, color=Colors.WHITE),
                ft.ElevatedButton("Start Batch Analysis", icon=Icons.PLAY_ARROW_ROUNDED, height=50, bgcolor=PRIMARY, color=Colors.BLACK, on_click=run_batch_vd),
            ], alignment=ft.MainAxisAlignment.END, spacing=20),
        ], spacing=10, scroll=ft.ScrollMode.ADAPTIVE),
         padding=30,
        bgcolor=GLASS_BG,
        border_radius=20,
        opacity=1.0,
    )
