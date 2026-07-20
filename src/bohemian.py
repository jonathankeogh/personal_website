"""Interactive explorer for Bohemian matrix eigenvalue densities.

Samples batches of n x n matrices with entries drawn iid from the discrete
population {-1, t, 1}, computes every eigenvalue with one vectorized
np.linalg.eigvals call over the stacked batch, and renders a log1p-scaled
2D histogram of the spectra in the complex plane.

Run interactively (needs a GUI backend):

    uv run python src/bohemian.py

Render one static PNG per family:

    uv run python src/bohemian.py --save frontend/images/bohemian

Sweep GIF (the animation at the top of frontend/bohemian.html)
--------------------------------------------------------------

    uv run python src/bohemian.py --gif frontend/images/bohemian-sweep.gif \
        --gif-cache /var/data/bohemian-sweep-grids.npz

Renders the tridiagonal ensemble at every t step across [GIF_T0, GIF_T1],
then assembles a boomerang loop (forward then reversed, so the endpoints
are seamless). Knobs are the GIF_* constants below, in two groups:

- data knobs (GIF_N, GIF_BATCH, GIF_DT, GIF_T0/T1, GIF_BINS): change what
  is computed; a full recompute takes ~20-30 min on this VPS (2 cores).
  Sweep speed = GIF_DT * GIF_FPS in t-units/second: to slow the sweep
  while keeping it smooth, shrink GIF_DT (more, closer frames) rather
  than just lowering GIF_FPS. To animate another family, edit _gif_frame.
- encoding knobs (GIF_FPS, GIF_LEVELS, colormap in render_sweep_gif):
  change only how the cached grids are turned into a GIF; re-encoding
  from cache takes seconds. NB file size scales with frame count.

The --gif-cache file holds the stack of per-timestep count histograms
(shape n_frames x GIF_BINS x GIF_BINS, uint16) - the expensive eigenvalue
work, before any color/encoding decisions. It is disposable: delete it
and the next run recomputes it. The data knobs are stored inside it and
a mismatch auto-invalidates, so a stale cache is never silently reused.

Why the animation is smooth: every frame reuses identical random draws
(only t changes, so there is no Monte Carlo flicker between frames), and
the per-frame color ceiling is smoothed over a 9-frame window so overall
brightness glides instead of popping as occupancy changes with t.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

FAMILIES = ("tridiagonal", "dense", "hessenberg", "toeplitz")

DEFAULT_N = 5
DEFAULT_BATCH = 200_000
DEFAULT_T = 0.0
BINS = 1000
PREVIEW_BATCH = 30_000  # cheap batch used while a slider is being dragged


class Sampler:
    """Holds the random draws so a change in t remaps values without resampling.

    Entries are stored as indices into the population vector [-1, t, 1];
    only n or batch changes force a fresh draw, and shrinking the batch just
    slices the cached draw.
    """

    def __init__(self, seed: int = 7):
        self.rng = np.random.default_rng(seed)
        self.n = 0
        self.idx = None       # (B, n, n) population indices for elementwise families
        self.idx_toep = None  # (B, 2n-1) population indices for the Toeplitz diagonals

    def ensure(self, n: int, batch: int) -> None:
        if self.idx is None or n != self.n or batch > self.idx.shape[0]:
            self.n = n
            self.idx = self.rng.integers(0, 3, size=(batch, n, n), dtype=np.int8)
            self.idx_toep = self.rng.integers(0, 3, size=(batch, 2 * n - 1), dtype=np.int8)

    def matrices(self, family: str, n: int, batch: int, t: float) -> np.ndarray:
        self.ensure(n, batch)
        pop = np.array([-1.0, t, 1.0], dtype=np.float32)
        if family == "toeplitz":
            diags = pop[self.idx_toep[:batch]]           # (B, 2n-1)
            i, j = np.indices((n, n))
            return diags[:, i - j + n - 1]               # T[i, j] = c[i-j]
        a = pop[self.idx[:batch]]                        # (B, n, n)
        if family == "dense":
            return a
        if family == "tridiagonal":
            i, j = np.indices((n, n))
            return np.where(np.abs(i - j) <= 1, a, 0.0)
        if family == "hessenberg":
            h = np.triu(a)                               # strict lower part zeroed
            sub = np.arange(1, n)
            h[:, sub, sub - 1] = 1.0                     # unit subdiagonal
            return h
        raise ValueError(f"unknown family {family!r}")


def eigenvalues(mats: np.ndarray, chunk: int = 32_768) -> np.ndarray:
    """All eigenvalues of a stacked batch, chunked only to bound memory."""
    out = [np.linalg.eigvals(mats[s : s + chunk]) for s in range(0, len(mats), chunk)]
    return np.concatenate(out).ravel()


def density(eigs: np.ndarray, r: float, bins: int = BINS) -> np.ndarray:
    h, _, _ = np.histogram2d(
        eigs.real, eigs.imag, bins=bins, range=[[-r, r], [-r, r]]
    )
    return np.log1p(h.T)  # transpose so imag runs along the vertical axis


def robust_vmax(grid: np.ndarray) -> float:
    """Color-scale ceiling: high quantile of the populated bins.

    Real-axis bins hold thousands of eigenvalues each, so even after log1p the
    raw maximum crushes the off-axis cloud to near-black; clipping there lets
    the axis saturate into a filament while the bulk stays visible.
    """
    pos = grid[grid > 0]
    if not pos.size:
        return 1.0
    if pos.size < 0.03 * grid.size:
        # Sparse spectrum (discrete families): most populated bins hold one or
        # two eigenvalues, so push those to the bright end of the map.
        return float(max(np.quantile(pos, 0.90), np.log1p(2)))
    return float(np.quantile(pos, 0.98))


def axis_radius(n: int) -> float:
    """Fixed symmetric extent per n, sized to hold the spectra for |t| <= 1.5."""
    return round(1.15 * np.sqrt(n) + 0.35, 2)


def compute(sampler: Sampler, family: str, n: int, batch: int, t: float) -> np.ndarray:
    return density(eigenvalues(sampler.matrices(family, n, batch, t)), axis_radius(n))


# ---------------------------------------------------------------- interactive


def run_interactive() -> None:
    import matplotlib.pyplot as plt
    from matplotlib.widgets import RadioButtons, Slider

    bg, panel, ink = "#0d0d10", "#16161c", "#c9c4bb"
    plt.rcParams.update(
        {
            "figure.facecolor": bg,
            "axes.facecolor": bg,
            "text.color": ink,
            "xtick.color": ink,
            "ytick.color": ink,
        }
    )

    state = {"family": "tridiagonal", "n": DEFAULT_N, "batch": DEFAULT_BATCH, "t": DEFAULT_T}
    sampler = Sampler()

    fig = plt.figure(figsize=(11.5, 8.6))
    ax = fig.add_axes([0.03, 0.05, 0.62, 0.9])
    ax.set_aspect("equal")
    for spine in ax.spines.values():
        spine.set_color("#33333d")
    ax.tick_params(labelsize=8, colors="#8a8a94")

    r = axis_radius(state["n"])
    im = ax.imshow(
        compute(sampler, **state),
        origin="lower",
        extent=(-r, r, -r, r),
        cmap="magma",
        interpolation="nearest",
    )
    title = ax.set_title("", fontsize=11, color=ink, family="monospace")

    def refresh(batch: int) -> None:
        r = axis_radius(state["n"])
        grid = compute(sampler, state["family"], state["n"], batch, state["t"])
        im.set_data(grid)
        im.set_extent((-r, r, -r, r))
        im.set_clim(0, robust_vmax(grid))
        ax.set_xlim(-r, r)
        ax.set_ylim(-r, r)
        title.set_text(
            f"{state['family']}  n={state['n']}  entries {{-1, {state['t']:+.2f}, 1}}"
            f"  |  {batch:,} matrices, {batch * state['n']:,} eigenvalues"
        )
        fig.canvas.draw_idle()

    # -- controls ------------------------------------------------------------
    rax = fig.add_axes([0.70, 0.55, 0.27, 0.33], facecolor=panel)
    rax.set_title("family", fontsize=9, color=ink, loc="left")
    radio = RadioButtons(rax, FAMILIES, active=FAMILIES.index("tridiagonal"), activecolor="#e8743d")
    for lbl in radio.labels:
        lbl.set_color(ink)
        lbl.set_fontsize(10)

    def slider(y: float, label: str, lo, hi, init, step=None) -> Slider:
        sax = fig.add_axes([0.72, y, 0.23, 0.03], facecolor=panel)
        s = Slider(sax, label, lo, hi, valinit=init, valstep=step,
                   color="#e8743d", track_color="#2a2a33")
        s.label.set_color(ink)
        s.valtext.set_color(ink)
        return s

    s_n = slider(0.42, "n", 3, 12, DEFAULT_N, step=1)
    s_batch = slider(0.34, "batch", 20_000, 500_000, DEFAULT_BATCH, step=20_000)
    s_t = slider(0.26, "t", -1.5, 1.5, DEFAULT_T)

    # Slider drags recompute with a small preview batch so the morph feels
    # live; the full batch is rendered once the mouse button is released.
    def on_family(label: str) -> None:
        state["family"] = label
        refresh(state["batch"])

    def on_drag(_val) -> None:
        state["n"] = int(s_n.val)
        state["batch"] = int(s_batch.val)
        state["t"] = float(s_t.val)
        refresh(min(state["batch"], PREVIEW_BATCH))

    def on_release(event) -> None:
        if event.name == "button_release_event":
            refresh(state["batch"])

    radio.on_clicked(on_family)
    for s in (s_n, s_batch, s_t):
        s.on_changed(on_drag)
    fig.canvas.mpl_connect("button_release_event", on_release)

    refresh(state["batch"])
    plt.show()


# ------------------------------------------------------------------- headless


def run_save(outdir: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    outdir.mkdir(parents=True, exist_ok=True)
    sampler = Sampler()
    # Dense and Hessenberg are already rich at n=5; the more constrained
    # families have tiny matrix spaces there, so render them at n=8.
    gallery_n = {"tridiagonal": 8, "toeplitz": 8}
    for family in FAMILIES:
        n = gallery_n.get(family, DEFAULT_N)
        grid = compute(sampler, family, n, DEFAULT_BATCH, DEFAULT_T)
        path = outdir / f"{family}.png"
        plt.imsave(path, grid, cmap="magma", origin="lower",
                   vmin=0.0, vmax=robust_vmax(grid))
        print(f"wrote {path}")


# ---------------------------------------------------------------- sweep gif

GIF_N = 8
GIF_BATCH = 1_000_000
GIF_DT = 0.015
GIF_T0, GIF_T1 = -1.5, 1.5
GIF_BINS = 720
GIF_FPS = 20
GIF_LEVELS = 64  # coarser-than-256 quantization compresses far better in LZW

_gif_idx = None  # per-process cache of the population-index draws


def _gif_init() -> None:
    # Same seed in every worker: all frames share identical draws (common
    # random numbers), so the only frame-to-frame change is t itself and the
    # morph carries no Monte Carlo flicker.
    global _gif_idx
    _gif_idx = np.random.default_rng(7).integers(
        0, 3, size=(GIF_BATCH, 3 * GIF_N - 2), dtype=np.int8)


def _gif_frame(t: float) -> np.ndarray:
    """Count grid (uint16, clipped) for tridiagonal n=GIF_N at population t."""
    n = GIF_N
    r = 1.15 * np.sqrt(n) + 0.35
    scale = GIF_BINS / (2 * r)
    pop = np.array([-1.0, t, 1.0], dtype=np.float32)
    vals = pop[_gif_idx]                        # (B, 3n-2) diagonal entries
    diag = np.arange(n)
    h = np.zeros(GIF_BINS * GIF_BINS, dtype=np.int64)
    for s in range(0, GIF_BATCH, 25_000):
        v = vals[s : s + 25_000]
        a = np.zeros((v.shape[0], n, n), dtype=np.float32)
        a[:, diag, diag] = v[:, :n]
        a[:, diag[1:], diag[:-1]] = v[:, n : 2 * n - 1]
        a[:, diag[:-1], diag[1:]] = v[:, 2 * n - 1 :]
        e = np.linalg.eigvals(a).ravel()
        re = np.concatenate([e.real, e.real])
        im = np.concatenate([e.imag, -e.imag])   # conjugate binning
        ix = np.floor((re + r) * scale).astype(np.int64)
        iy = np.floor((im + r) * scale).astype(np.int64)
        ok = (ix >= 0) & (ix < GIF_BINS) & (iy >= 0) & (iy < GIF_BINS)
        h += np.bincount((GIF_BINS - 1 - iy[ok]) * GIF_BINS + ix[ok],
                         minlength=GIF_BINS * GIF_BINS)
    return np.minimum(h, 65535).astype(np.uint16).reshape(GIF_BINS, GIF_BINS)


def compute_sweep_grids(cache: Path | None, processes: int = 2) -> np.ndarray:
    """Count grids for every t step; cached because they take ~20 min.

    The cache stores the data-generating parameters alongside the grids and
    is ignored whenever they differ, so twiddling GIF_* knobs that change
    the data (n, batch, dt, range, bins) safely triggers a recompute.
    Encoding-only knobs (fps, levels, colormap) reuse the cache.
    """
    import multiprocessing as mp

    if cache is not None and cache.suffix != ".npz":
        cache = cache.with_suffix(".npz")  # np.savez appends .npz regardless
    params = np.array([GIF_N, GIF_BATCH, GIF_DT, GIF_T0, GIF_T1, GIF_BINS], dtype=np.float64)
    ts = np.round(np.arange(GIF_T0, GIF_T1 + GIF_DT / 2, GIF_DT), 4)
    if cache is not None and cache.exists():
        try:
            with np.load(cache) as z:
                if np.array_equal(z["params"], params):
                    print(f"reusing cached grids from {cache}")
                    return z["grids"]
            print("cache was built with different parameters; recomputing")
        except Exception:
            print("cache unreadable; recomputing")
    print(f"{len(ts)} frames, {GIF_BATCH:,} matrices each, {processes} processes")
    out = np.empty((len(ts), GIF_BINS, GIF_BINS), dtype=np.uint16)
    with mp.Pool(processes, initializer=_gif_init) as pool:
        for i, g in enumerate(pool.imap(_gif_frame, ts)):
            out[i] = g
            print(f"  frame {i + 1}/{len(ts)} (t={ts[i]:+.2f})", flush=True)
    if cache is not None:
        np.savez(cache, grids=out, params=params)
    return out


def render_sweep_gif(path: Path, cache: Path | None = None, processes: int = 2) -> None:
    """Looping boomerang GIF of the tridiagonal spectrum as t sweeps."""
    from matplotlib import cm
    from PIL import Image

    grids = compute_sweep_grids(cache, processes)
    logs = [np.log1p(g.astype(np.float32)) for g in grids]
    # Per-frame color ceilings flicker as occupancy changes with t; smooth
    # them over neighbouring frames so brightness glides instead of popping.
    vmaxes = np.array([robust_vmax(l) for l in logs])
    kernel = np.ones(9) / 9
    vs = np.convolve(np.pad(vmaxes, 4, mode="edge"), kernel, mode="valid")

    pal = (np.array(cm.magma(np.linspace(0, 1, GIF_LEVELS)))[:, :3] * 255
           ).round().astype(np.uint8).ravel().tolist()
    frames = []
    for l, v in zip(logs, vs):
        idx = np.clip(l / v * (GIF_LEVELS - 1), 0, GIF_LEVELS - 1).astype(np.uint8)
        img = Image.fromarray(idx, mode="P")
        img.putpalette(pal)
        frames.append(img)
    frames += frames[-2:0:-1]  # boomerang: seamless loop back to the start
    path.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(path, save_all=True, append_images=frames[1:],
                   duration=1000 // GIF_FPS, loop=0)
    print(f"wrote {path} ({path.stat().st_size:,} bytes, {len(frames)} frames)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", metavar="DIR", type=Path,
                        help="render one PNG per family to DIR instead of opening the UI")
    parser.add_argument("--gif", metavar="FILE", type=Path,
                        help="render the looping t-sweep GIF used by the web page")
    parser.add_argument("--gif-cache", metavar="FILE", type=Path, default=None,
                        help="npy cache of the sweep count grids (skips the eigenvalue work)")
    args = parser.parse_args()
    if args.gif:
        render_sweep_gif(args.gif, cache=args.gif_cache)
    elif args.save:
        run_save(args.save)
    else:
        run_interactive()


if __name__ == "__main__":
    main()
