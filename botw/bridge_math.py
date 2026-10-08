"""Coordinate transforms for the future Ryujinx guest-state adapter.

No BOTW memory layout or in-game scale is assumed here. Calibrate the
basis and origin from measurements for the *specific* BOTW build.
Pure Python 3.10+, no emulator dependency.
"""
from dataclasses import dataclass
from math import isfinite, sqrt


@dataclass(frozen=True)
class Vector3:
    x: float
    y: float
    z: float

    def __add__(self, other: "Vector3") -> "Vector3":
        return Vector3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vector3") -> "Vector3":
        return Vector3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, factor: float) -> "Vector3":
        return Vector3(self.x * factor, self.y * factor, self.z * factor)


def dot(a: Vector3, b: Vector3) -> float:
    return a.x*b.x + a.y*b.y + a.z*b.z


@dataclass(frozen=True)
class CoordinateMap:
    """BOTW guest units -> MC blocks.

    basis_* specify Minecraft +X/+Y/+Z in BOTW coordinates.
    A valid basis is orthonormal (supports axis swaps and reflection).
    """
    botw_origin: Vector3
    minecraft_origin: Vector3
    units_per_block: float
    basis_x: Vector3
    basis_y: Vector3
    basis_z: Vector3

    def __post_init__(self) -> None:
        axes = (self.basis_x, self.basis_y, self.basis_z)
        vals = (self.units_per_block, *self.botw_origin.__dict__.values(),
                *self.minecraft_origin.__dict__.values(),
                *(v for a in axes for v in a.__dict__.values()))
        if not all(isfinite(v) for v in vals):
            raise ValueError("Coordinates and scale must be finite")
        if self.units_per_block <= 0:
            raise ValueError("Scale must be positive")
        for i in range(3):
            for j in range(3):
                actual = dot(axes[i], axes[j])
                expected = 1.0 if i == j else 0.0
                if abs(actual - expected) > 1e-5:
                    raise ValueError("Basis vectors must be orthonormal")

    def to_minecraft(self, pos: Vector3) -> Vector3:
        p = (pos - self.botw_origin) * (1.0 / self.units_per_block)
        return self.minecraft_origin + Vector3(
            dot(p, self.basis_x), dot(p, self.basis_y), dot(p, self.basis_z))

    def to_botw(self, pos: Vector3) -> Vector3:
        p = (pos - self.minecraft_origin) * self.units_per_block
        return self.botw_origin + (self.basis_x * p.x) + (
            self.basis_y * p.y) + (self.basis_z * p.z)


# Diagnostic identity mapping ONLY; real BOTW scale/orientation is unknown.
IDENTITY_TEST_MAP = CoordinateMap(
    Vector3(0, 0, 0), Vector3(0, 0, 0), 1.0,
    Vector3(1, 0, 0), Vector3(0, 1, 0), Vector3(0, 0, 1))
