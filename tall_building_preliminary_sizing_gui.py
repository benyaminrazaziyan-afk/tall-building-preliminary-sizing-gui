
"""
Final preliminary graphical sizing tool
Supports:
- Square plan
- Triangular plan
- Basement retaining perimeter walls
- Distributed perimeter shear walls in upper zones
- Stronger corner columns
- Period from T = 2*pi*sqrt(M/K)

Preliminary sizing only.
"""

from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from dataclasses import dataclass, field
from math import pi, sqrt
from typing import List, Tuple

G = 9.81
STEEL_DENSITY = 7850.0


@dataclass
class ZoneDefinition:
    name: str
    story_start: int
    story_end: int

    @property
    def n_stories(self) -> int:
        return self.story_end - self.story_start + 1


@dataclass
class BuildingInput:
    plan_shape: str
    n_story: int
    n_basement: int
    story_height: float
    basement_height: float
    plan_x: float
    plan_y: float
    n_bays_x: int
    n_bays_y: int
    bay_x: float
    bay_y: float

    stair_count: int = 2
    elevator_count: int = 8
    elevator_area_each: float = 3.5
    stair_area_each: float = 14.0
    service_area: float = 35.0
    corridor_factor: float = 1.40

    fck: float = 60.0
    Ec: float = 36000.0
    fy: float = 420.0

    DL: float = 6.5
    LL: float = 2.5
    slab_finish_allowance: float = 1.5
    facade_line_load: float = 14.0

    prelim_lateral_force_coeff: float = 0.015
    drift_limit_ratio: float = 1 / 500
    target_period_factor: float = 0.95
    max_period_factor_over_target: float = 1.25

    min_wall_thickness: float = 0.30
    max_wall_thickness: float = 1.20
    min_column_dim: float = 0.70
    max_column_dim: float = 1.80
    min_beam_width: float = 0.40
    min_beam_depth: float = 0.75
    min_slab_thickness: float = 0.22
    max_slab_thickness: float = 0.40

    wall_cracked_factor: float = 0.70
    column_cracked_factor: float = 0.70
    max_story_wall_slenderness: float = 12.0

    wall_rebar_ratio: float = 0.003
    column_rebar_ratio: float = 0.010
    beam_rebar_ratio: float = 0.015
    slab_rebar_ratio: float = 0.0035

    seismic_mass_factor: float = 1.0
    effective_modal_mass_ratio: float = 0.80

    Ct: float = 0.0488
    x_period: float = 0.75

    perimeter_column_factor: float = 1.10
    corner_column_factor: float = 1.30

    lower_zone_wall_count: int = 8
    middle_zone_wall_count: int = 6
    upper_zone_wall_count: int = 4

    basement_retaining_wall_thickness: float = 0.50
    perimeter_shear_wall_ratio: float = 0.20  # fraction of side length used by distributed wall segments


@dataclass
class ZoneCoreResult:
    zone: ZoneDefinition
    wall_count: int
    wall_lengths: List[float]
    wall_thickness: float
    core_outer_x: float
    core_outer_y: float
    core_opening_x: float
    core_opening_y: float
    Ieq_gross_m4: float
    Ieq_effective_m4: float
    story_slenderness: float
    perimeter_wall_segments: List[Tuple[str, float, float]]  # side, start, end in local side coordinate
    retaining_wall_active: bool


@dataclass
class ZoneColumnResult:
    zone: ZoneDefinition
    corner_column_m: float
    perimeter_column_m: float
    interior_column_m: float
    corner_column_x_m: float
    corner_column_y_m: float
    perimeter_column_x_m: float
    perimeter_column_y_m: float
    interior_column_x_m: float
    interior_column_y_m: float
    P_corner_kN: float
    P_perimeter_kN: float
    P_interior_kN: float
    I_col_group_effective_m4: float


@dataclass
class ReinforcementEstimate:
    wall_concrete_volume_m3: float
    column_concrete_volume_m3: float
    beam_concrete_volume_m3: float
    slab_concrete_volume_m3: float
    wall_steel_kg: float
    column_steel_kg: float
    beam_steel_kg: float
    slab_steel_kg: float
    total_steel_kg: float


@dataclass
class DesignResult:
    H_m: float
    floor_area_m2: float
    total_weight_kN: float
    effective_modal_mass_kg: float
    T_code_s: float
    T_target_s: float
    T_est_s: float
    K_required_N_per_m: float
    K_core_N_per_m: float
    K_columns_N_per_m: float
    K_estimated_N_per_m: float
    top_drift_m: float
    drift_ratio: float
    zone_core_results: List[ZoneCoreResult]
    zone_column_results: List[ZoneColumnResult]
    slab_thickness_m: float
    beam_width_m: float
    beam_depth_m: float
    reinforcement: ReinforcementEstimate
    system_assessment: str
    messages: List[str] = field(default_factory=list)


def total_height(inp: BuildingInput) -> float:
    return inp.n_story * inp.story_height

def floor_area(inp: BuildingInput) -> float:
    if inp.plan_shape == "triangle":
        return 0.5 * inp.plan_x * inp.plan_y
    return inp.plan_x * inp.plan_y

def slab_thickness_prelim(inp: BuildingInput) -> float:
    span = max(inp.bay_x, inp.bay_y)
    return max(inp.min_slab_thickness, min(inp.max_slab_thickness, span / 28.0))

def beam_size_prelim(inp: BuildingInput):
    span = max(inp.bay_x, inp.bay_y)
    depth = max(inp.min_beam_depth, span / 12.0)
    width = max(inp.min_beam_width, 0.45 * depth)
    return width, depth

def code_type_period(H: float, Ct: float, x_period: float) -> float:
    return Ct * (H ** x_period)

def total_weight_kN(inp: BuildingInput, slab_t: float) -> float:
    A = floor_area(inp)
    perimeter = 2.0 * (inp.plan_x + inp.plan_y) if inp.plan_shape == "square" else (inp.plan_x + inp.plan_y + (inp.plan_x**2 + inp.plan_y**2)**0.5)
    slab_self_weight = slab_t * 25.0
    floor_load = inp.DL + inp.LL + inp.slab_finish_allowance + slab_self_weight
    above_grade = floor_load * A * inp.n_story
    basement = 1.10 * floor_load * A * inp.n_basement
    facade = inp.facade_line_load * perimeter * inp.n_story
    structure_allowance = 0.12 * (above_grade + basement)
    return (above_grade + basement + facade + structure_allowance) * inp.seismic_mass_factor

def effective_modal_mass(total_weight_kN_value: float, ratio: float) -> float:
    return ratio * total_weight_kN_value * 1000.0 / G

def required_stiffness(M_eff: float, T_target: float) -> float:
    return 4.0 * pi**2 * M_eff / (T_target**2)

def preliminary_lateral_force_N(inp: BuildingInput, W_total_kN: float) -> float:
    return inp.prelim_lateral_force_coeff * W_total_kN * 1000.0

def cantilever_tip_stiffness(EI: float, H: float) -> float:
    return 3.0 * EI / (H**3)

def define_three_zones(n_story: int):
    z1 = max(1, round(0.30 * n_story))
    z2 = max(z1 + 1, round(0.70 * n_story))
    return [
        ZoneDefinition("Lower Zone", 1, z1),
        ZoneDefinition("Middle Zone", z1 + 1, z2),
        ZoneDefinition("Upper Zone", z2 + 1, n_story),
    ]

def required_opening_area(inp: BuildingInput) -> float:
    return (inp.elevator_count * inp.elevator_area_each + inp.stair_count * inp.stair_area_each + inp.service_area) * inp.corridor_factor

def opening_dimensions(inp: BuildingInput):
    area = required_opening_area(inp)
    aspect = 1.6
    oy = sqrt(area / aspect)
    return aspect * oy, oy

def initial_core_dimensions(inp: BuildingInput, opening_x: float, opening_y: float):
    outer_x = max(opening_x + 3.0, 0.24 * inp.plan_x)
    outer_y = max(opening_y + 3.0, 0.22 * inp.plan_y)
    return min(outer_x, 0.42 * inp.plan_x), min(outer_y, 0.42 * inp.plan_y)

def active_wall_count_by_zone(inp: BuildingInput, zone_name: str) -> int:
    if zone_name == "Lower Zone":
        return inp.lower_zone_wall_count
    if zone_name == "Middle Zone":
        return inp.middle_zone_wall_count
    return inp.upper_zone_wall_count

def wall_lengths_for_layout(outer_x: float, outer_y: float, wall_count: int):
    if wall_count == 4:
        return [outer_x, outer_x, outer_y, outer_y]
    if wall_count == 6:
        return [outer_x, outer_x, outer_y, outer_y, 0.45 * outer_x, 0.45 * outer_x]
    if wall_count == 8:
        return [outer_x, outer_x, outer_y, outer_y, 0.45 * outer_x, 0.45 * outer_x, 0.45 * outer_y, 0.45 * outer_y]
    raise ValueError("wall_count must be one of 4, 6, 8")

def wall_rect_inertia_about_global_y(length: float, thickness: float, x_centroid: float) -> float:
    I_local = length * thickness**3 / 12.0
    area = length * thickness
    return I_local + area * x_centroid**2

def wall_rect_inertia_about_global_x(length: float, thickness: float, y_centroid: float) -> float:
    I_local = length * thickness**3 / 12.0
    area = length * thickness
    return I_local + area * y_centroid**2

def core_equivalent_inertia(outer_x: float, outer_y: float, lengths: List[float], t: float, wall_count: int) -> float:
    x_side = outer_x / 2.0
    y_side = outer_y / 2.0
    top_len, bot_len, left_len, right_len = lengths[0], lengths[1], lengths[2], lengths[3]
    I_x = 0.0
    I_y = 0.0
    I_x += wall_rect_inertia_about_global_x(top_len, t, +y_side)
    I_x += wall_rect_inertia_about_global_x(bot_len, t, -y_side)
    I_y += (t * top_len**3 / 12.0) + (t * bot_len**3 / 12.0)
    I_y += wall_rect_inertia_about_global_y(left_len, t, -x_side)
    I_y += wall_rect_inertia_about_global_y(right_len, t, +x_side)
    I_x += (t * left_len**3 / 12.0) + (t * right_len**3 / 12.0)
    if wall_count >= 6:
        inner_x = 0.22 * outer_x
        l1, l2 = lengths[4], lengths[5]
        I_y += wall_rect_inertia_about_global_y(l1, t, -inner_x)
        I_y += wall_rect_inertia_about_global_y(l2, t, +inner_x)
        I_x += (t * l1**3 / 12.0) + (t * l2**3 / 12.0)
    if wall_count >= 8:
        inner_y = 0.22 * outer_y
        l3, l4 = lengths[6], lengths[7]
        I_x += wall_rect_inertia_about_global_x(l3, t, -inner_y)
        I_x += wall_rect_inertia_about_global_x(l4, t, +inner_y)
        I_y += (t * l3**3 / 12.0) + (t * l4**3 / 12.0)
    return min(I_x, I_y)

def wall_thickness_by_zone(inp: BuildingInput, H: float, zone: ZoneDefinition) -> float:
    base_t = max(inp.min_wall_thickness, min(inp.max_wall_thickness, H / 180.0))
    if zone.name == "Lower Zone":
        return base_t
    if zone.name == "Middle Zone":
        return max(inp.min_wall_thickness, 0.80 * base_t)
    return max(inp.min_wall_thickness, 0.60 * base_t)

def perimeter_wall_segments_for_square(inp: BuildingInput, zone: ZoneDefinition) -> List[Tuple[str, float, float]]:
    segments = []
    if zone.name == "Lower Zone":
        # retaining wall all around
        segments = [("top", 0.0, inp.plan_x), ("bottom", 0.0, inp.plan_x), ("left", 0.0, inp.plan_y), ("right", 0.0, inp.plan_y)]
    else:
        ratio = inp.perimeter_shear_wall_ratio
        lx = inp.plan_x * ratio
        ly = inp.plan_y * ratio
        sx = (inp.plan_x - lx) / 2.0
        sy = (inp.plan_y - ly) / 2.0
        segments = [("top", sx, sx + lx), ("bottom", sx, sx + lx), ("left", sy, sy + ly), ("right", sy, sy + ly)]
    return segments

def perimeter_wall_segments_for_triangle(inp: BuildingInput, zone: ZoneDefinition) -> List[Tuple[str, float, float]]:
    # symbolic segments on 3 sides
    if zone.name == "Lower Zone":
        return [("edge1", 0.0, 1.0), ("edge2", 0.0, 1.0), ("edge3", 0.0, 1.0)]
    ratio = inp.perimeter_shear_wall_ratio
    s = (1.0 - ratio) / 2.0
    return [("edge1", s, s + ratio), ("edge2", s, s + ratio), ("edge3", s, s + ratio)]

def design_core_by_zone(inp: BuildingInput, zones):
    opening_x, opening_y = opening_dimensions(inp)
    outer_x, outer_y = initial_core_dimensions(inp, opening_x, opening_y)
    H = total_height(inp)
    results = []
    for zone in zones:
        wall_count = active_wall_count_by_zone(inp, zone.name)
        lengths = wall_lengths_for_layout(outer_x, outer_y, wall_count)
        t = wall_thickness_by_zone(inp, H, zone)
        I_gross = core_equivalent_inertia(outer_x, outer_y, lengths, t, wall_count)
        I_eff = inp.wall_cracked_factor * I_gross
        perim = perimeter_wall_segments_for_triangle(inp, zone) if inp.plan_shape == "triangle" else perimeter_wall_segments_for_square(inp, zone)
        results.append(
            ZoneCoreResult(
                zone=zone,
                wall_count=wall_count,
                wall_lengths=lengths,
                wall_thickness=t,
                core_outer_x=outer_x,
                core_outer_y=outer_y,
                core_opening_x=opening_x,
                core_opening_y=opening_y,
                Ieq_gross_m4=I_gross,
                Ieq_effective_m4=I_eff,
                story_slenderness=inp.story_height / t,
                perimeter_wall_segments=perim,
                retaining_wall_active=(zone.name == "Lower Zone"),
            )
        )
    return results


def directional_column_dims(base_dim: float, corner_factor: float, perimeter_factor: float, plan_x: float, plan_y: float, col_type: str):
    """Return directional column dimensions (x, y).
    For rectangular plans, make columns rectangular to help balance directional stiffness.
    Major dimension is placed to improve the weaker plan direction in a simple preliminary way.
    """
    aspect = max(plan_x, plan_y) / max(min(plan_x, plan_y), 1e-9)

    if col_type == "interior":
        nominal = base_dim
    elif col_type == "perimeter":
        nominal = base_dim * perimeter_factor
    else:
        nominal = base_dim * corner_factor

    if aspect <= 1.10:
        d = nominal
        return d, d

    # preliminary anisotropic adjustment
    major = nominal * 1.15
    minor = nominal * 0.90

    # if plan is longer in X, strengthen the Y-direction response by giving columns
    # a larger cross-section dimension parallel to X (larger bending resistance for lateral Y).
    if plan_x >= plan_y:
        return major, minor
    return minor, major


def estimate_zone_column_sizes(inp: BuildingInput, zones, slab_t: float) -> List[ZoneColumnResult]:
    q = inp.DL + inp.LL + inp.slab_finish_allowance + slab_t * 25.0
    sigma_allow = 0.35 * inp.fck * 1000.0
    results = []

    if inp.plan_shape == "triangle":
        total_columns = (inp.n_bays_x + 1) * (inp.n_bays_y + 1) // 2 + 3
        corner_cols = 3
        perimeter_cols = max(6, inp.n_bays_x + inp.n_bays_y)
        interior_cols = max(0, total_columns - corner_cols - perimeter_cols)
        r2_sum = 0.35 * inp.plan_x * inp.plan_y * max(total_columns, 1)
    else:
        total_columns = (inp.n_bays_x + 1) * (inp.n_bays_y + 1)
        corner_cols = 4
        perimeter_cols = max(0, 2 * (inp.n_bays_x - 1) + 2 * (inp.n_bays_y - 1))
        interior_cols = max(0, total_columns - corner_cols - perimeter_cols)
        plan_center_x = inp.plan_x / 2.0
        plan_center_y = inp.plan_y / 2.0
        r2_sum = 0.0
        for i in range(inp.n_bays_x + 1):
            for j in range(inp.n_bays_y + 1):
                x = i * inp.bay_x
                y = j * inp.bay_y
                r2_sum += (x - plan_center_x) ** 2 + (y - plan_center_y) ** 2

    for zone in zones:
        floors_above = inp.n_story - zone.story_start + 1
        n_effective = floors_above + 0.70 * inp.n_basement
        tributary_interior = inp.bay_x * inp.bay_y
        tributary_perimeter = 0.50 * inp.bay_x * inp.bay_y
        tributary_corner = 0.25 * inp.bay_x * inp.bay_y

        P_interior = tributary_interior * q * n_effective * 1.18
        interior_dim = min(inp.max_column_dim, max(inp.min_column_dim, sqrt(P_interior / sigma_allow)))
        perimeter_dim = min(inp.max_column_dim, max(inp.min_column_dim, interior_dim * inp.perimeter_column_factor))
        corner_dim = min(inp.max_column_dim, max(inp.min_column_dim, interior_dim * inp.corner_column_factor))
        P_perimeter = tributary_perimeter * q * n_effective * 1.18
        P_corner = tributary_corner * q * n_effective * 1.18

        interior_x, interior_y = directional_column_dims(interior_dim, inp.corner_column_factor, inp.perimeter_column_factor, inp.plan_x, inp.plan_y, "interior")
        perimeter_x, perimeter_y = directional_column_dims(interior_dim, inp.corner_column_factor, inp.perimeter_column_factor, inp.plan_x, inp.plan_y, "perimeter")
        corner_x, corner_y = directional_column_dims(interior_dim, inp.corner_column_factor, inp.perimeter_column_factor, inp.plan_x, inp.plan_y, "corner")

        A_corner = corner_x * corner_y
        A_perim = perimeter_x * perimeter_y
        A_inter = interior_x * interior_y
        Iavg_corner = max(corner_x * corner_y**3 / 12.0, corner_y * corner_x**3 / 12.0)
        Iavg_perim = max(perimeter_x * perimeter_y**3 / 12.0, perimeter_y * perimeter_x**3 / 12.0)
        Iavg_inter = max(interior_x * interior_y**3 / 12.0, interior_y * interior_x**3 / 12.0)
        I_avg = (corner_cols * Iavg_corner + perimeter_cols * Iavg_perim + interior_cols * Iavg_inter) / max(total_columns, 1)
        A_avg = (corner_cols * A_corner + perimeter_cols * A_perim + interior_cols * A_inter) / max(total_columns, 1)
        I_col_group = inp.column_cracked_factor * (I_avg * max(total_columns, 1) + A_avg * r2_sum)

        results.append(
            ZoneColumnResult(
                zone=zone,
                corner_column_m=corner_dim,
                perimeter_column_m=perimeter_dim,
                interior_column_m=interior_dim,
                corner_column_x_m=corner_x,
                corner_column_y_m=corner_y,
                perimeter_column_x_m=perimeter_x,
                perimeter_column_y_m=perimeter_y,
                interior_column_x_m=interior_x,
                interior_column_y_m=interior_y,
                P_corner_kN=P_corner,
                P_perimeter_kN=P_perimeter,
                P_interior_kN=P_interior,
                I_col_group_effective_m4=I_col_group,
            )
        )
    return results

def weighted_core_stiffness(inp: BuildingInput, zone_cores: List[ZoneCoreResult]) -> float:
    H = total_height(inp)
    E = inp.Ec * 1e6
    total_flex_factor = 0.0
    for zc in zone_cores:
        hi = zc.zone.n_stories * inp.story_height
        # add perimeter wall contribution crudely by increasing effective I
        perimeter_bonus = 1.0 + 0.20 * len(zc.perimeter_wall_segments)
        total_flex_factor += (hi / H) / max(E * zc.Ieq_effective_m4 * perimeter_bonus, 1e-9)
    EI_equiv = 1.0 / max(total_flex_factor, 1e-18)
    return cantilever_tip_stiffness(EI_equiv, H)

def weighted_column_stiffness(inp: BuildingInput, zone_cols: List[ZoneColumnResult]) -> float:
    H = total_height(inp)
    E = inp.Ec * 1e6
    total_flex_factor = 0.0
    for zc in zone_cols:
        hi = zc.zone.n_stories * inp.story_height
        total_flex_factor += (hi / H) / max(E * zc.I_col_group_effective_m4, 1e-9)
    EI_equiv = 1.0 / max(total_flex_factor, 1e-18)
    return cantilever_tip_stiffness(EI_equiv, H)

def estimate_reinforcement(inp: BuildingInput, zone_cores, zone_cols, slab_t, beam_b, beam_h) -> ReinforcementEstimate:
    n_total_levels = inp.n_story + inp.n_basement
    total_floor_area = floor_area(inp) * n_total_levels
    wall_concrete = 0.0
    for zc in zone_cores:
        wall_concrete += sum(zc.wall_lengths) * zc.wall_thickness * (zc.zone.n_stories * inp.story_height)
        # perimeter walls
        if inp.plan_shape == "square":
            side_len = {"top": inp.plan_x, "bottom": inp.plan_x, "left": inp.plan_y, "right": inp.plan_y}
            for side, a, b in zc.perimeter_wall_segments:
                wall_concrete += (b - a) * zc.wall_thickness * (zc.zone.n_stories * inp.story_height)
        else:
            perim_lengths = {"edge1": inp.plan_x, "edge2": inp.plan_y, "edge3": (inp.plan_x**2 + inp.plan_y**2)**0.5}
            for side, a, b in zc.perimeter_wall_segments:
                wall_concrete += perim_lengths[side] * (b - a) * zc.wall_thickness * (zc.zone.n_stories * inp.story_height)

    if inp.plan_shape == "triangle":
        corner_cols = 3
        perimeter_cols = max(6, inp.n_bays_x + inp.n_bays_y)
        total_cols = (inp.n_bays_x + 1) * (inp.n_bays_y + 1) // 2 + 3
        interior_cols = max(0, total_cols - corner_cols - perimeter_cols)
    else:
        corner_cols = 4
        perimeter_cols = max(0, 2 * (inp.n_bays_x - 1) + 2 * (inp.n_bays_y - 1))
        total_cols = (inp.n_bays_x + 1) * (inp.n_bays_y + 1)
        interior_cols = max(0, total_cols - corner_cols - perimeter_cols)

    column_concrete = 0.0
    for zc in zone_cols:
        zone_height = zc.zone.n_stories * inp.story_height
        column_concrete += (
            corner_cols * zc.corner_column_m**2 * zone_height +
            perimeter_cols * zc.perimeter_column_m**2 * zone_height +
            interior_cols * zc.interior_column_m**2 * zone_height
        )

    beam_lines_per_floor = max(1, inp.n_bays_y * (inp.n_bays_x + 1) + inp.n_bays_x * (inp.n_bays_y + 1))
    avg_span = 0.5 * (inp.bay_x + inp.bay_y)
    total_beam_length = beam_lines_per_floor * avg_span * n_total_levels
    beam_concrete = beam_b * beam_h * total_beam_length
    slab_concrete = total_floor_area * slab_t

    wall_steel = wall_concrete * inp.wall_rebar_ratio * STEEL_DENSITY
    column_steel = column_concrete * inp.column_rebar_ratio * STEEL_DENSITY
    beam_steel = beam_concrete * inp.beam_rebar_ratio * STEEL_DENSITY
    slab_steel = slab_concrete * inp.slab_rebar_ratio * STEEL_DENSITY
    total_steel = wall_steel + column_steel + beam_steel + slab_steel

    return ReinforcementEstimate(
        wall_concrete_volume_m3=wall_concrete,
        column_concrete_volume_m3=column_concrete,
        beam_concrete_volume_m3=beam_concrete,
        slab_concrete_volume_m3=slab_concrete,
        wall_steel_kg=wall_steel,
        column_steel_kg=column_steel,
        beam_steel_kg=beam_steel,
        slab_steel_kg=slab_steel,
        total_steel_kg=total_steel,
    )

def run_design(inp: BuildingInput) -> DesignResult:
    H = total_height(inp)
    A = floor_area(inp)
    zones = define_three_zones(inp.n_story)
    slab_t = slab_thickness_prelim(inp)
    beam_b, beam_h = beam_size_prelim(inp)
    W_total = total_weight_kN(inp, slab_t)
    M_eff = effective_modal_mass(W_total, inp.effective_modal_mass_ratio)
    T_code = code_type_period(H, inp.Ct, inp.x_period)
    T_target = inp.target_period_factor * T_code
    K_req = required_stiffness(M_eff, T_target)

    zone_cores = design_core_by_zone(inp, zones)
    zone_cols = estimate_zone_column_sizes(inp, zones, slab_t)

    K_core = weighted_core_stiffness(inp, zone_cores)
    K_cols = weighted_column_stiffness(inp, zone_cols)
    K_est = K_core + K_cols

    T_est = 2.0 * pi * sqrt(M_eff / K_est)
    top_drift = preliminary_lateral_force_N(inp, W_total) / K_est
    drift_ratio = top_drift / H

    reinforcement = estimate_reinforcement(inp, zone_cores, zone_cols, slab_t, beam_b, beam_h)

    messages = []
    ratio = T_est / T_target if T_target > 0 else 0.0
    if ratio > 2.0:
        messages.append(f"Warning: T_est/T_target = {ratio:.2f}. The system is much softer than the target.")
    if K_est < K_req:
        messages.append("Estimated total stiffness is lower than required stiffness from the target period.")
    if drift_ratio > inp.drift_limit_ratio:
        messages.append("Estimated top drift exceeds selected preliminary drift limit.")
    for zc in zone_cores:
        if zc.story_slenderness > inp.max_story_wall_slenderness:
            messages.append(f"{zc.zone.name}: wall slenderness h/t exceeds selected preliminary limit.")
    if inp.plan_shape == "triangle":
        messages.append("Triangular plan selected: three strong corner columns are emphasized.")
    else:
        messages.append("Square plan selected: four strong corner columns are emphasized.")
    messages.append("Lower zone includes perimeter retaining walls.")
    messages.append("Upper zones include distributed perimeter shear wall segments in addition to the central core.")
    messages.append("Period is computed from T = 2π√(M/K_total).")
    if abs(inp.plan_x - inp.plan_y) > 1e-6:
        messages.append("Rectangular plan detected: directional column dimensions are adjusted in the calculations and the plan view now draws the same rectangular column shapes.")

    assessment = "System appears preliminarily adequate." if (K_est >= K_req and drift_ratio <= inp.drift_limit_ratio and T_est <= inp.max_period_factor_over_target * T_target) else "System appears preliminarily too flexible; enlarge walls/columns or refine the stiffness model."

    return DesignResult(
        H_m=H, floor_area_m2=A, total_weight_kN=W_total, effective_modal_mass_kg=M_eff,
        T_code_s=T_code, T_target_s=T_target, T_est_s=T_est,
        K_required_N_per_m=K_req, K_core_N_per_m=K_core, K_columns_N_per_m=K_cols, K_estimated_N_per_m=K_est,
        top_drift_m=top_drift, drift_ratio=drift_ratio,
        zone_core_results=zone_cores, zone_column_results=zone_cols,
        slab_thickness_m=slab_t, beam_width_m=beam_b, beam_depth_m=beam_h,
        reinforcement=reinforcement, system_assessment=assessment, messages=messages
    )

def build_report(result: DesignResult) -> str:
    lines = []
    lines.append("GLOBAL RESPONSE")
    lines.append("-" * 74)
    lines.append(f"Estimated period from M/K      = {result.T_est_s:.3f} s")
    lines.append(f"Target period                  = {result.T_target_s:.3f} s")
    lines.append(f"Required stiffness             = {result.K_required_N_per_m:,.3e} N/m")
    lines.append(f"Core stiffness                 = {result.K_core_N_per_m:,.3e} N/m")
    lines.append(f"Column stiffness contribution  = {result.K_columns_N_per_m:,.3e} N/m")
    lines.append(f"Total estimated stiffness      = {result.K_estimated_N_per_m:,.3e} N/m")
    lines.append(f"Estimated top drift            = {result.top_drift_m:.3f} m")
    lines.append(f"Total structural weight       = {result.total_weight_kN:,.0f} kN")
    lines.append(f"Effective modal mass          = {result.effective_modal_mass_kg:,.0f} kg")
    lines.append(f"Estimated drift ratio          = {result.drift_ratio:.5f}")
    lines.append(f"Beam size (b x h)             = {result.beam_width_m:.2f} x {result.beam_depth_m:.2f} m")
    lines.append(f"Slab thickness                = {result.slab_thickness_m:.2f} m")
    lines.append("")
    lines.append("SYSTEM ASSESSMENT")
    lines.append("-" * 74)
    lines.append(result.system_assessment)
    lines.append("")
    lines.append("ZONE-BY-ZONE COLUMN DIMENSIONS")
    lines.append("-" * 74)
    for zc in result.zone_column_results:
        lines.append(f"{zc.zone.name}:")
        lines.append(f"  Corner columns   = {zc.corner_column_x_m:.2f} x {zc.corner_column_y_m:.2f} m")
        lines.append(f"  Perimeter cols   = {zc.perimeter_column_x_m:.2f} x {zc.perimeter_column_y_m:.2f} m")
        lines.append(f"  Interior cols    = {zc.interior_column_x_m:.2f} x {zc.interior_column_y_m:.2f} m")
        lines.append(f"  Column group Ieff= {zc.I_col_group_effective_m4:,.2f} m^4")
    lines.append("")
    lines.append("ZONE-BY-ZONE CORE / WALLS")
    lines.append("-" * 74)
    for zc in result.zone_core_results:
        lines.append(f"{zc.zone.name}:")
        lines.append(f"  Core outer       = {zc.core_outer_x:.2f} x {zc.core_outer_y:.2f} m")
        lines.append(f"  Core opening     = {zc.core_opening_x:.2f} x {zc.core_opening_y:.2f} m")
        lines.append(f"  Wall thickness   = {zc.wall_thickness:.2f} m")
        lines.append(f"  Active core walls= {zc.wall_count}")
        lines.append(f"  Gross Ieq        = {zc.Ieq_gross_m4:,.2f} m^4")
        lines.append(f"  Effective Ieq    = {zc.Ieq_effective_m4:,.2f} m^4")
        lines.append(f"  Story slenderness= {zc.story_slenderness:.2f}")
    lines.append("")
    lines.append("MESSAGES")
    lines.append("-" * 74)
    for m in result.messages:
        lines.append(f"- {m}")
    return "\n".join(lines)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Final Tall Building Plan Output Tool")
        self.geometry("1420x900")
        self.fields = {}
        self.latest_report = ""
        self.latest_result = None
        self._build_ui()

    def _add_entry(self, parent, row, label, key, default):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=3)
        var = tk.StringVar(value=str(default))
        ttk.Entry(parent, textvariable=var, width=14).grid(row=row, column=1, sticky="w", padx=6, pady=3)
        self.fields[key] = var

    def _build_ui(self):
        main = ttk.Panedwindow(self, orient="horizontal")
        main.pack(fill="both", expand=True, padx=8, pady=8)

        left = ttk.Frame(main)
        right = ttk.Frame(main)
        main.add(left, weight=1)
        main.add(right, weight=2)

        host = tk.Canvas(left)
        host.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(left, orient="vertical", command=host.yview)
        scroll.pack(side="right", fill="y")
        host.configure(yscrollcommand=scroll.set)
        form = ttk.Frame(host)
        host.create_window((0, 0), window=form, anchor="nw")
        form.bind("<Configure>", lambda e: host.configure(scrollregion=host.bbox("all")))

        shape_frame = ttk.LabelFrame(form, text="Plan Shape")
        shape_frame.pack(fill="x", padx=6, pady=6)
        self.shape_var = tk.StringVar(value="square")
        ttk.Radiobutton(shape_frame, text="Square", variable=self.shape_var, value="square").pack(side="left", padx=8, pady=6)
        ttk.Radiobutton(shape_frame, text="Triangular", variable=self.shape_var, value="triangle").pack(side="left", padx=8, pady=6)

        frames = [
            ttk.LabelFrame(form, text="Geometry"),
            ttk.LabelFrame(form, text="Loads/Materials"),
            ttk.LabelFrame(form, text="Controls/Final Options"),
        ]
        for frm in frames:
            frm.pack(fill="x", padx=6, pady=6)

        for i, (lbl, key, d) in enumerate([
            ("Above-grade stories", "n_story", 50),
            ("Basement stories", "n_basement", 10),
            ("Story height (m)", "story_height", 3.4),
            ("Basement height (m)", "basement_height", 3.5),
            ("Plan X (m)", "plan_x", 80.0),
            ("Plan Y (m)", "plan_y", 80.0),
            ("Bays in X", "n_bays_x", 8),
            ("Bays in Y", "n_bays_y", 8),
            ("Bay X (m)", "bay_x", 10.0),
            ("Bay Y (m)", "bay_y", 10.0),
            ("Stairs", "stair_count", 2),
            ("Elevators", "elevator_count", 8),
        ]):
            self._add_entry(frames[0], i, lbl, key, d)

        for i, (lbl, key, d) in enumerate([
            ("Elevator area each (m²)", "elevator_area_each", 3.5),
            ("Stair area each (m²)", "stair_area_each", 14.0),
            ("Service area (m²)", "service_area", 35.0),
            ("Core circulation factor", "corridor_factor", 1.40),
            ("fck (MPa)", "fck", 60.0),
            ("Ec (MPa)", "Ec", 36000.0),
            ("fy (MPa)", "fy", 420.0),
            ("DL (kN/m²)", "DL", 6.5),
            ("LL (kN/m²)", "LL", 2.5),
            ("Slab/fit-out allowance", "slab_finish_allowance", 1.5),
            ("Facade line load (kN/m)", "facade_line_load", 14.0),
            ("Wall cracked factor", "wall_cracked_factor", 0.70),
            ("Column cracked factor", "column_cracked_factor", 0.70),
            ("Basement retaining wall t (m)", "basement_retaining_wall_thickness", 0.50),
        ]):
            self._add_entry(frames[1], i, lbl, key, d)

        for i, (lbl, key, d) in enumerate([
            ("Prelim lateral coeff", "prelim_lateral_force_coeff", 0.015),
            ("Drift denominator", "drift_denominator", 500.0),
            ("Target period factor", "target_period_factor", 0.95),
            ("Max period/target", "max_period_factor_over_target", 1.25),
            ("Min wall thickness (m)", "min_wall_thickness", 0.30),
            ("Max wall thickness (m)", "max_wall_thickness", 1.20),
            ("Min column dimension (m)", "min_column_dim", 0.70),
            ("Max column dimension (m)", "max_column_dim", 1.80),
            ("Min beam width (m)", "min_beam_width", 0.40),
            ("Min beam depth (m)", "min_beam_depth", 0.75),
            ("Min slab thickness (m)", "min_slab_thickness", 0.22),
            ("Max slab thickness (m)", "max_slab_thickness", 0.40),
            ("Max wall slenderness", "max_story_wall_slenderness", 12.0),
            ("Perimeter column factor", "perimeter_column_factor", 1.10),
            ("Corner column factor", "corner_column_factor", 1.30),
            ("Lower zone wall count", "lower_zone_wall_count", 8),
            ("Middle zone wall count", "middle_zone_wall_count", 6),
            ("Upper zone wall count", "upper_zone_wall_count", 4),
            ("Perimeter shear wall ratio", "perimeter_shear_wall_ratio", 0.20),
            ("Wall rebar ratio", "wall_rebar_ratio", 0.003),
            ("Column rebar ratio", "column_rebar_ratio", 0.010),
            ("Beam rebar ratio", "beam_rebar_ratio", 0.015),
            ("Slab rebar ratio", "slab_rebar_ratio", 0.0035),
            ("Seismic mass factor", "seismic_mass_factor", 1.0),
            ("Effective modal mass ratio", "effective_modal_mass_ratio", 0.80),
            ("Ct", "Ct", 0.0488),
            ("x exponent", "x_period", 0.75),
        ]):
            self._add_entry(frames[2], i, lbl, key, d)

        btn_bar = ttk.Frame(form)
        btn_bar.pack(fill="x", padx=6, pady=10)
        tk.Button(btn_bar, text="ANALYZE", command=self.run_design_action, bg="#0b5ed7", fg="white", font=("Arial", 12, "bold"), padx=18, pady=8).pack(side="left", padx=6)
        tk.Button(btn_bar, text="SAVE REPORT", command=self.save_report_action, bg="#198754", fg="white", font=("Arial", 11, "bold"), padx=14, pady=8).pack(side="left", padx=6)

        top_controls = ttk.Frame(right)
        top_controls.pack(fill="x", padx=6, pady=4)
        ttk.Label(top_controls, text="Displayed zone:").pack(side="left")
        self.zone_var = tk.StringVar(value="Lower Zone")
        box = ttk.Combobox(top_controls, textvariable=self.zone_var, values=["Lower Zone", "Middle Zone", "Upper Zone"], state="readonly", width=16)
        box.pack(side="left", padx=6)
        box.bind("<<ComboboxSelected>>", lambda e: self.redraw_plan())

        self.canvas = tk.Canvas(right, bg="white", height=560)
        self.canvas.pack(fill="both", expand=False, padx=6, pady=6)

        self.result_text = tk.Text(right, wrap="word", font=("Consolas", 10), height=16)
        self.result_text.pack(fill="both", expand=True, padx=6, pady=6)

    def _get_input(self) -> BuildingInput:
        f = self.fields
        return BuildingInput(
            plan_shape=self.shape_var.get(),
            n_story=int(f["n_story"].get()),
            n_basement=int(f["n_basement"].get()),
            story_height=float(f["story_height"].get()),
            basement_height=float(f["basement_height"].get()),
            plan_x=float(f["plan_x"].get()),
            plan_y=float(f["plan_y"].get()),
            n_bays_x=int(f["n_bays_x"].get()),
            n_bays_y=int(f["n_bays_y"].get()),
            bay_x=float(f["bay_x"].get()),
            bay_y=float(f["bay_y"].get()),
            stair_count=int(f["stair_count"].get()),
            elevator_count=int(f["elevator_count"].get()),
            elevator_area_each=float(f["elevator_area_each"].get()),
            stair_area_each=float(f["stair_area_each"].get()),
            service_area=float(f["service_area"].get()),
            corridor_factor=float(f["corridor_factor"].get()),
            fck=float(f["fck"].get()),
            Ec=float(f["Ec"].get()),
            fy=float(f["fy"].get()),
            DL=float(f["DL"].get()),
            LL=float(f["LL"].get()),
            slab_finish_allowance=float(f["slab_finish_allowance"].get()),
            facade_line_load=float(f["facade_line_load"].get()),
            prelim_lateral_force_coeff=float(f["prelim_lateral_force_coeff"].get()),
            drift_limit_ratio=1.0 / float(f["drift_denominator"].get()),
            target_period_factor=float(f["target_period_factor"].get()),
            max_period_factor_over_target=float(f["max_period_factor_over_target"].get()),
            min_wall_thickness=float(f["min_wall_thickness"].get()),
            max_wall_thickness=float(f["max_wall_thickness"].get()),
            min_column_dim=float(f["min_column_dim"].get()),
            max_column_dim=float(f["max_column_dim"].get()),
            min_beam_width=float(f["min_beam_width"].get()),
            min_beam_depth=float(f["min_beam_depth"].get()),
            min_slab_thickness=float(f["min_slab_thickness"].get()),
            max_slab_thickness=float(f["max_slab_thickness"].get()),
            wall_cracked_factor=float(f["wall_cracked_factor"].get()),
            column_cracked_factor=float(f["column_cracked_factor"].get()),
            max_story_wall_slenderness=float(f["max_story_wall_slenderness"].get()),
            wall_rebar_ratio=float(f["wall_rebar_ratio"].get()),
            column_rebar_ratio=float(f["column_rebar_ratio"].get()),
            beam_rebar_ratio=float(f["beam_rebar_ratio"].get()),
            slab_rebar_ratio=float(f["slab_rebar_ratio"].get()),
            seismic_mass_factor=float(f["seismic_mass_factor"].get()),
            effective_modal_mass_ratio=float(f["effective_modal_mass_ratio"].get()),
            Ct=float(f["Ct"].get()),
            x_period=float(f["x_period"].get()),
            perimeter_column_factor=float(f["perimeter_column_factor"].get()),
            corner_column_factor=float(f["corner_column_factor"].get()),
            lower_zone_wall_count=int(f["lower_zone_wall_count"].get()),
            middle_zone_wall_count=int(f["middle_zone_wall_count"].get()),
            upper_zone_wall_count=int(f["upper_zone_wall_count"].get()),
            basement_retaining_wall_thickness=float(f["basement_retaining_wall_thickness"].get()),
            perimeter_shear_wall_ratio=float(f["perimeter_shear_wall_ratio"].get()),
        )

    def run_design_action(self):
        try:
            inp = self._get_input()
            self.latest_result = run_design(inp)
            self.latest_report = build_report(self.latest_result)
            self.result_text.delete("1.0", tk.END)
            self.result_text.insert(tk.END, self.latest_report)
            self.redraw_plan()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def save_report_action(self):
        if not self.latest_report:
            messagebox.showinfo("Info", "Run the analysis first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files", "*.txt")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.latest_report)
            messagebox.showinfo("Saved", f"Report saved to:\n{path}")

    def _transform_square(self, x, y, inp, cw, ch, margin):
        scale = min((cw - 2 * margin) / inp.plan_x, (ch - 2 * margin) / inp.plan_y)
        ox = (cw - inp.plan_x * scale) / 2
        oy = (ch - inp.plan_y * scale) / 2
        return ox + x * scale, oy + y * scale, scale, ox, oy

    def _triangle_points(self, inp):
        # right triangle
        return [(0, inp.plan_y), (inp.plan_x/2, 0), (inp.plan_x, inp.plan_y)]

    def _transform_triangle(self, x, y, inp, cw, ch, margin):
        scale = min((cw - 2 * margin) / inp.plan_x, (ch - 2 * margin) / inp.plan_y)
        ox = (cw - inp.plan_x * scale) / 2
        oy = (ch - inp.plan_y * scale) / 2
        return ox + x * scale, oy + y * scale, scale, ox, oy

    def redraw_plan(self):
        self.canvas.delete("all")
        if self.latest_result is None:
            self.canvas.create_text(260, 90, text="Click ANALYZE to display the plan.", font=("Arial", 14))
            return

        zone_name = self.zone_var.get()
        core = next(z for z in self.latest_result.zone_core_results if z.zone.name == zone_name)
        cols = next(z for z in self.latest_result.zone_column_results if z.zone.name == zone_name)
        inp = self._get_input()

        self.canvas.update_idletasks()
        cw = max(950, int(self.canvas.winfo_width()))
        ch = max(560, int(self.canvas.winfo_height()))
        margin = 70

        if inp.plan_shape == "triangle":
            self._draw_triangle_plan(inp, core, cols, cw, ch, margin)
        else:
            self._draw_square_plan(inp, core, cols, cw, ch, margin)

    def _draw_square_plan(self, inp, core, cols, cw, ch, margin):
        def tf(x, y):
            X, Y, scale, ox, oy = self._transform_square(x, y, inp, cw, ch, margin)
            return X, Y, scale

        x0, y0, scale = tf(0, 0)
        x1, y1, _ = tf(inp.plan_x, inp.plan_y)
        self.canvas.create_rectangle(x0, y0, x1, y1, width=2)
        self.canvas.create_text((x0+x1)/2, y0-20, text=f"{core.zone.name} - Square plan", font=("Arial", 12, "bold"))

        # grid
        for i in range(inp.n_bays_x + 1):
            gx = i * inp.bay_x
            X, Y, _ = tf(gx, 0)
            _, Y2, _ = tf(gx, inp.plan_y)
            self.canvas.create_line(X, Y, X, Y2, fill="#d9d9d9")
        for j in range(inp.n_bays_y + 1):
            gy = j * inp.bay_y
            X, Y, _ = tf(0, gy)
            X2, _, _ = tf(inp.plan_x, gy)
            self.canvas.create_line(X, Y, X2, Y, fill="#d9d9d9")

        # columns: draw with the same directional dimensions used in calculations
        for i in range(inp.n_bays_x + 1):
            for j in range(inp.n_bays_y + 1):
                px = i * inp.bay_x
                py = j * inp.bay_y
                at_lr = i == 0 or i == inp.n_bays_x
                at_bt = j == 0 or j == inp.n_bays_y
                if at_lr and at_bt:
                    dx = cols.corner_column_x_m
                    dy = cols.corner_column_y_m
                    color = "#8b0000"
                elif at_lr or at_bt:
                    dx = cols.perimeter_column_x_m
                    dy = cols.perimeter_column_y_m
                    color = "#cc5500"
                else:
                    dx = cols.interior_column_x_m
                    dy = cols.interior_column_y_m
                    color = "#4444aa"
                X, Y, _ = tf(px, py)
                half_x = (dx * scale) / 2
                half_y = (dy * scale) / 2
                self.canvas.create_rectangle(X-half_x, Y-half_y, X+half_x, Y+half_y, fill=color, outline="")

        # core
        cx0 = (inp.plan_x - core.core_outer_x) / 2
        cy0 = (inp.plan_y - core.core_outer_y) / 2
        cx1 = cx0 + core.core_outer_x
        cy1 = cy0 + core.core_outer_y
        ix0 = (inp.plan_x - core.core_opening_x) / 2
        iy0 = (inp.plan_y - core.core_opening_y) / 2
        ix1 = ix0 + core.core_opening_x
        iy1 = iy0 + core.core_opening_y
        wall_color = "#2e8b57"
        t = core.wall_thickness

        X0, Y0, _ = tf(cx0, cy0)
        X1, Y1, _ = tf(cx1, cy1)
        self.canvas.create_rectangle(X0, Y0, X1, Y1, outline="black", width=2)
        IX0, IY0, _ = tf(ix0, iy0)
        IX1, IY1, _ = tf(ix1, iy1)
        self.canvas.create_rectangle(IX0, IY0, IX1, IY1, outline="#666666", dash=(4, 2))

        # core walls
        xa, ya, _ = tf(cx0, cy0)
        xb, yb, _ = tf(cx1, cy0 + t)
        self.canvas.create_rectangle(xa, ya, xb, yb, fill=wall_color, outline="")
        xa, ya, _ = tf(cx0, cy1 - t)
        xb, yb, _ = tf(cx1, cy1)
        self.canvas.create_rectangle(xa, ya, xb, yb, fill=wall_color, outline="")
        xa, ya, _ = tf(cx0, cy0)
        xb, yb, _ = tf(cx0 + t, cy1)
        self.canvas.create_rectangle(xa, ya, xb, yb, fill=wall_color, outline="")
        xa, ya, _ = tf(cx1 - t, cy0)
        xb, yb, _ = tf(cx1, cy1)
        self.canvas.create_rectangle(xa, ya, xb, yb, fill=wall_color, outline="")

        # internal core walls
        if core.wall_count >= 6:
            inner_x1 = (inp.plan_x / 2) - 0.22 * core.core_outer_x
            inner_x2 = (inp.plan_x / 2) + 0.22 * core.core_outer_x - t
            wlen = 0.45 * core.core_outer_x
            ymid0 = (inp.plan_y - wlen) / 2
            ymid1 = ymid0 + wlen
            xa, ya, _ = tf(inner_x1, ymid0)
            xb, yb, _ = tf(inner_x1 + t, ymid1)
            self.canvas.create_rectangle(xa, ya, xb, yb, fill=wall_color, outline="")
            xa, ya, _ = tf(inner_x2, ymid0)
            xb, yb, _ = tf(inner_x2 + t, ymid1)
            self.canvas.create_rectangle(xa, ya, xb, yb, fill=wall_color, outline="")
        if core.wall_count >= 8:
            inner_y1 = (inp.plan_y / 2) - 0.22 * core.core_outer_y
            inner_y2 = (inp.plan_y / 2) + 0.22 * core.core_outer_y - t
            wlen = 0.45 * core.core_outer_y
            xmid0 = (inp.plan_x - wlen) / 2
            xmid1 = xmid0 + wlen
            xa, ya, _ = tf(xmid0, inner_y1)
            xb, yb, _ = tf(xmid1, inner_y1 + t)
            self.canvas.create_rectangle(xa, ya, xb, yb, fill=wall_color, outline="")
            xa, ya, _ = tf(xmid0, inner_y2)
            xb, yb, _ = tf(xmid1, inner_y2 + t)
            self.canvas.create_rectangle(xa, ya, xb, yb, fill=wall_color, outline="")

        # perimeter walls
        perim_color = "#4caf50"
        thickness = inp.basement_retaining_wall_thickness if core.retaining_wall_active else core.wall_thickness
        for side, a, b in core.perimeter_wall_segments:
            if side == "top":
                xa, ya, _ = tf(a, 0)
                xb, yb, _ = tf(b, thickness)
            elif side == "bottom":
                xa, ya, _ = tf(a, inp.plan_y - thickness)
                xb, yb, _ = tf(b, inp.plan_y)
            elif side == "left":
                xa, ya, _ = tf(0, a)
                xb, yb, _ = tf(thickness, b)
            else:
                xa, ya, _ = tf(inp.plan_x - thickness, a)
                xb, yb, _ = tf(inp.plan_x, b)
            self.canvas.create_rectangle(xa, ya, xb, yb, fill=perim_color, outline="")

        self._draw_common_annotations(inp, core, cols, scale, x1, y0, x0, y1)

    def _draw_triangle_plan(self, inp, core, cols, cw, ch, margin):
        pts = self._triangle_points(inp)

        def tf(x, y):
            X, Y, scale, ox, oy = self._transform_triangle(x, y, inp, cw, ch, margin)
            return X, Y, scale

        tpts = [tf(x, y)[:2] for x, y in pts]
        self.canvas.create_polygon(*sum(([x, y] for x, y in tpts), []), outline="black", fill="", width=2)
        self.canvas.create_text(sum(x for x, _ in tpts)/3, min(y for _, y in tpts)-20, text=f"{core.zone.name} - Triangular plan", font=("Arial", 12, "bold"))

        # three strong corners: use calculated rectangular dimensions
        for (x, y) in pts:
            X, Y, scale = tf(x, y)
            half_x = (cols.corner_column_x_m * scale) / 2
            half_y = (cols.corner_column_y_m * scale) / 2
            self.canvas.create_rectangle(X-half_x, Y-half_y, X+half_x, Y+half_y, fill="#8b0000", outline="")

        # some side/interior nodes
        # base edge
        for i in range(1, inp.n_bays_x):
            x = inp.plan_x * i / inp.n_bays_x
            y = inp.plan_y
            X, Y, scale = tf(x, y)
            half_x = (cols.perimeter_column_x_m * scale) / 2
            half_y = (cols.perimeter_column_y_m * scale) / 2
            self.canvas.create_rectangle(X-half_x, Y-half_y, X+half_x, Y+half_y, fill="#cc5500", outline="")
        # left slope
        for i in range(1, inp.n_bays_y):
            x = (inp.plan_x/2) * (1 - i/inp.n_bays_y)
            y = inp.plan_y * (i/inp.n_bays_y)
            X, Y, scale = tf(x, y)
            half_x = (cols.perimeter_column_x_m * scale) / 2
            half_y = (cols.perimeter_column_y_m * scale) / 2
            self.canvas.create_rectangle(X-half_x, Y-half_y, X+half_x, Y+half_y, fill="#cc5500", outline="")
        # right slope
        for i in range(1, inp.n_bays_y):
            x = inp.plan_x/2 + (inp.plan_x/2) * (i/inp.n_bays_y)
            y = inp.plan_y * (i/inp.n_bays_y)
            X, Y, scale = tf(x, y)
            half_x = (cols.perimeter_column_x_m * scale) / 2
            half_y = (cols.perimeter_column_y_m * scale) / 2
            self.canvas.create_rectangle(X-half_x, Y-half_y, X+half_x, Y+half_y, fill="#cc5500", outline="")
        # one central interior
        X, Y, scale = tf(inp.plan_x/2, 0.65*inp.plan_y)
        half_x = (cols.interior_column_x_m * scale) / 2
        half_y = (cols.interior_column_y_m * scale) / 2
        self.canvas.create_rectangle(X-half_x, Y-half_y, X+half_x, Y+half_y, fill="#4444aa", outline="")

        # draw simplified core as rectangle centered in triangle envelope
        cx0 = (inp.plan_x - core.core_outer_x) / 2
        cy0 = inp.plan_y * 0.42
        cx1 = cx0 + core.core_outer_x
        cy1 = cy0 + core.core_outer_y
        ix0 = (inp.plan_x - core.core_opening_x) / 2
        iy0 = cy0 + (core.core_outer_y - core.core_opening_y) / 2
        ix1 = ix0 + core.core_opening_x
        iy1 = iy0 + core.core_opening_y
        wall_color = "#2e8b57"
        t = core.wall_thickness

        X0, Y0, _ = tf(cx0, cy0)
        X1, Y1, _ = tf(cx1, cy1)
        self.canvas.create_rectangle(X0, Y0, X1, Y1, outline="black", width=2)
        IX0, IY0, _ = tf(ix0, iy0)
        IX1, IY1, _ = tf(ix1, iy1)
        self.canvas.create_rectangle(IX0, IY0, IX1, IY1, outline="#666666", dash=(4, 2))

        xa, ya, _ = tf(cx0, cy0)
        xb, yb, _ = tf(cx1, cy0+t)
        self.canvas.create_rectangle(xa, ya, xb, yb, fill=wall_color, outline="")
        xa, ya, _ = tf(cx0, cy1-t)
        xb, yb, _ = tf(cx1, cy1)
        self.canvas.create_rectangle(xa, ya, xb, yb, fill=wall_color, outline="")
        xa, ya, _ = tf(cx0, cy0)
        xb, yb, _ = tf(cx0+t, cy1)
        self.canvas.create_rectangle(xa, ya, xb, yb, fill=wall_color, outline="")
        xa, ya, _ = tf(cx1-t, cy0)
        xb, yb, _ = tf(cx1, cy1)
        self.canvas.create_rectangle(xa, ya, xb, yb, fill=wall_color, outline="")

        # perimeter walls on edges
        edge_pts = [(pts[0], pts[1]), (pts[1], pts[2]), (pts[2], pts[0])]
        perim_color = "#4caf50"
        thickness = inp.basement_retaining_wall_thickness if core.retaining_wall_active else core.wall_thickness
        for idx, ((x0, y0), (x1, y1)) in enumerate(edge_pts):
            side_name = f"edge{idx+1}"
            seg = next((s for s in core.perimeter_wall_segments if s[0] == side_name), None)
            if seg is None:
                continue
            _, a, b = seg
            xa = x0 + (x1 - x0) * a
            ya = y0 + (y1 - y0) * a
            xb = x0 + (x1 - x0) * b
            yb = y0 + (y1 - y0) * b
            XA, YA, sc = tf(xa, ya)
            XB, YB, _ = tf(xb, yb)
            self.canvas.create_line(XA, YA, XB, YB, fill=perim_color, width=max(2, int(thickness * sc)))

        # annotations
        Xr = max(x for x, _ in tpts)
        Yr = min(y for _, y in tpts)
        for i, txt in enumerate([
            f"Core {core.core_outer_x:.2f} x {core.core_outer_y:.2f} m",
            f"Wall t = {core.wall_thickness:.2f} m",
            f"Corner col = {cols.corner_column_x_m:.2f} x {cols.corner_column_y_m:.2f} m",
            f"Perim col = {cols.perimeter_column_x_m:.2f} x {cols.perimeter_column_y_m:.2f} m",
            f"Interior col = {cols.interior_column_x_m:.2f} x {cols.interior_column_y_m:.2f} m",
            f"Beam = {self.latest_result.beam_width_m:.2f} x {self.latest_result.beam_depth_m:.2f} m",
            f"Slab t = {self.latest_result.slab_thickness_m:.2f} m",
        ]):
            self.canvas.create_text(Xr+40, Yr+20+i*18, text=txt, anchor="w")

        self._draw_legend(min(x for x, _ in tpts)+20, max(y for _, y in tpts)-90)

    def _draw_common_annotations(self, inp, core, cols, scale, x1, y0, x0, y1):
        self.canvas.create_line(x0, y1+20, x1, y1+20, arrow=tk.BOTH)
        self.canvas.create_text((x0+x1)/2, y1+35, text=f"Plan X = {inp.plan_x:.2f} m")
        self.canvas.create_line(x1+20, y0, x1+20, y1, arrow=tk.BOTH)
        self.canvas.create_text(x1+55, (y0+y1)/2, text=f"Plan Y = {inp.plan_y:.2f} m", angle=90)

        info_x = x1 + 70
        info_y = y0 + 10
        for i, txt in enumerate([
            f"Core {core.core_outer_x:.2f} x {core.core_outer_y:.2f} m",
            f"Wall t = {core.wall_thickness:.2f} m",
            f"Corner col = {cols.corner_column_x_m:.2f} x {cols.corner_column_y_m:.2f} m",
            f"Perim col = {cols.perimeter_column_x_m:.2f} x {cols.perimeter_column_y_m:.2f} m",
            f"Interior col = {cols.interior_column_x_m:.2f} x {cols.interior_column_y_m:.2f} m",
            f"Beam = {self.latest_result.beam_width_m:.2f} x {self.latest_result.beam_depth_m:.2f} m",
            f"Slab t = {self.latest_result.slab_thickness_m:.2f} m",
            f"Ieff = {core.Ieq_effective_m4:.1f} m^4",
        ]):
            self.canvas.create_text(info_x, info_y + i*18, text=txt, anchor="w")

        self._draw_legend(x0+15, y1-90)

    def _draw_legend(self, x, y):
        self.canvas.create_rectangle(x, y, x+20, y+20, fill="#8b0000", outline="")
        self.canvas.create_text(x+30, y+10, text="Strong corner column", anchor="w")
        self.canvas.create_rectangle(x, y+25, x+20, y+45, fill="#cc5500", outline="")
        self.canvas.create_text(x+30, y+35, text="Perimeter column", anchor="w")
        self.canvas.create_rectangle(x, y+50, x+20, y+70, fill="#4444aa", outline="")
        self.canvas.create_text(x+30, y+60, text="Interior column", anchor="w")
        self.canvas.create_rectangle(x+180, y, x+200, y+20, fill="#2e8b57", outline="")
        self.canvas.create_text(x+210, y+10, text="Core shear wall", anchor="w")
        self.canvas.create_rectangle(x+180, y+25, x+200, y+45, fill="#4caf50", outline="")
        self.canvas.create_text(x+210, y+35, text="Perimeter wall / retaining wall", anchor="w")


if __name__ == "__main__":
    app = App()
    app.mainloop()
