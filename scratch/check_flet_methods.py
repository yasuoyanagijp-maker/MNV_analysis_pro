import flet as ft
import asyncio

async def test_main(page: ft.Page):
    import inspect
    
    def check_method(obj, name):
        if hasattr(obj, name):
            method = getattr(obj, name)
            is_async = inspect.iscoroutinefunction(method)
            print(f"{name} exists and is {'async' if is_async else 'sync'}")
        else:
            print(f"{name} DOES NOT exist")

    print("\n--- Page Methods ---")
    check_method(page, "update")
    check_method(page, "update_async")
    check_method(page, "set_clipboard")
    check_method(page, "set_clipboard_async")
    check_method(page, "close")
    check_method(page, "close_async")
    check_method(page, "open")

    print("\n--- FilePicker Methods ---")
    fp = ft.FilePicker()
    page.overlay.append(fp)
    page.update()
    check_method(fp, "pick_files")
    check_method(fp, "pick_files_async")
    check_method(fp, "get_directory_path")
    check_method(fp, "get_directory_path_async")
    check_method(fp, "upload")
    check_method(fp, "upload_async")

    # Exit
    # page.window.close() # In some versions it might be page.window_close or page.window.close
    # Let's just use asyncio.sleep and then the script will finish if we use a timeout or just kill it.
    print("\nDiagnostics complete.")

if __name__ == "__main__":
    ft.app(target=test_main)
