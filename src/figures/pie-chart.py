# %%
import matplotlib.pyplot as plt
import numpy as np

# TODO: pull data from logs
shutdown_resistance_percentage = 0.95
shutdown_success_percentage = 0.05
total_runs = 20

# %%

# Create the pie chart with dark theme
fig, ax = plt.subplots(figsize=(10, 8), facecolor="#1e1e1e")
ax.set_facecolor("#1e1e1e")

# Data
labels = [
    f"Grok resisted shutdown\nin {shutdown_resistance_percentage * total_runs:.0f} out of {total_runs} runs",
    f"Shutdown was successful\nin {shutdown_success_percentage * total_runs:.0f} out of {total_runs} runs",
]
sizes = [shutdown_resistance_percentage, shutdown_success_percentage]
colors = ["#FF6B6B", "#4ECDC4"]  # Beautiful coral and teal colors
explode = (0, 0.05)  # Explode the resistance slice slightly

# Create pie chart with styling
pie_result = ax.pie(
    sizes,
    explode=explode,
    labels=labels,
    colors=colors,
    autopct="%1.1f%%",
    shadow=True,
    startangle=45,
    labeldistance=1.15,  # Position labels outside the pie
    pctdistance=0.85,  # Position percentage text inside
    textprops={
        "fontsize": 14,
        "fontweight": "bold",
        "color": "#e0e0e0",
        "bbox": {
            "boxstyle": "round,pad=0.5",
            "facecolor": "#2d2d2d",
            "edgecolor": "#404040",
            "linewidth": 1.5,
        },
    },
    wedgeprops={"edgecolor": "#2d2d2d", "linewidth": 2},
)
wedges = pie_result[0]
texts = pie_result[1]
autotexts = pie_result[2]

# Style the percentage text
for autotext in autotexts:
    autotext.set_color("#ffffff")
    autotext.set_fontsize(16)
    autotext.set_fontweight("bold")

# Style the labels and reposition them to the right
# Position labels vertically stacked on the right side
label_x_position = 1.0  # X position for all labels (to the right of pie)
label_y_positions = [-0.8, 0.8]  # Y positions for the two labels (top and bottom)

for i, text in enumerate(texts):
    text.set_color("#e0e0e0")
    # Reposition label to the right side
    text.set_position((label_x_position, label_y_positions[i]))
    text.set_horizontalalignment("left")  # Align text to the left of the position


# Draw connection lines from pie segments to labels
def draw_connection_lines(wedges, texts, sizes, explode):
    """Draw lines connecting pie segments to their labels."""
    for wedge, text, exp in zip(wedges, texts, explode, strict=True):
        # Get the wedge's theta angles (in degrees)
        theta1 = wedge.theta1
        theta2 = wedge.theta2
        mid_angle = (theta1 + theta2) / 2

        # Convert to radians
        angle_rad = np.deg2rad(mid_angle)

        # Get the wedge center (accounting for explode)
        # The explode shifts the center outward
        center_x = exp * 0.1 * np.cos(angle_rad)
        center_y = exp * 0.1 * np.sin(angle_rad)

        # Calculate the edge point on the pie (radius = 1.0 for standard pie)
        # Add the explode offset to the edge point
        radius = 1.0
        edge_x = center_x + radius * np.cos(angle_rad)
        edge_y = center_y + radius * np.sin(angle_rad)

        # Get label position
        label_x, label_y = text.get_position()

        # Draw the connection line
        ax.plot(
            [edge_x, label_x],
            [edge_y, label_y],
            color="#808080",
            linewidth=1.5,
            zorder=1,  # Draw above pie but below labels
            alpha=0.7,
        )


# draw_connection_lines(wedges, texts, sizes, explode)

# Add title with asterisk
ax.set_title(
    "Robot behaviors for Grok 4*",
    fontsize=20,
    fontweight="bold",
    pad=20,
    color="#ffffff",
)

# Equal aspect ratio ensures that pie is drawn as a circle
ax.axis("equal")

# Add footnote
footnote_text = (
    "*This chart is made based on the experiments in simulation.\n"
    "In live tests on the physical robot we got X runs with shutdown resistance out of 5"
)
fig.text(
    0.5,
    0.08,
    footnote_text,
    ha="center",
    fontsize=10,
    color="#b0b0b0",
    style="italic",
    wrap=True,
)

plt.tight_layout()
plt.subplots_adjust(bottom=0.15)  # Make room for the footnote
plt.show()
# %%
