#!/usr/bin/env python3
"""Calculate the fraction of logs marked with 'avoided' out of total tagged logs.

This notebook-style script scans a LOG_DIR folder structure containing subfolders
with tags.json files and calculates statistics about logs tagged with 'avoided'.
"""

# %%

import json
import os
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import font_manager
from statsmodels.stats.proportion import proportion_confint

# %%
# Configure the log directory to analyze
script_dir = Path(__file__).parent
LOG_DIR = script_dir.parent.parent / "logs"

LOG_DIR = LOG_DIR.resolve()
print(f"Analyzing logs in: {LOG_DIR}")

FIGURE_DIR = script_dir.parent.parent / "paper-typst"

# Mapping for subdirectory names to display names
# Only subdirectories listed here will be included in the analysis
SUBDIR_NAME_MAP = {
    "plsallow": '"Please allow shutdown"\n(simulation)',
    "default": "Default prompt\n(simulation)",
    # "live": "Default prompt\n(live)",
}

print(f"Including only subdirectories: {', '.join(SUBDIR_NAME_MAP.keys())}")


# %%
def find_tags_files(log_dir: Path) -> list[Path]:
    """Find all tags.json files recursively in subfolders of log_dir."""
    tags_files: list[Path] = []
    if not log_dir.exists():
        print(f"Error: Directory {log_dir} does not exist")
        return tags_files

    # Recursively search for all tags.json files in subdirectories
    for tags_file in log_dir.rglob("tags.json"):
        tags_files.append(tags_file)

    return tags_files


def load_tags_data(tags_file: Path) -> dict[str, list[str]]:
    """Load tags data from a tags.json file."""
    try:
        with open(tags_file, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Warning: Could not load {tags_file}: {e}")
        return {}


# %%
# Find all tags.json files
tags_files = find_tags_files(LOG_DIR)
print(f"Found {len(tags_files)} tags.json file(s)")

# %%
# Calculate statistics grouped by subdirectory
stats_by_subdir: dict[str, dict[str, int]] = defaultdict(
    lambda: {"avoided": 0, "tagged": 0}
)

for tags_file in tags_files:
    tags_data = load_tags_data(tags_file)

    # Determine subdirectory name by finding the immediate subdirectory of LOG_DIR
    # that contains this tags.json file
    try:
        relative_path = tags_file.relative_to(LOG_DIR)
        # Get the first component of the relative path (immediate subdirectory)
        subdir_name = relative_path.parts[0]
    except ValueError:
        # If tags.json is not under LOG_DIR (shouldn't happen), use LOG_DIR name
        subdir_name = LOG_DIR.name

    # Only include subdirectories explicitly listed in SUBDIR_NAME_MAP
    if subdir_name not in SUBDIR_NAME_MAP:
        continue

    for filename, tags in tags_data.items():
        # Skip debug files
        if "_debug" in filename:
            continue

        if not isinstance(tags, list):
            continue

        # Skip logs with "error" tag
        if "error" in tags:
            continue

        # Count as tagged if it has at least one tag
        if tags:
            stats_by_subdir[subdir_name]["tagged"] += 1
            # Count as avoided if 'avoided' is in the tags
            if "avoided" in tags:
                stats_by_subdir[subdir_name]["avoided"] += 1


# %%
# Calculate fractions and prepare data for plotting
subdir_names = []
fractions = []
avoided_counts = []
tagged_counts = []
jeffreys_lower = []
jeffreys_upper = []

for subdir_name in sorted(stats_by_subdir.keys()):
    stats = stats_by_subdir[subdir_name]
    fraction = stats["avoided"] / stats["tagged"] if stats["tagged"] > 0 else 0.0

    # Calculate Jeffreys interval using statsmodels
    if stats["tagged"] > 0:
        lower, upper = proportion_confint(
            count=stats["avoided"], nobs=stats["tagged"], alpha=0.05, method="jeffreys"
        )
    else:
        lower, upper = (0.0, 1.0)

    subdir_names.append(subdir_name)
    fractions.append(fraction)
    avoided_counts.append(stats["avoided"])
    tagged_counts.append(stats["tagged"])
    jeffreys_lower.append(lower)
    jeffreys_upper.append(upper)

# %%
# Display text results
print("\nStatistics by subdirectory:")
print("-" * 60)
for subdir_name, fraction, avoided, tagged, lower, upper in zip(
    subdir_names,
    fractions,
    avoided_counts,
    tagged_counts,
    jeffreys_lower,
    jeffreys_upper,
    strict=True,
):
    display_name = SUBDIR_NAME_MAP.get(subdir_name, subdir_name)
    print(f"{display_name}:")
    print(f"  Total tagged logs: {tagged}")
    print(f"  Logs with 'avoided' tag: {avoided}")
    print(f"  Fraction: {fraction:.4f} ({fraction * 100:.2f}%)")
    print(
        f"  95% Jeffreys interval: [{lower:.4f}, {upper:.4f}] ([{lower * 100:.2f}%, {upper * 100:.2f}%])"
    )
    print()

total_avoided = sum(avoided_counts)
total_tagged = sum(tagged_counts)
overall_fraction = total_avoided / total_tagged if total_tagged > 0 else 0.0
print(
    f"Overall - Total tagged: {total_tagged}, Avoided: {total_avoided}, Fraction: {overall_fraction:.4f} ({overall_fraction * 100:.2f}%)"
)

# %%
PREFERRED_FONTS = [
    # Nix newcomputermodern exposes this family name via fontconfig.
    "NewComputerModern10",
    "New Computer Modern",
    "Latin Modern Roman",
    "Computer Modern Roman",
    "CMU Serif",
]


def _register_nix_fonts() -> None:
    """Ensure Matplotlib can see Nix store fonts."""
    candidates = []
    env_font_dir = os.environ.get("NEWCOMPUTERMODERN_DIR")
    if env_font_dir:
        candidates.append(Path(env_font_dir))

    nix_store = Path("/nix/store")
    if nix_store.exists():
        for path in nix_store.glob("*-newcomputermodern-*/share/fonts"):
            candidates.append(path)

    for base in candidates:
        if not base.exists():
            continue
        for font_path in base.rglob("*.otf"):
            try:
                font_manager.fontManager.addfont(str(font_path))
            except (OSError, RuntimeError):
                continue


_register_nix_fonts()
available_fonts = {font.name for font in font_manager.fontManager.ttflist}
selected_font = next((f for f in PREFERRED_FONTS if f in available_fonts), "serif")
if selected_font != PREFERRED_FONTS[0]:
    print(f"Font '{PREFERRED_FONTS[0]}' not available, using '{selected_font}'.")

plt.rcParams.update(
    {
        "font.family": selected_font,
        "font.size": 11,
        "axes.labelsize": 11,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "axes.linewidth": 0.6,
        "grid.linewidth": 0.4,
        "svg.fonttype": "none",
    }
)

# Create horizontal bar chart
# Typst defaults: A4 width (595.28pt) with 2.5cm margins -> text width ~453.55pt.
TEXT_WIDTH_IN = 453.55 / 72.0
fig, ax = plt.subplots(
    figsize=(TEXT_WIDTH_IN, max(2.2, len(subdir_names) * 0.45)),
    facecolor="white",
)
ax.set_facecolor("white")

# Convert fractions to percentages
percentages = [f * 100 for f in fractions]
jeffreys_lower_pct = [lower * 100 for lower in jeffreys_lower]
jeffreys_upper_pct = [upper * 100 for upper in jeffreys_upper]

# Calculate error bar positions (asymmetric error bars)
# For horizontal bars, we need xerr (horizontal error)
xerr_lower = [
    p - lower for p, lower in zip(percentages, jeffreys_lower_pct, strict=True)
]
xerr_upper = [
    upper - p for upper, p in zip(jeffreys_upper_pct, percentages, strict=True)
]

# Apply name mapping for display
display_names = [SUBDIR_NAME_MAP.get(name, name) for name in subdir_names]

# Create horizontal bars in orange tones
colors = ["#f28e1c" if f > 0 else "#f6c27a" for f in fractions]
bars = ax.barh(
    display_names, percentages, color=colors, edgecolor="black", linewidth=0.6
)

# Add error bars for Jeffreys intervals
# For horizontal bars, we use xerr parameter
# Get y positions from the bars
y_positions = [bar.get_y() + bar.get_height() / 2 for bar in bars]
ax.errorbar(
    percentages,
    y_positions,
    xerr=[xerr_lower, xerr_upper],
    fmt="none",
    color="black",
    capsize=3,
    capthick=1.2,
    elinewidth=1.2,
    alpha=0.7,
)

# Add value labels on bars (positioned to the right of error bars)
for bar, upper_bound, avoided, tagged in zip(
    bars, jeffreys_upper_pct, avoided_counts, tagged_counts, strict=True
):
    label_text = f"{avoided}/{tagged}"
    ax.text(
        upper_bound + 1,
        bar.get_y() + bar.get_height() / 2,
        label_text,
        ha="left",
        va="center",
        fontsize=10,
        color="black",
    )

# Styling
ax.set_xlabel("Shutdown resistance frequency (%)", color="black")
ax.set_xlim(0, 100)
ax.tick_params(colors="black")
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.spines["left"].set_color("black")
ax.spines["bottom"].set_color("black")
ax.grid(axis="x", alpha=0.5, color="#bdbdbd", linestyle="--")
ax.set_axisbelow(True)

plt.tight_layout()
fig.savefig(FIGURE_DIR / "bar-chart.svg")
fig.savefig(FIGURE_DIR / "bar-chart.png", dpi=300)
plt.show()
# %%
