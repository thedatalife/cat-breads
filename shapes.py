"""shapes.py - a few organic SDF studies built with sdf.py. Each is p -> distance."""
import numpy as np
import sdf

BOUNDS = (-1.35, 1.35)


def tendril(p, start, direction, length, radius, curl_axis, curl=0.9, segments=5, taper=0.55, k=0.06):
    """A curving, tapering arm made of chained capsules, with a bulb at the tip."""
    a = np.asarray(start, np.float32)
    d = np.asarray(direction, np.float32)
    d = d / np.linalg.norm(d)
    seg = length / segments
    out = None
    for i in range(segments):
        d = sdf.rotate_vec(d, curl_axis, curl / segments)
        b = a + d * seg
        r0 = radius * (1 - taper * i / segments)
        r1 = radius * (1 - taper * (i + 1) / segments)
        di = sdf.cone_capsule(p, a, b, r0, r1)
        out = di if out is None else sdf.smooth_union(out, di, k)
        a = b
    return sdf.smooth_union(out, sdf.sphere(p, r1 * 1.9, a), 0.05)


def pod(p):
    """A soft body with curling tendrils, noise-warped, with a subtle bumpy skin."""
    q = sdf.warp(p, amplitude=0.09, frequency=1.7, seed=3)
    d = sdf.ellipsoid(q, (0.55, 0.50, 0.66))
    rng = np.random.default_rng(7)
    for n in sdf.fibonacci_sphere(12):
        axis = sdf.rotate_vec(n, (0.3, 0.8, 0.5), 1.4)  # some perpendicular-ish axis
        d = sdf.smooth_union(
            d,
            tendril(q, n * 0.28, n, length=0.85 + 0.35 * rng.random(), radius=0.13 + 0.04 * rng.random(),
                    curl_axis=axis, curl=0.7 + 0.8 * rng.random()),
            0.16,
        )
    return d + 0.022 * sdf.fbm3(p * 6.0, octaves=2, seed=11)


def gyroid_egg(p):
    """An egg whose upper shell is peeled away to reveal a gyroid lattice inside."""
    q = p.copy()
    q[..., 2] = np.where(q[..., 2] > 0, q[..., 2] / 1.12, q[..., 2] / 0.92)  # egg asymmetry
    egg = sdf.ellipsoid(q, (0.70, 0.70, 0.88))
    lattice = sdf.gyroid(sdf.rotate(p, (1, 0.4, 0.2), 0.5), scale=12.5, thickness=0.065)
    core = sdf.intersect(sdf.inflate(egg, -0.015), lattice)
    skin = sdf.shell(egg, 0.035)
    peel = p[..., 2] - (0.05 + 0.35 * p[..., 0] + 0.12 * np.sin(6 * p[..., 1]))  # wavy tilted cut
    skin = sdf.smooth_intersect(skin, peel, 0.04)
    return sdf.smooth_union(core, skin, 0.03)


def ridged_torus(p, R, r, ridges=3, turns=3, amp=0.045):
    """A torus with helical ridges spiralling around the tube."""
    theta = np.arctan2(p[..., 1], p[..., 0])
    rho = np.hypot(p[..., 0], p[..., 1]) - np.float32(R)
    phi = np.arctan2(p[..., 2], rho)
    d = np.hypot(rho, p[..., 2]) - np.float32(r)
    return d + np.float32(amp) * np.cos(ridges * phi + turns * theta)


def linked_rings(p):
    """Two ridged rings threaded through each other (a Hopf link), gently warped."""
    q = sdf.translate(p, (-0.36, 0, 0))
    q = sdf.warp(q, amplitude=0.05, frequency=2.0, seed=5)
    a = ridged_torus(q, 0.72, 0.26, ridges=3, turns=3, amp=0.045)
    qb = sdf.rotate(sdf.translate(q, (0.72, 0, 0)), (1, 0, 0), np.pi / 2)
    b = ridged_torus(qb, 0.72, 0.26, ridges=4, turns=2, amp=0.04)
    return sdf.smooth_union(a, b, 0.06)


CATALOG = [
    ("Pod", pod, (0.80, 0.24, 0.17)),
    ("GyroidEgg", gyroid_egg, (0.90, 0.82, 0.66)),
    ("LinkedRings", linked_rings, (0.08, 0.40, 0.47)),
]
