import flet as ft
from flet import Colors, Icons, FontWeight
from src.flet_ui.components.shared import PRIMARY, PRIMARY_GLOW, TEXT_MUTED, GLASS_BG, AppContext

async def get_login_view(ctx: AppContext):
    username_field = ft.TextField(
        label="Researcher Name",
        prefix_icon=Icons.PERSON_ROUNDED,
        border_color=PRIMARY,
        focused_border_color=PRIMARY_GLOW,
        width=350,
    )
    password_field = ft.TextField(
        label="Password",
        prefix_icon=Icons.LOCK_ROUNDED,
        password=True,
        can_reveal_password=True,
        border_color=PRIMARY,
        focused_border_color=PRIMARY_GLOW,
        width=350,
    )
    
    error_text = ft.Text(color=Colors.RED_400, size=12, visible=False)

    async def login_click(e):
        if not username_field.value or not password_field.value:
            error_text.value = "Please fill in all fields."
            error_text.visible = True
            ctx.page.update()
            return
        
        e.control.disabled = True
        ctx.page.update()
        
        login_res = await ctx.client.login(username_field.value, password_field.value)
        
        if login_res.get("success"):
            ctx.page.session.set("username", username_field.value)
            ctx.page.go("/")
        else:
            error_text.value = login_res.get("message", "Login failed.")
            error_text.visible = True
            e.control.disabled = False
            ctx.page.update()

    return ft.Container(
        content=ft.Column([
            ft.Container(
                content=ft.Column([
                    ft.Icon(Icons.SECURITY_ROUNDED, size=80, color=PRIMARY),
                    ft.Text("Researcher Access", size=28, weight=FontWeight.BOLD, color=Colors.WHITE),
                    ft.Text("ARIAKE OCTA ALPHA ACCESS", size=12, color=TEXT_MUTED),
                    ft.Container(height=20),
                    username_field,
                    password_field,
                    error_text,
                    ft.Container(height=10),
                    ft.ElevatedButton(
                        "Secure Login", 
                        height=50, 
                        width=350, 
                        bgcolor=PRIMARY, 
                        color=Colors.BLACK,
                        on_click=login_click
                    ),
                    ft.Text("Forgot Password? ariake2024", size=10, color=TEXT_MUTED),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=15),
                padding=60,
                bgcolor=GLASS_BG,
                border_radius=25,
                border=ft.border.all(1, Colors.with_opacity(0.1, Colors.WHITE)),
                shadow=ft.BoxShadow(blur_radius=50, color=Colors.with_opacity(0.1, PRIMARY)),
            )
        ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        expand=True,
    )
