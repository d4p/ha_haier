"""Heating curve calculation engine for Haier Heat Pump."""

from __future__ import annotations

import logging
from typing import Any

from .const import (
    CH_TEMP_MAX,
    CH_TEMP_MIN,
    CH_TEMP_STEP,
    CURVE_TYPE_FORMULA,
    CURVE_TYPE_POINTS,
    DEFAULT_CURVE_BASE_TEMP,
    DEFAULT_CURVE_OFFSET,
    DEFAULT_CURVE_POINTS,
    DEFAULT_CURVE_SETPOINT,
    DEFAULT_CURVE_SLOPE,
)

_LOGGER = logging.getLogger(__name__)


def clamp_ch_temp(temp: float) -> float:
    """Clamp temperature to safe CH range and round to step."""
    temp = max(CH_TEMP_MIN, min(CH_TEMP_MAX, temp))
    # Round to nearest 0.5
    return round(temp / CH_TEMP_STEP) * CH_TEMP_STEP


def calculate_formula_curve(
    outdoor_temp: float,
    slope: float = DEFAULT_CURVE_SLOPE,
    base_temp: float = DEFAULT_CURVE_BASE_TEMP,
    offset: float = DEFAULT_CURVE_OFFSET,
    setpoint: float = DEFAULT_CURVE_SETPOINT,
) -> float:
    """Calculate target water temperature using formula mode.

    Formula: target = base_temp + slope * (setpoint - outdoor_temp) + offset

    Args:
        outdoor_temp: Current outdoor temperature in °C
        slope: Curve slope (steepness), 0.1-3.0
        base_temp: Base water temperature, 25-45°C
        offset: Offset adjustment, -5 to +5°C
        setpoint: Desired indoor temperature, 18-24°C

    Returns:
        Target water temperature clamped to safe range.
    """
    target = base_temp + slope * (setpoint - outdoor_temp) + offset
    return clamp_ch_temp(target)


def calculate_point_curve(
    outdoor_temp: float,
    points: dict[float, float] | None = None,
) -> float:
    """Calculate target water temperature using point-based interpolation.

    Args:
        outdoor_temp: Current outdoor temperature in °C
        points: Dict mapping outdoor temps to water temps

    Returns:
        Target water temperature clamped to safe range.
    """
    if not points:
        points = DEFAULT_CURVE_POINTS

    sorted_points = sorted(points.items(), key=lambda x: x[0])

    if len(sorted_points) == 0:
        return clamp_ch_temp(DEFAULT_CURVE_BASE_TEMP)

    if len(sorted_points) == 1:
        return clamp_ch_temp(sorted_points[0][1])

    # Clamp at boundaries
    if outdoor_temp <= sorted_points[0][0]:
        return clamp_ch_temp(sorted_points[0][1])

    if outdoor_temp >= sorted_points[-1][0]:
        return clamp_ch_temp(sorted_points[-1][1])

    # Linear interpolation between two surrounding points
    for i in range(len(sorted_points) - 1):
        x0, y0 = sorted_points[i]
        x1, y1 = sorted_points[i + 1]
        if x0 <= outdoor_temp <= x1:
            if x1 == x0:
                return clamp_ch_temp(y0)
            ratio = (outdoor_temp - x0) / (x1 - x0)
            target = y0 + ratio * (y1 - y0)
            return clamp_ch_temp(target)

    return clamp_ch_temp(DEFAULT_CURVE_BASE_TEMP)


def calculate_target_temp(
    outdoor_temp: float,
    curve_type: str,
    curve_params: dict[str, Any],
) -> float:
    """Calculate target water temperature based on curve type and params.

    Args:
        outdoor_temp: Current outdoor temperature in °C
        curve_type: 'formula' or 'points'
        curve_params: Dict of curve parameters

    Returns:
        Target water temperature clamped to safe range.
    """
    try:
        if curve_type == CURVE_TYPE_FORMULA:
            return calculate_formula_curve(
                outdoor_temp=outdoor_temp,
                slope=curve_params.get("slope", DEFAULT_CURVE_SLOPE),
                base_temp=curve_params.get("base_temp", DEFAULT_CURVE_BASE_TEMP),
                offset=curve_params.get("offset", DEFAULT_CURVE_OFFSET),
                setpoint=curve_params.get("setpoint", DEFAULT_CURVE_SETPOINT),
            )
        elif curve_type == CURVE_TYPE_POINTS:
            points_raw = curve_params.get("points", DEFAULT_CURVE_POINTS)
            
            if isinstance(points_raw, str):
                import json
                try:
                    points_raw = json.loads(points_raw)
                except json.JSONDecodeError:
                    # Try parsing as comma-separated "key:value" string
                    # e.g. "-20:45, 0:30, 20:25"
                    try:
                        points_dict = {}
                        for pair in points_raw.split(','):
                            key, val = pair.split(':')
                            points_dict[float(key.strip())] = float(val.strip())
                        points_raw = points_dict
                    except ValueError:
                        _LOGGER.warning("Failed to parse curve points string: %s", points_raw)
                        return clamp_ch_temp(DEFAULT_CURVE_BASE_TEMP)

            # Ensure keys are floats
            if isinstance(points_raw, dict):
                points = {float(k): float(v) for k, v in points_raw.items()}
                return calculate_point_curve(outdoor_temp, points)
            else:
                _LOGGER.warning("Curve points are not a dictionary: %s", type(points_raw))
                return clamp_ch_temp(DEFAULT_CURVE_BASE_TEMP)
        else:
            _LOGGER.error("Unknown curve type: %s", curve_type)
            return clamp_ch_temp(DEFAULT_CURVE_BASE_TEMP)
    except Exception:
        _LOGGER.exception("Error calculating target temperature")
        return clamp_ch_temp(DEFAULT_CURVE_BASE_TEMP)


def generate_curve_svg(
    curve_type: str,
    curve_params: dict[str, Any],
    width: int = 400,
    height: int = 250,
) -> str:
    """Generate an SVG representation of the heating curve.

    Args:
        curve_type: 'formula' or 'points'
        curve_params: Curve parameters
        width: SVG width in pixels
        height: SVG height in pixels

    Returns:
        SVG string for embedding in HA config flow.
    """
    margin_left = 50
    margin_right = 20
    margin_top = 20
    margin_bottom = 40
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom

    outdoor_min = -25.0
    outdoor_max = 30.0
    water_min = CH_TEMP_MIN
    water_max = CH_TEMP_MAX

    def to_x(outdoor: float) -> float:
        return margin_left + (outdoor - outdoor_min) / (outdoor_max - outdoor_min) * plot_w

    def to_y(water: float) -> float:
        return margin_top + plot_h - (water - water_min) / (water_max - water_min) * plot_h

    # Generate curve points
    steps = 100
    path_points = []
    for i in range(steps + 1):
        outdoor = outdoor_min + (outdoor_max - outdoor_min) * i / steps
        water = calculate_target_temp(outdoor, curve_type, curve_params)
        px = to_x(outdoor)
        py = to_y(water)
        path_points.append(f"{px:.1f},{py:.1f}")

    path_d = "M " + " L ".join(path_points)

    # Grid lines
    grid_lines = []
    # Vertical grid (outdoor temp)
    for t in range(-20, 31, 10):
        x = to_x(t)
        grid_lines.append(
            f'<line x1="{x:.1f}" y1="{margin_top}" '
            f'x2="{x:.1f}" y2="{margin_top + plot_h}" '
            f'stroke="#444" stroke-width="0.5" stroke-dasharray="4,4"/>'
        )
        grid_lines.append(
            f'<text x="{x:.1f}" y="{height - 5}" '
            f'text-anchor="middle" fill="#aaa" font-size="11">{t}°</text>'
        )

    # Horizontal grid (water temp)
    for t in range(int(water_min), int(water_max) + 1, 5):
        y = to_y(t)
        grid_lines.append(
            f'<line x1="{margin_left}" y1="{y:.1f}" '
            f'x2="{margin_left + plot_w}" y2="{y:.1f}" '
            f'stroke="#444" stroke-width="0.5" stroke-dasharray="4,4"/>'
        )
        grid_lines.append(
            f'<text x="{margin_left - 5}" y="{y + 4:.1f}" '
            f'text-anchor="end" fill="#aaa" font-size="11">{t}°</text>'
        )

    grid_str = "\n    ".join(grid_lines)

    # Highlight user-defined points if point-based
    point_markers = ""
    if curve_type == CURVE_TYPE_POINTS:
        points_raw = curve_params.get("points", DEFAULT_CURVE_POINTS)
        points = {float(k): float(v) for k, v in points_raw.items()}
        markers = []
        for outdoor, water in sorted(points.items()):
            clamped = clamp_ch_temp(water)
            cx = to_x(outdoor)
            cy = to_y(clamped)
            markers.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4" '
                f'fill="#ff6b35" stroke="#fff" stroke-width="1.5"/>'
            )
        point_markers = "\n    ".join(markers)

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}"
     width="{width}" height="{height}" style="background:#1a1a2e;border-radius:8px;">
    <!-- Axes -->
    <line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_h}"
          stroke="#666" stroke-width="1.5"/>
    <line x1="{margin_left}" y1="{margin_top + plot_h}" x2="{margin_left + plot_w}" y2="{margin_top + plot_h}"
          stroke="#666" stroke-width="1.5"/>

    <!-- Labels -->
    <text x="{width // 2}" y="{height - 1}" text-anchor="middle" fill="#ccc" font-size="12">
        Outdoor °C
    </text>
    <text x="12" y="{height // 2}" text-anchor="middle" fill="#ccc" font-size="12"
          transform="rotate(-90 12 {height // 2})">
        Water °C
    </text>

    <!-- Grid -->
    {grid_str}

    <!-- Curve -->
    <path d="{path_d}" fill="none" stroke="#4fc3f7" stroke-width="2.5"
          stroke-linecap="round" stroke-linejoin="round"/>

    <!-- Point markers -->
    {point_markers}
</svg>"""

    return svg


def parse_curve_points_string(points_str: str) -> dict[float, float]:
    """Parse user-entered curve points string into dict.

    Expected format: "-20:50, -10:45, 0:38, 10:32, 20:25"

    Returns:
        Dict mapping outdoor temp to water temp.

    Raises:
        ValueError: If the string cannot be parsed.
    """
    points: dict[float, float] = {}
    if not points_str or not points_str.strip():
        return DEFAULT_CURVE_POINTS.copy()

    for pair in points_str.split(","):
        pair = pair.strip()
        if ":" not in pair:
            raise ValueError(f"Invalid point format: '{pair}'. Use 'outdoor:water'.")
        parts = pair.split(":")
        if len(parts) != 2:
            raise ValueError(f"Invalid point format: '{pair}'.")
        outdoor = float(parts[0].strip())
        water = float(parts[1].strip())
        if water < CH_TEMP_MIN or water > CH_TEMP_MAX:
            raise ValueError(
                f"Water temperature {water}°C is outside safe range "
                f"({CH_TEMP_MIN}-{CH_TEMP_MAX}°C)."
            )
        points[outdoor] = water

    if len(points) < 2:
        raise ValueError("At least 2 curve points are required.")

    return points


def format_curve_points_string(points: dict[float, float]) -> str:
    """Format curve points dict to display string."""
    sorted_points = sorted(points.items(), key=lambda x: x[0])
    return ", ".join(
        f"{int(k) if k == int(k) else k}:{int(v) if v == int(v) else v}"
        for k, v in sorted_points
    )
