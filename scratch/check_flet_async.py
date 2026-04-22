import flet as ft
import inspect

def main(page: ft.Page):
    fp = ft.FilePicker()
    print(f"get_directory_path is async: {inspect.iscoroutinefunction(fp.get_directory_path)}")
    print(f"pick_files is async: {inspect.iscoroutinefunction(fp.pick_files)}")
    page.window_close()

ft.app(target=main)
