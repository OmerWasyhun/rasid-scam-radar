"""Build the pitch deck (PDF + PPTX) and the project description (PDF) from the HTML sources in this folder.

    .venv\\Scripts\\python presentation\\build\\build.py

The walkthrough (presentation/index.html) sets the design; deck.html and description.html follow it through rasid.css.
The PPTX holds one picture per slide so the Arabic type looks the same on every computer; the slide text is in the notes.
"""
import asyncio
import io
import sys
from pathlib import Path

from playwright.async_api import async_playwright
from pptx import Presentation
from pptx.util import Emu

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUT_DECK_PDF = ROOT / "RASID-ScamShield-pitch.pdf"
OUT_DECK_PPTX = ROOT / "RASID-ScamShield-pitch.pptx"
OUT_DESC_PDF = ROOT / "RASID-project-description.pdf"
PREVIEW = HERE / "preview"


async def ready(page):
    await page.evaluate("document.fonts.ready")
    await page.wait_for_function("[...document.images].every(i => i.complete && i.naturalWidth > 0)")
    await page.wait_for_timeout(300)


async def main():
    PREVIEW.mkdir(exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()

        # ---- deck ----
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        await page.goto((HERE / "deck.html").as_uri(), wait_until="networkidle")
        await ready(page)
        await page.pdf(path=str(OUT_DECK_PDF), width="1920px", height="1080px", print_background=True)
        slides = await page.query_selector_all("section.slide")
        shots, notes = [], []
        for i, s in enumerate(slides, 1):
            png = PREVIEW / f"slide-{i:02d}.png"
            await s.screenshot(path=str(png))
            shots.append(png)
            notes.append((await s.inner_text()).strip())
            over = await s.evaluate("e => e.scrollHeight > e.clientHeight + 1 || [...e.querySelectorAll('.body')].some(b => b.scrollHeight > b.clientHeight + 1)")
            if over:
                print(f"  slide {i}: content overflows")
        await page.close()

        prs = Presentation()
        prs.slide_width, prs.slide_height = Emu(12192000), Emu(6858000)
        blank = prs.slide_layouts[6]
        for png, note in zip(shots, notes):
            slide = prs.slides.add_slide(blank)
            slide.shapes.add_picture(str(png), 0, 0, width=prs.slide_width, height=prs.slide_height)
            slide.notes_slide.notes_text_frame.text = note
        prs.core_properties.title = "RASID راصد: حارس المكالمات ورادار الاحتيال"
        prs.core_properties.author = "Omer Wasiyehun, Ibrahim Abulaban, Ahmed Ismail Bulbul"
        prs.save(str(OUT_DECK_PPTX))
        print(f"deck: {len(shots)} slides")

        # ---- project description ----
        src = HERE / "description.html"
        if src.exists():
            page = await browser.new_page(viewport={"width": 794, "height": 1123})
            await page.goto(src.as_uri(), wait_until="networkidle")
            await ready(page)
            await page.pdf(path=str(OUT_DESC_PDF), format="A4", print_background=True, margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
            pages = await page.query_selector_all("section.page")
            for i, s in enumerate(pages, 1):
                await s.screenshot(path=str(PREVIEW / f"page-{i:02d}.png"))
                if await s.evaluate("e => e.scrollHeight > e.clientHeight + 1"):
                    print(f"  page {i}: content overflows")
            print(f"description: {len(pages)} pages")
        await browser.close()


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    asyncio.run(main())
