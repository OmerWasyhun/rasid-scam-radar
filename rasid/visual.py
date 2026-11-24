"""Compare two screenshots without any outside service: perceptual hashes, colour histograms and a block-by-block
layout match. Returns 0..1 similarity plus the parts, so the case file can show why two pages look alike."""
from pathlib import Path

from PIL import Image, ImageOps

W, H = 64, 48  # comparison grid (keeps the page's aspect ratio roughly 4:3)


def _load(p: Path) -> Image.Image:
    im = Image.open(p).convert("RGB")
    # compare the top of the page (header, logo, hero, login box), where phishing kits copy the brand
    w, h = im.size
    return im.crop((0, 0, w, min(h, int(w * 0.66))))


def _dhash(im: Image.Image, size: int = 16) -> int:
    g = ImageOps.grayscale(im).resize((size + 1, size), Image.LANCZOS)
    px = list(g.getdata())
    bits = 0
    for r in range(size):
        for c in range(size):
            bits = (bits << 1) | (px[r * (size + 1) + c] > px[r * (size + 1) + c + 1])
    return bits


def _ahash(im: Image.Image, size: int = 16) -> int:
    g = ImageOps.grayscale(im).resize((size, size), Image.LANCZOS)
    px = list(g.getdata())
    avg = sum(px) / len(px)
    bits = 0
    for v in px:
        bits = (bits << 1) | (v > avg)
    return bits


def _hamming_sim(a: int, b: int, nbits: int) -> float:
    return 1 - bin(a ^ b).count("1") / nbits


def _hist_sim(a: Image.Image, b: Image.Image) -> float:
    ha = a.resize((128, 96)).quantize(colors=64, method=Image.Quantize.FASTOCTREE).convert("RGB").histogram()
    hb = b.resize((128, 96)).quantize(colors=64, method=Image.Quantize.FASTOCTREE).convert("RGB").histogram()
    inter = sum(min(x, y) for x, y in zip(ha, hb))
    return inter / max(1, sum(ha))


def _blocks_sim(a: Image.Image, b: Image.Image) -> float:
    ga = list(ImageOps.grayscale(a).resize((W, H), Image.BILINEAR).getdata())
    gb = list(ImageOps.grayscale(b).resize((W, H), Image.BILINEAR).getdata())
    diff = sum(abs(x - y) for x, y in zip(ga, gb)) / (255 * len(ga))
    return 1 - diff


def blank(p: Path) -> bool:
    """True for an empty or almost single-colour screenshot (blank page, error page)."""
    im = ImageOps.grayscale(Image.open(p)).resize((64, 48))
    lo, hi = im.getextrema()
    return hi - lo < 12


def compare(sus: Path, off: Path) -> dict:
    a, b = _load(sus), _load(off)
    parts = {
        "structure": round(_hamming_sim(_dhash(a), _dhash(b), 256), 2),
        "shape": round(_hamming_sim(_ahash(a), _ahash(b), 256), 2),
        "colours": round(_hist_sim(a, b), 2),
        "pixels": round(_blocks_sim(a, b), 2),
    }
    # hashes of unrelated pages still agree ~50% by chance, so rescale them to 0..1 above that baseline
    s_struct = max(0.0, (parts["structure"] - 0.55) / 0.45)
    s_shape = max(0.0, (parts["shape"] - 0.55) / 0.45)
    s_pix = max(0.0, (parts["pixels"] - 0.7) / 0.3)
    score = 0.35 * s_struct + 0.2 * s_shape + 0.25 * parts["colours"] * (1 if s_struct > 0.2 else 0.5) + 0.2 * s_pix
    return {"score": round(min(1.0, score), 2), "parts": parts}
