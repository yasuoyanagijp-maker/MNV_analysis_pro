import flet as ft
from flet import Colors, Icons, FontWeight
from src.flet_ui.components.shared import PRIMARY, PRIMARY_GLOW, TEXT_MUTED, GLASS_BG, AppContext
from src.utils.institution_config import (
    INSTITUTION_PRESETS,
    load_persisted_institution_id,
    persist_institution_id,
    resolve_institution_id,
)


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

    persisted = load_persisted_institution_id(
        ctx.page.session, getattr(ctx.page, "client_storage", None)
    )
    preset_codes = {code for code, _ in INSTITUTION_PRESETS if code != "CUSTOM"}
    initial_preset = persisted if persisted in preset_codes else ("CUSTOM" if persisted else "ARIAKE_OHANACHAYA")

    institution_dd = ft.Dropdown(
        label="Institution code",
        width=350,
        border_color=PRIMARY,
        focused_border_color=PRIMARY_GLOW,
        value=initial_preset,
        options=[
            ft.dropdown.Option(code, f"{code} — {label}")
            for code, label in INSTITUTION_PRESETS
        ],
        tooltip="Site code for export/{institution_id}/… (stable for multi-site ML). "
        "Locked installs can set ARIAKE_INSTITUTION_ID.",
    )
    institution_custom = ft.TextField(
        label="Custom institution code (UPPER_SNAKE)",
        width=350,
        border_color=PRIMARY,
        focused_border_color=PRIMARY_GLOW,
        value=persisted if initial_preset == "CUSTOM" else "",
        visible=(initial_preset == "CUSTOM"),
        text_size=12,
        hint_text="e.g. MY_HOSPITAL_CODE",
    )

    def _on_institution_change(_=None):
        institution_custom.visible = institution_dd.value == "CUSTOM"
        ctx.page.update()

    institution_dd.on_change = _on_institution_change

    error_text = ft.Text(color=Colors.RED_400, size=12, visible=False)

    async def login_click(e):
        if not username_field.value or not password_field.value:
            error_text.value = "Please fill in all fields."
            error_text.visible = True
            ctx.page.update()
            return

        if institution_dd.value == "CUSTOM" and not (institution_custom.value or "").strip():
            error_text.value = "Enter a custom institution code, or pick a preset."
            error_text.visible = True
            ctx.page.update()
            return

        e.control.disabled = True
        ctx.page.update()

        login_res = await ctx.client.login(username_field.value, password_field.value)

        if login_res.get("success"):
            raw_inst = (
                (institution_custom.value or "").strip()
                if institution_dd.value == "CUSTOM"
                else (institution_dd.value or "")
            )
            code = persist_institution_id(
                raw_inst,
                ctx.page.session,
                getattr(ctx.page, "client_storage", None),
            )
            # Env still wins for exports if set; session keeps UI choice for display
            _ = resolve_institution_id(ctx.page.session, getattr(ctx.page, "client_storage", None))
            ctx.page.session.set("username", username_field.value)
            ctx.page.session.set("institution_id", code)
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
                    institution_dd,
                    institution_custom,
                    ft.Text(
                        "Institution code tags export folders for multi-site datasets "
                        "(rater_id = Researcher Name).",
                        size=10,
                        color=TEXT_MUTED,
                        width=350,
                    ),
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
