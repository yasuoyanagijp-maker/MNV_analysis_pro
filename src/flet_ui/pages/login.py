import flet as ft
from flet import Colors, Icons, FontWeight
from src.flet_ui.components.shared import (
    PRIMARY,
    PRIMARY_GLOW,
    TEXT_MUTED,
    GLASS_BG,
    AppContext,
    APP_LOGIN_TITLE,
    APP_LOGIN_SUBTITLE,
)
from src.utils.institution_config import (
    INSTITUTION_PRESETS,
    client_storage_set_async,
    load_persisted_institution_id,
    load_persisted_institution_id_async,
    persist_institution_id,
    persist_institution_id_client_async,
)
from src.utils.second_reader import (
    READER_ROLE_KEY,
    READER_ROLE_OPTIONS,
    ROLE_FINAL_READER,
    ROLE_FIRST_GRADER,
    ROLE_SECOND_READER,
)
from src.utils.grdm_access import (
    GRDM_GRADED_INSTITUTION_KEY,
    GRDM_PENDING_INSTITUTION_KEY,
    clear_grdm_session_institutions,
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

    # Session / env only while building the form. Sync client_storage reads are
    # blocking RPCs (up to 5s) and delayed first paint; hydrate via get_async after.
    persisted = load_persisted_institution_id(ctx.page.session, None)
    preset_codes = {code for code, _ in INSTITUTION_PRESETS if code != "CUSTOM"}
    initial_preset = persisted if persisted in preset_codes else ("CUSTOM" if persisted else "ARIAKE_OHANACHAYA")
    _institution_locked = bool(persisted)

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
        tooltip="Site code for export/images|masks|meta/{institution_id}/… (MedSAM multi-site). "
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

    _role_persisted = str(ctx.page.session.get(READER_ROLE_KEY) or ROLE_FIRST_GRADER)
    role_dd = ft.Dropdown(
        label="Role / 読影担当",
        width=350,
        border_color=PRIMARY,
        focused_border_color=PRIMARY_GLOW,
        value=_role_persisted
        if _role_persisted in (ROLE_FIRST_GRADER, ROLE_SECOND_READER, ROLE_FINAL_READER)
        else ROLE_FIRST_GRADER,
        options=[
            ft.dropdown.Option(code, label) for code, label in READER_ROLE_OPTIONS
        ],
        tooltip=(
            "第2リーダー: 施設エキスポート（export/meta）の親フォルダ、"
            "または GakuNin RDM から第1読影データを取得して二重読影。"
            " RPD≤20% で平均採用。中央読影は施設コード Team YY。"
            " 最終読影者: RECHECK対象MD（*_summary.md）を選択して再読影し、"
            "G1/G2/最終読影者の3値中央値で確定します。"
        ),
    )

    def _on_institution_change(_=None):
        nonlocal _institution_locked
        _institution_locked = True
        institution_custom.visible = institution_dd.value == "CUSTOM"
        ctx.page.update()

    institution_dd.on_change = _on_institution_change

    error_text = ft.Text(color=Colors.RED_400, size=12, visible=False)
    login_btn = ft.ElevatedButton(
        "Secure Login",
        height=50,
        width=350,
        bgcolor=PRIMARY,
        color=Colors.BLACK,
    )

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

        login_btn.disabled = True
        login_btn.text = "Signing in…"
        ctx.page.update()

        login_res = await ctx.client.login(username_field.value, password_field.value)

        if login_res.get("success"):
            # Session only on the click path. Sync client_storage get/set/remove
            # are blocking RPCs (up to 5s each) and delayed Launch Analysis.
            clear_grdm_session_institutions(ctx.page.session, None)
            raw_inst = (
                (institution_custom.value or "").strip()
                if institution_dd.value == "CUSTOM"
                else (institution_dd.value or "")
            )
            code = persist_institution_id(raw_inst, ctx.page.session, None)
            role = role_dd.value or ROLE_FIRST_GRADER
            ctx.page.session.set("username", username_field.value)
            ctx.page.session.set("institution_id", code)
            ctx.page.session.set(READER_ROLE_KEY, role)
            ctx.page.go("/")

            async def _persist_client_storage():
                # Let dashboard first paint win the websocket before any CS RPC.
                cs = getattr(ctx.page, "client_storage", None)
                await persist_institution_id_client_async(
                    code,
                    cs,
                    extra_remove_keys=(
                        GRDM_GRADED_INSTITUTION_KEY,
                        GRDM_PENDING_INSTITUTION_KEY,
                    ),
                )
                await client_storage_set_async(cs, READER_ROLE_KEY, role)

            ctx.page.run_task(_persist_client_storage)
        else:
            error_text.value = login_res.get("message", "Login failed.")
            error_text.visible = True
            login_btn.disabled = False
            login_btn.text = "Secure Login"
            ctx.page.update()

    login_btn.on_click = login_click

    async def _hydrate_institution_dropdown():
        if _institution_locked:
            return
        stored = await load_persisted_institution_id_async(
            getattr(ctx.page, "client_storage", None),
        )
        if _institution_locked or not stored:
            return
        if stored in preset_codes:
            institution_dd.value = stored
            institution_custom.value = ""
            institution_custom.visible = False
        else:
            institution_dd.value = "CUSTOM"
            institution_custom.value = stored
            institution_custom.visible = True
        try:
            ctx.page.update()
        except Exception:
            pass

    ctx.page.run_task(_hydrate_institution_dropdown)

    return ft.Container(
        content=ft.Column([
            ft.Container(
                content=ft.Column([
                    ft.Icon(Icons.SECURITY_ROUNDED, size=80, color=PRIMARY),
                    ft.Text(APP_LOGIN_TITLE, size=28, weight=FontWeight.BOLD, color=Colors.WHITE),
                    ft.Text(APP_LOGIN_SUBTITLE, size=12, color=TEXT_MUTED),
                    ft.Container(height=20),
                    username_field,
                    password_field,
                    institution_dd,
                    institution_custom,
                    role_dd,
                    ft.Text(
                        "Institution code tags export folders for multi-site datasets "
                        "(rater_id = Researcher Name).",
                        size=10,
                        color=TEXT_MUTED,
                        width=350,
                    ),
                    error_text,
                    ft.Container(height=10),
                    login_btn,
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
