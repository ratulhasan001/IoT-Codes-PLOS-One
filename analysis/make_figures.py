
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, LogLocator

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["DejaVu Serif"],
    "font.size": 8,
    "axes.labelsize": 8,
    "axes.titlesize": 8,
    "xtick.labelsize": 7.5,
    "ytick.labelsize": 7.5,
    "legend.fontsize": 7.5,
    "axes.linewidth": 0.6,
    "xtick.major.width": 0.6,
    "ytick.major.width": 0.6,
    "grid.linewidth": 0.4,
    "pdf.fonttype": 42,
})

C = {
    "orange":  "#E69F00",
    "sky":     "#56B4E9",
    "green":   "#009E73",
    "yellow":  "#F0E442",
    "blue":    "#0072B2",
    "vermil":  "#D55E00",
    "purple":  "#CC79A7",
    "grey":    "#4D4D4D",
}

MM = 1 / 25.4
FULL = 168 * MM

src = ["ACC_X", "ACC_Y", "ACC_Z", "LIGHT", "SOUND", "HALL", "JITTER"]
iid = [0.619, 0.750, 0.974, 0.939, 0.897, 0.952, 0.994]
non = [0.285, 0.214, 0.319, 0.523, 0.523, 0.610, 0.726]

fig, ax = plt.subplots(figsize=(FULL, 55 * MM))
x = range(len(src))
w = 0.38
b1 = ax.bar([i - w / 2 for i in x], iid, w, label="IID upper bound",
            color=C["sky"], edgecolor="black", linewidth=0.6)
b2 = ax.bar([i + w / 2 for i in x], non, w, label="non-IID estimate",
            color=C["blue"], edgecolor="black", linewidth=0.6)
for r in b1:
    ax.text(r.get_x() + r.get_width() / 2, r.get_height() + 0.015,
            f"{r.get_height():.3f}", ha="center", va="bottom", fontsize=6)
for r in b2:
    ax.text(r.get_x() + r.get_width() / 2, r.get_height() + 0.015,
            f"{r.get_height():.3f}", ha="center", va="bottom", fontsize=6,
            color=C["blue"])
ax.set_xticks(list(x))
ax.set_xticklabels([s.replace("_", r"\_").replace(r"\_", "_") for s in src])
ax.set_ylabel("min-entropy (bits per sample)")
ax.set_ylim(0, 1.13)
ax.yaxis.grid(True, linestyle=":", color="0.7")
ax.set_axisbelow(True)
ax.legend(frameon=False, ncol=2, loc="upper center",
          bbox_to_anchor=(0.5, 1.16))
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
fig.tight_layout()
fig.savefig("fig_minentropy.pdf", bbox_inches="tight", pad_inches=0.02)
fig.savefig("fig_minentropy.png", dpi=200, bbox_inches="tight", pad_inches=0.02)
plt.close(fig)

lab = ["A\nsix independent", "B\nsensors grouped",
       "C\nACC also grouped", "D\nall analogue grouped"]
tot = [680, 412, 284, 203]

fig, ax = plt.subplots(figsize=(FULL, 62 * MM))
cols = [C["green"], C["green"], C["orange"], C["vermil"]]
bars = ax.bar(range(4), tot, 0.55, color=cols, edgecolor="black",
              linewidth=0.6)
for r, v in zip(bars, tot):
    ax.text(r.get_x() + r.get_width() / 2, v + 12, str(v),
            ha="center", va="bottom", fontsize=8)
ax.axhline(256, linestyle="--", color=C["vermil"], linewidth=1.1)
ax.text(3.45, 300, "256-bit seed requirement", ha="right", va="bottom",
        fontsize=7, color=C["vermil"])
ax.set_xticks(range(4))
ax.set_xticklabels(lab)
ax.set_ylabel("entropy budget (bits per block)", labelpad=4)
ax.set_ylim(0, 800)
ax.yaxis.grid(True, linestyle=":", color="0.7")
ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
fig.tight_layout()
fig.savefig("fig_budget.pdf", bbox_inches="tight", pad_inches=0.02)
fig.savefig("fig_budget.png", dpi=200, bbox_inches="tight", pad_inches=0.02)
plt.close(fig)

pts = [
    ("ML-DSA-44",     2420,  4.77, "lattice",   (7, -3),   "left"),
    ("ML-DSA-65",     3309,  7.71, "lattice",   (7, -3),   "left"),
    ("ML-DSA-87",     4627, 12.59, "lattice",   (0, 9),    "center"),
    ("Falcon-512",     654,  3.00, "ntru",      (0, 9),    "center"),
    ("Falcon-1024",   1273,  6.42, "ntru",      (0, 9),    "center"),
    ("SLH-DSA-128s",  7856, 11.65, "hash",      (0, -14),  "center"),
    ("SLH-DSA-128f", 17088, 29.35, "hash",      (-9, 2),   "right"),
    ("SLH-DSA-192f", 35664, 50.29, "hash",      (-9, 2),   "right"),
]
style = {
    "lattice": dict(marker="o", color=C["blue"],   label="ML-DSA (lattice)"),
    "ntru":    dict(marker="s", color=C["green"],  label="Falcon (NTRU lattice)"),
    "hash":    dict(marker="^", color=C["vermil"], label="SLH-DSA (hash)"),
}

fig, ax = plt.subplots(figsize=(FULL, 68 * MM))
seen = set()
for name, sz, vf, fam, off, ha in pts:
    st = dict(style[fam])
    lbl = st.pop("label")
    ax.plot(sz, vf, linestyle="none", markersize=5,
            markerfacecolor=st["color"],
            markeredgecolor=st["color"], markeredgewidth=0.9,
            marker=st["marker"],
            label=lbl if fam not in seen else None)
    seen.add(fam)
    ax.annotate(name, (sz, vf), textcoords="offset points", xytext=off,
                ha=ha, fontsize=7, color=st["color"])

ax.set_xscale("log")
ax.set_xlim(480, 52000)
ax.set_ylim(0, 58)
ax.set_xlabel("signature size (bytes, log scale)")
ax.set_ylabel("verification latency (ms)")
ax.xaxis.set_major_locator(LogLocator(base=10))
ax.xaxis.set_major_formatter(FuncFormatter(
    lambda v, _: f"{int(v):,}".replace(",", "\u2009")))
ax.grid(True, which="major", linestyle=":", color="0.75")
ax.grid(True, which="minor", axis="x", linestyle=":", color="0.9")
ax.set_axisbelow(True)
ax.legend(frameon=False, loc="upper left")
for s in ("top", "right"):
    ax.spines[s].set_visible(False)

ax.annotate("smaller and faster",
            xy=(560, 0.9), xytext=(1500, 0.9),
            fontsize=7, va="center", ha="left", color=C["grey"],
            arrowprops=dict(arrowstyle="->", linewidth=0.7, color=C["grey"]))

fig.tight_layout()
fig.savefig("fig_tradeoff.pdf", bbox_inches="tight", pad_inches=0.02)
fig.savefig("fig_tradeoff.png", dpi=200, bbox_inches="tight", pad_inches=0.02)
plt.close(fig)

print("wrote fig_minentropy, fig_budget, fig_tradeoff (.pdf and .png)")

import numpy as np

names = ["ACC_X", "ACC_Y", "ACC_Z", "LIGHT", "SOUND", "HALL"]
full = np.array([
    [ 1.000, -0.274,  0.248, -0.241, -0.214, -0.179],
    [-0.274,  1.000, -0.182,  0.396,  0.365,  0.311],
    [ 0.248, -0.182,  1.000, -0.221, -0.183, -0.145],
    [-0.241,  0.396, -0.221,  1.000,  0.923,  0.809],
    [-0.214,  0.365, -0.183,  0.923,  1.000,  0.966],
    [-0.179,  0.311, -0.145,  0.809,  0.966,  1.000]])
lsb = np.array([
    [ 1.000, -0.062,  0.040,  0.014, -0.010, -0.013],
    [-0.062,  1.000, -0.031, -0.000,  0.021,  0.007],
    [ 0.040, -0.031,  1.000, -0.013,  0.008, -0.002],
    [ 0.014, -0.000, -0.013,  1.000, -0.008,  0.005],
    [-0.010,  0.021,  0.008, -0.008,  1.000, -0.195],
    [-0.013,  0.007, -0.002,  0.005, -0.195,  1.000]])

fig, axes = plt.subplots(1, 2, figsize=(FULL, 80 * MM))
fig.subplots_adjust(wspace=0.42)
for ax, M, title in zip(axes, (full, lsb),
                        ("full sample value", "least significant bit only")):
    D = M.astype(float).copy()
    np.fill_diagonal(D, np.nan)
    im = ax.imshow(D, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(6)); ax.set_yticks(range(6))
    ax.set_xticklabels(names, rotation=45, ha="right", fontsize=7)
    ax.set_yticklabels(names, fontsize=7)
    ax.set_title(title, fontsize=8, pad=6)
    for i in range(6):
        for j in range(6):
            if i == j:
                ax.text(j, i, "--", ha="center", va="center",
                        fontsize=7, color=C["grey"])
            else:
                v = M[i, j]
                ax.text(j, i, f"{v:+.3f}", ha="center", va="center",
                        fontsize=6.2,
                        color="white" if abs(v) > 0.62 else "black")
    for sp in ax.spines.values():
        sp.set_linewidth(0.6)
    ax.set_xticks(np.arange(-0.5, 6, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, 6, 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=0.8)
    ax.tick_params(which="minor", length=0)

cb = fig.colorbar(im, ax=axes, fraction=0.022, pad=0.02)
cb.set_label(r"$r$", fontsize=8)
cb.set_ticks([-1, -0.5, 0, 0.5, 1])
cb.ax.tick_params(labelsize=7)
cb.outline.set_linewidth(0.6)
fig.savefig("fig_correlation.pdf", bbox_inches="tight", pad_inches=0.02)
fig.savefig("fig_correlation.png", dpi=200, bbox_inches="tight", pad_inches=0.02)
plt.close(fig)
print("wrote fig_correlation (.pdf and .png)")

acf = {
    "ACC_X": [0.114, 0.116, 0.109, 0.123, 0.118, 0.124, 0.130, 0.118],
    "ACC_Y": [0.285, 0.259, 0.278, 0.287, 0.282, 0.282, 0.295, 0.278],
    "ACC_Z": [0.142, 0.087, 0.094, 0.096, 0.090, 0.092, 0.114, 0.094],
    "LIGHT": [-0.082, 0.004, -0.016, 0.090, 0.019, 0.025, 0.058, -0.016],
    "SOUND": [0.079, 0.029, 0.007, 0.001, 0.001, 0.016, 0.021, 0.028],
    "HALL":  [0.074, -0.030, -0.019, 0.001, 0.004, -0.024, -0.031, 0.017],
}
mk = {"ACC_X": ("o", C["blue"],   "-"),  "ACC_Y": ("s", C["sky"],    "-"),
      "ACC_Z": ("^", C["purple"], "-"),  "LIGHT": ("v", C["green"],  "--"),
      "SOUND": ("D", C["orange"], "--"), "HALL":  ("*", C["vermil"], "--")}
lags = list(range(1, 9))

fig, ax = plt.subplots(figsize=(FULL, 62 * MM))
for name, vals in acf.items():
    m, col, ls = mk[name]
    ax.plot(lags, vals, marker=m, color=col, linestyle=ls, linewidth=1.1,
            markersize=4.2, markerfacecolor=col, markeredgecolor=col,
            markeredgewidth=0.8, label=name)
ax.axhline(0, color=C["grey"], linewidth=0.7)

ax.set_xlabel("lag $k$")
ax.set_ylabel(r"autocorrelation $\rho_s(k)$")
ax.set_xticks(lags)
ax.set_xlim(0.7, 8.3)
ax.set_ylim(-0.13, 0.34)
ax.yaxis.grid(True, linestyle=":", color="0.75")
ax.set_axisbelow(True)
ax.legend(frameon=False, ncol=6, loc="upper center",
          bbox_to_anchor=(0.5, 1.15), columnspacing=1.1, handletextpad=0.4)
for sp in ("top", "right"):
    ax.spines[sp].set_visible(False)
fig.savefig("fig_acf.pdf", bbox_inches="tight", pad_inches=0.02)
fig.savefig("fig_acf.png", dpi=200, bbox_inches="tight", pad_inches=0.02)
plt.close(fig)
print("wrote fig_acf (.pdf and .png)")
