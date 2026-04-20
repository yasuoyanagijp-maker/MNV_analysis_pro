import asyncio
from components.shared import AppContext
from pages.roi_selection import get_roi_view

class MockPage:
    session = {"target_path": "/some/path.png"}
    def get(self, k): return self.session.get(k)
    def set(self, k, v): self.session[k] = v
    def run_task(self, fn, *args): pass

ctx = AppContext(MockPage(), None)
async def run():
    try:
        view = await get_roi_view(ctx)
        print("Success, returned:", type(view))
    except Exception as e:
        import traceback
        traceback.print_exc()

asyncio.run(run())
