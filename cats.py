"""cats.py - SDF cat characters modelled on the hand-drawn 'Cat Breads' cards (all 23).

A character is a list of parts; each part wraps a Model: a smooth union of coloured SDF primitives
plus paint layers. Model.sdf(p) is the surface, Model.color(p) the colour at a point. The runner
bakes colour into a vertex-colour attribute on the OpenVDB mesh, so one mesh carries patches,
stripes, eyes, blush and mouths with no UVs or textures.

Cats face -Y. The floor is z = 0. A builder returns a list of parts, or {"parts": [...], "yaw": deg}.
"""
import numpy as np
import sdf

F = np.float32
BOUNDS = ((-1.05, -1.05, -0.15), (1.05, 1.05, 1.95))

# ---------------------------------------------------------------- palette
WHITE = (0.96, 0.95, 0.92)
BLACK = (0.05, 0.05, 0.06)
ORANGE = (0.95, 0.50, 0.10)
DARK_ORANGE = (0.80, 0.38, 0.06)
BROWN = (0.40, 0.21, 0.10)
FUR_BROWN = (0.55, 0.35, 0.20)
DARK_FUR = (0.35, 0.22, 0.12)
GREY = (0.55, 0.55, 0.57)
DARK_GREY = (0.33, 0.33, 0.36)
PINK = (0.98, 0.55, 0.64)
HOT_PINK = (0.95, 0.22, 0.58)
MAGENTA = (0.90, 0.20, 0.60)
PURPLE = (0.58, 0.28, 0.80)
CYAN = (0.25, 0.80, 0.92)
BLUE = (0.30, 0.48, 0.92)
LIGHT_BLUE = (0.50, 0.72, 0.92)
RED = (0.85, 0.10, 0.10)
GOLD = (0.98, 0.78, 0.22)
YELLOW = (0.99, 0.82, 0.15)
GREEN = (0.35, 0.65, 0.25)
LEAF = (0.30, 0.55, 0.20)
COFFEE = (0.28, 0.16, 0.08)
CREAM = (0.98, 0.94, 0.86)
CARDBOARD = (0.74, 0.54, 0.32)
TAN = (0.84, 0.64, 0.50)


def hsv(h, s, v):
    h = np.asarray(h, F) % 1.0
    i = np.floor(h * 6).astype(int) % 6
    f = h * 6 - np.floor(h * 6)
    p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    vv = np.full_like(f, v)
    sel = [i == 0, i == 1, i == 2, i == 3, i == 4, i == 5]
    r = np.select(sel, [vv, q, p, p, t, vv])
    g = np.select(sel, [t, vv, vv, q, p, p])
    b = np.select(sel, [p, p, t, vv, vv, q])
    return np.stack([r, g, b], -1).astype(F)


def rainbow(t):
    return hsv(np.asarray(t, F) * 0.85, 0.85, 0.97)


# ---------------------------------------------------------------- model
class Model:
    def __init__(self, k=0.05, color_softness=0.008):
        self.parts, self.paints, self.k, self.cs = [], [], k, color_softness
        self.tags, self.anatomy = [], {}  # per-part rig tag ("body", "head", "ear.L", ...) and bone landmarks

    def add(self, fn, color, k=None, tag=None):
        self.parts.append((fn, np.asarray(color, F), self.k if k is None else k))
        self.tags.append(tag)
        return fn

    def tag_distance(self, p, tag):
        """Distance to the union of the parts carrying `tag` (None if the tag is unused)."""
        d = None
        for (fn, _, _), t in zip(self.parts, self.tags):
            if t == tag:
                di = fn(p)
                d = di if d is None else np.minimum(d, di)
        return d

    def paint(self, mask_fn, color):
        """Overlay a colour (or a points->rgb callable) where mask_fn(p) is 1."""
        self.paints.append((mask_fn, color))
        return self

    def snapshot(self):
        """The surface so far, frozen, for parts that hug the existing body (collars, bands)."""
        parts = list(self.parts)

        def fn(p):
            d = None
            for f, _, k in parts:
                di = f(p)
                d = di if d is None else sdf.smooth_union(d, di, k)
            return d

        return fn

    def sdf(self, p):
        return self.snapshot()(p)

    def color(self, p):
        ds = np.stack([fn(p) for fn, _, _ in self.parts], -1)
        cols = np.stack([c for _, c, _ in self.parts])
        w = np.exp(-(ds - ds.min(-1, keepdims=True)) / F(self.cs))
        col = (w / w.sum(-1, keepdims=True)) @ cols
        for mask_fn, c in self.paints:
            m = np.clip(mask_fn(p), 0, 1).astype(F)[..., None]
            cc = c(p) if callable(c) else np.broadcast_to(np.asarray(c, F), col.shape)
            col = col * (1 - m) + cc * m
        return col


def part(name, model, material="clay", bounds=None, scale=1.0, offset=(0, 0, 0)):
    """Wrap a Model as a mesh part. scale/offset place a model built at standard size."""
    s, off = F(scale), np.asarray(offset, F)
    if scale == 1.0 and not np.any(off):
        fn, col = model.sdf, model.color
    else:
        fn = lambda p: model.sdf((p - off) / s) * s
        col = lambda p: model.color((p - off) / s)
    if bounds is None and (scale != 1.0 or np.any(off)):
        lo, hi = (np.asarray(b, F) for b in BOUNDS)
        bounds = (tuple(lo * s + off), tuple(hi * s + off))
    return {"name": name, "sdf": fn, "color": col, "material": material, "bounds": bounds or BOUNDS,
            "model": model, "scale": float(scale), "offset": tuple(float(v) for v in off)}


# ---------------------------------------------------------------- primitives at a place
def _v(x):
    return np.asarray(x, F)


def ellipsoid_at(center, radii, rot=None):
    c = _v(center)
    if rot is None:
        return lambda p: sdf.ellipsoid(p, radii, c)
    axis, ang = rot
    return lambda p: sdf.ellipsoid(sdf.rotate(p - c, axis, ang), radii)


def sphere_at(center, r):
    return lambda p: sdf.sphere(p, r, center)


def cone_at(a, b, r0, r1):
    return lambda p: sdf.cone_capsule(p, a, b, r0, r1)


def torus_at(center, R, r, rot=None):
    c = _v(center)
    if rot is None:
        return lambda p: sdf.torus(p, R, r, c)
    axis, ang = rot
    return lambda p: sdf.torus(sdf.rotate(p - c, axis, ang), R, r)


def cylinder_at(center, r, half_height, rounding=0.0, rot=None):
    c = _v(center)
    if rot is None:
        return lambda p: sdf.cylinder(p, r - rounding, half_height - rounding, c) - F(rounding)
    axis, ang = rot
    return lambda p: sdf.cylinder(sdf.rotate(p - c, axis, ang), r - rounding, half_height - rounding) - F(rounding)


def box_at(center, size, rounding=0.0, rot=None):
    """Rounded box; size = half extents."""
    c, sz = _v(center), _v(size) - F(rounding)
    if rot is None:
        return lambda p: sdf.box(p, sz, c) - F(rounding)
    axis, ang = rot
    return lambda p: sdf.box(sdf.rotate(p - c, axis, ang), sz) - F(rounding)


def hollow_box(center, size, wall=0.05, rounding=0.02, open_axis=2, open_sign=1):
    """A box with one open face (a cardboard box, a paper bag)."""
    c, s = _v(center), _v(size)
    outer = box_at(c, s, rounding)
    s_in = s - F(wall)
    s_in[open_axis] = s[open_axis]
    c_in = c.copy()
    c_in[open_axis] += open_sign * wall
    inner = box_at(c_in, s_in, rounding * 0.5)
    return lambda p: sdf.subtract(outer(p), inner(p))


def heart_at(center, size, depth=0.25):
    """A plump heart standing upright in the x-z plane (thickness along y)."""
    c = _v(center)
    A, B, C = np.array([-0.5, 0.25]), np.array([0.5, 0.25]), np.array([0.0, -0.62])
    edges = []
    for P, Q in ((A, B), (B, C), (C, A)):
        e = Q - P
        n = np.array([e[1], -e[0]])
        n /= np.linalg.norm(n)
        if np.dot(np.array([0, 0]) - P, n) > 0:
            n = -n
        edges.append((P.astype(F), n.astype(F)))

    def fn(p):
        q = (p - c) / F(size)
        x, y, z = q[..., 0], q[..., 1], q[..., 2]
        tri = None
        for P, n in edges:
            d = (x - P[0]) * n[0] + (z - P[1]) * n[1]
            tri = d if tri is None else np.maximum(tri, d)
        d2 = sdf.smooth_union(sdf.smooth_union(np.hypot(x + 0.26, z - 0.28) - F(0.36), np.hypot(x - 0.26, z - 0.28) - F(0.36), 0.08), tri, 0.06)
        w = np.abs(y) - F(depth / size)
        d3 = np.sqrt(np.maximum(d2, 0) ** 2 + np.maximum(w, 0) ** 2) + np.minimum(np.maximum(d2, w), 0)
        return (d3 - F(0.04)) * F(size)

    return fn


def bezier(p0, p1, p2, n=10):
    p0, p1, p2 = (_v(v) for v in (p0, p1, p2))
    t = np.linspace(0, 1, n, dtype=F)[:, None]
    return (1 - t) ** 2 * p0 + 2 * (1 - t) * t * p1 + t ** 2 * p2


def chain(points, r0, r1=None):
    """A polyline of capsules whose radius tapers from r0 to r1."""
    pts = _v(points)
    n = len(pts) - 1
    r1 = r0 if r1 is None else r1

    def fn(p):
        d = None
        for i in range(n):
            di = sdf.cone_capsule(p, pts[i], pts[i + 1], r0 + (r1 - r0) * i / n, r0 + (r1 - r0) * (i + 1) / n)
            d = di if d is None else np.minimum(d, di)
        return d

    return fn


def polyline_param(p, points):
    """Distance to a polyline and the normalised arc-length parameter of the closest point."""
    pts = _v(points)
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seg)])
    best_d = best_t = None
    for i in range(len(pts) - 1):
        a, ba = pts[i], pts[i + 1] - pts[i]
        pa = p - a
        h = np.clip((pa @ ba) / float(ba @ ba), 0, 1).astype(F)
        d = np.linalg.norm(pa - ba * h[..., None], axis=-1)
        t = (cum[i] + h * seg[i]) / cum[-1]
        if best_d is None:
            best_d, best_t = d, t
        else:
            m = d < best_d
            best_d, best_t = np.where(m, d, best_d), np.where(m, t, best_t)
    return best_d, best_t


def horn(base, tip, r0, r1, turns=3.0, depth=0.14):
    """A cone with a helical ridge: a unicorn horn."""
    base, tip = _v(base), _v(tip)
    axis = tip - base
    L = float(np.linalg.norm(axis))
    u = axis / L
    a = np.array([1, 0, 0], F) if abs(u[0]) < 0.9 else np.array([0, 1, 0], F)
    e1 = np.cross(u, a)
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(u, e1)

    def fn(p):
        q = p - base
        t, x, y = q @ u, q @ e1, q @ e2
        r_local = r0 + (r1 - r0) * np.clip(t / L, 0, 1)
        return sdf.cone_capsule(p, base, tip, r0, r1) + F(depth) * r_local * np.sin(np.arctan2(y, x) - 2 * np.pi * turns * t / L)

    return fn


def wing_feather(sx, root=(0.36, 0.30, 0.95), color=None):
    """Three stacked flattened ellipsoids fanning up and out: an angel wing. Returns an sdf."""
    rx, ry, rz = root
    lobes = [((sx * (rx + 0.12), ry, rz + 0.14), (0.32, 0.10, 0.13), -38), ((sx * (rx + 0.06), ry, rz), (0.30, 0.10, 0.12), -18),
             ((sx * rx, ry, rz - 0.13), (0.26, 0.10, 0.11), 0)]
    fns = [ellipsoid_at(c, r, rot=((0, 1, 0), sx * np.radians(a))) for c, r, a in lobes]
    return lambda p: sdf.smooth_union(sdf.smooth_union(fns[0](p), fns[1](p), 0.04), fns[2](p), 0.04)


def wing_bat(sx, root=(0.52, 0.30, 0.92)):
    """A flattened ellipsoid with two scallops bitten out of its lower edge: a bat wing."""
    rx, ry, rz = root
    body = ellipsoid_at((sx * rx, ry, rz), (0.38, 0.07, 0.26), rot=((0, 1, 0), sx * np.radians(-22)))
    bites = [sphere_at((sx * (rx - 0.14), ry, rz - 0.30), 0.15), sphere_at((sx * (rx + 0.16), ry, rz - 0.27), 0.15)]
    return lambda p: sdf.subtract(body(p), np.minimum(bites[0](p), bites[1](p)))


def add_flower(m, center, petal, core=YELLOW, r=0.085, k=0.01):
    c = _v(center)
    m.add(sphere_at(c, r * 0.55), core, k)
    for i in range(5):
        a = i * 2 * np.pi / 5 + np.pi / 2
        m.add(ellipsoid_at(c + np.array([np.cos(a), 0, np.sin(a)], F) * r, (r * 0.62, r * 0.32, r * 0.62)), petal, k)


# ---------------------------------------------------------------- paint masks (points -> [0,1])
def soft(d, edge=0.01):
    return np.clip(F(0.5) - d / F(edge), 0, 1)


def region(fn, edge=0.01):
    return lambda p: soft(fn(p), edge)


def disc(center, r, edge=0.012):
    c = _v(center)
    return lambda p: soft(np.linalg.norm(p - c, axis=-1) - F(r), edge)


def stroke(points, width, edge=0.006):
    return lambda p: soft(polyline_param(p, points)[0] - F(width / 2), edge)


def bands(axis, start, width, edge=0.01):
    """Alternating stripes along an axis, starting with a painted band at `start`."""

    def m(p):
        t = (p[..., axis] - F(start)) / F(width)
        wave = np.clip(F(0.5) + np.sin(np.pi * t) * F(width / (2 * np.pi * edge)), 0, 1)
        return wave * soft(F(start) - p[..., axis], edge)

    return m


def noise_patches(freq, threshold, seed=0, edge=0.05):
    return lambda p: np.clip((sdf.fbm3(p * F(freq), octaves=2, seed=seed) - F(threshold)) / F(edge) + F(0.5), 0, 1)


def above(z, edge=0.05):
    return lambda p: soft(F(z) - p[..., 2], edge)


def behind(y, edge=0.05):
    return lambda p: soft(F(y) - p[..., 1], edge)


def before(y, edge=0.05):
    return lambda p: soft(p[..., 1] - F(y), edge)


def both(a, b):
    return lambda p: a(p) * b(p)


def either(a, b):
    return lambda p: np.clip(a(p) + b(p), 0, 1)


# ---------------------------------------------------------------- the cat kit
class Cat:
    """Loaf cat: body + head ellipsoids, with helpers that place features on the head surface."""

    def __init__(self, model, body=((0, 0.05, 0.40), (0.58, 0.50, 0.40)), head=((0, -0.10, 0.78), (0.50, 0.44, 0.40)),
                 color=WHITE, k=0.15, body_rot=None):
        self.m, self.color = model, color
        self.bc, self.br = _v(body[0]), _v(body[1])
        self.hc, self.hr = _v(head[0]), _v(head[1])
        model.add(ellipsoid_at(self.bc, self.br, rot=body_rot), color, tag="body")
        model.add(ellipsoid_at(self.hc, self.hr), color, k, tag="head")
        model.anatomy.update({"body": (self.bc.copy(), self.br.copy()), "head": (self.hc.copy(), self.hr.copy())})

    def front(self, x, z, out=0.0):
        """Point on the head's front surface at (x, z); out > 0 moves it outward (toward -y)."""
        cx, cy, cz = self.hc
        rx, ry, rz = self.hr
        s = max(1 - ((x - cx) / rx) ** 2 - ((z - cz) / rz) ** 2, 0.0)
        return np.array([x, cy - ry * np.sqrt(s) - out, z], F)

    def on_head(self, theta_deg, phi_deg, out=0.0):
        """Point on the head surface by azimuth (0 = +x, -90 = front) and elevation."""
        t, ph = np.radians(theta_deg), np.radians(phi_deg)
        n = np.array([np.cos(ph) * np.cos(t), np.cos(ph) * np.sin(t), np.sin(ph)], F)
        return self.hc + self.hr * n * (1 + out)

    def ears(self, colors=None, inner=PINK, spread=0.30, k=0.06, size=1.0):
        cx, cy, cz = self.hc
        rz = self.hr[2]
        for sx, col in zip((-1, 1), colors or (self.color, self.color)):
            base = np.array([cx + sx * spread, cy + 0.02, cz + rz * 0.70], F)
            tip = base + np.array([sx * 0.14, 0.02, rz * 0.30 + 0.28], F) * size
            side = "L" if sx > 0 else "R"  # the cat faces -Y, so its left is +X
            self.m.add(cone_at(base, tip, 0.15 * size, 0.035 * size), col, k, tag=f"ear.{side}")
            self.m.anatomy[f"ear.{side}"] = (base.copy(), tip.copy())
            if inner is not None:
                fwd = np.array([0, -0.10 * size, 0.03], F)
                self.m.paint(region(cone_at(base + fwd, tip + fwd - (tip - base) * 0.2, 0.07 * size, 0.012), 0.01), inner)

    def paws(self, color=None, k=0.05, front=True, back=True):
        col = color or self.color
        cy, ry = self.bc[1], self.br[1]
        for sx in (-1, 1):
            if front:
                self.m.add(ellipsoid_at((sx * 0.27, cy - ry * 0.82, 0.10), (0.14, 0.12, 0.09)), col, k, tag="body")
            if back:
                self.m.add(ellipsoid_at((sx * 0.42, cy + ry * 0.55, 0.10), (0.14, 0.12, 0.09)), col, k, tag="body")

    def tail(self, color=None, r0=0.09, r1=0.06, k=0.05, points=None):
        col = color or self.color
        if points is None:
            cx, cy, cz = self.bc
            rx, ry, rz = self.br
            points = bezier((cx + rx * 0.7, cy + ry * 0.75, 0.24), (cx + rx * 1.6, cy + ry * 0.85, 0.30),
                            (cx + rx * 1.35, cy + ry * 0.15, rz * 1.9), 10)
        self.m.add(chain(points, r0, r1), col, k, tag="tail")
        self.m.anatomy["tail"] = np.asarray(points, F)
        return points

    def whiskers(self, color=WHITE, z=None, width=0.010):
        cz = float(self.hc[2])
        z = cz + 0.02 if z is None else z
        for sx in (-1, 1):
            for dz in (-0.05, 0.0, 0.05):
                a, b = self.front(sx * 0.24, z + dz * 0.5, 0.004), self.front(sx * 0.44, z + dz * 1.8, 0.004)
                self.m.paint(stroke([a, b], width), color)

    def face(self, eye_dx=0.17, eye_z=None, eye_r=0.045, eye_color=BLACK, nose=PINK, mouth=BLACK, blush=PINK, eyes="dot",
             mouth_width=0.016, eye_ring=None):
        cz = float(self.hc[2])
        ez = cz + 0.08 if eye_z is None else eye_z
        for sx in (-1, 1):
            c = self.front(sx * eye_dx, ez, -0.015)
            if eye_ring is not None:
                self.m.paint(disc(c, eye_r + 0.028, 0.008), eye_ring)
            if eyes == "dot":  # geometry only (no painted disc), so a rig can squash it for a blink
                side = "L" if sx > 0 else "R"
                self.m.add(sphere_at(c, eye_r), eye_color, 0.004, tag=f"eye.{side}")
                self.m.anatomy[f"eye.{side}"] = (c.copy(), float(eye_r))
                if eye_color != BLACK:
                    self.m.paint(disc(c + np.array([0, -eye_r, 0], F), 0.022, 0.006), BLACK)
            elif eyes in ("happy", "closed"):
                a0, a1 = (200, 340) if eyes == "happy" else (20, 160)
                pts = [self.front(sx * eye_dx + eye_r * np.cos(np.radians(a)), ez + eye_r * np.sin(np.radians(a)), 0.004)
                       for a in np.linspace(a0, a1, 7)]
                self.m.paint(stroke(pts, 0.018, 0.006), BLACK)
            elif eyes == "x":
                for s in (-1, 1):
                    a = self.front(sx * eye_dx - eye_r, ez + s * eye_r, 0.004)
                    b = self.front(sx * eye_dx + eye_r, ez - s * eye_r, 0.004)
                    self.m.paint(stroke([a, b], 0.018, 0.006), BLACK)
        if nose is not None:
            self.m.add(sphere_at(self.front(0, ez - 0.10, -0.008), 0.022), nose, 0.004, tag="head")
        if mouth is not None:
            mz = ez - 0.14
            pts = [self.front(x, mz + dz, 0.004) for x, dz in ((-0.07, 0), (-0.035, -0.03), (0, 0), (0.035, -0.03), (0.07, 0))]
            self.m.paint(stroke(pts, mouth_width, 0.006), mouth)
        if blush is not None:
            for sx in (-1, 1):
                self.m.paint(disc(self.front(sx * 0.31, ez - 0.10, 0.0), 0.065, 0.02), blush)


def standard_cat(m, color=WHITE, k=0.15, ears=True, paws=True, tail=True, ear_inner=PINK, ear_colors=None, ear_size=1.0):
    cat = Cat(m, color=color, k=k)
    if ears:
        cat.ears(colors=ear_colors, inner=ear_inner, size=ear_size)
    if paws:
        cat.paws()
    pts = cat.tail() if tail else None
    return cat, pts


def calico(m, seeds=(4, 9), colors=(ORANGE, BROWN), gate=None):
    gate = gate or either(above(0.95, 0.06), behind(0.10, 0.06))
    m.paint(both(noise_patches(3.2, 0.12, seed=seeds[0]), gate), colors[0])
    m.paint(both(noise_patches(3.0, 0.22, seed=seeds[1]), gate), colors[1])


def tabby(m, dark, width=0.12, start=-0.40, gate=None):
    m.paint(both(bands(1, start, width, edge=0.012), gate or above(0.62, 0.08)), dark)


# ---------------------------------------------------------------- characters
def mascot():
    """The cover cat: a calico beside a tall red flower."""
    m = Model(k=0.05)
    cat, _ = standard_cat(m)
    calico(m, seeds=(2, 3))
    fc = np.array([-0.78, -0.30, 0.98], F)
    add_flower(m, fc, RED, r=0.11)
    m.add(chain([fc + [0, 0, -0.08], (-0.76, -0.27, 0.55), (-0.72, -0.24, 0.05)], 0.025, 0.03), LEAF, 0.01)
    m.add(ellipsoid_at((-0.88, -0.27, 0.45), (0.11, 0.03, 0.05), rot=((0, 1, 0), np.radians(30))), LEAF, 0.01)
    m.add(ellipsoid_at((-0.62, -0.26, 0.32), (0.10, 0.03, 0.05), rot=((0, 1, 0), np.radians(-35))), LEAF, 0.01)
    m.add(ellipsoid_at((-0.55, -0.40, 0.22), (0.13, 0.11, 0.09)), WHITE, 0.05)  # paw reaching for the stem
    cat.face()
    return [part("body", m)]


def siamese():
    DARK, CREAMY = (0.28, 0.16, 0.09), (0.94, 0.86, 0.70)
    m = Model(k=0.05)
    cat = Cat(m, body=((0, 0.02, 0.50), (0.52, 0.45, 0.50)), head=((0, -0.08, 1.05), (0.48, 0.42, 0.40)), color=CREAMY, k=0.12)
    cat.ears(colors=(DARK, DARK), inner=(0.55, 0.35, 0.30))
    cat.paws(DARK)
    cat.tail(DARK)
    m.paint(region(ellipsoid_at(cat.front(0, 1.05, -0.06), (0.30, 0.22, 0.27)), 0.03), DARK)
    cat.face(eye_color=(0.35, 0.62, 0.92), blush=None)
    return [part("body", m)]


def sphynx():
    TAN_D = (0.62, 0.42, 0.30)
    m = Model(k=0.05)
    cat = Cat(m, body=((0, 0.02, 0.48), (0.46, 0.40, 0.48)), head=((0, -0.06, 1.00), (0.46, 0.40, 0.38)), color=TAN, k=0.10)
    cat.ears(inner=(0.90, 0.60, 0.55), spread=0.28, size=1.35)
    cat.paws()
    cat.tail(r0=0.06, r1=0.03)
    for dz in (0.20, 0.26, 0.32):  # forehead wrinkles
        pts = [cat.front(x, 1.00 + dz + 0.10 * x * x, 0.004) for x in (-0.16, -0.08, 0, 0.08, 0.16)]
        m.paint(stroke(pts, 0.012, 0.005), TAN_D)
    m.paint(region(ellipsoid_at((0, -0.40, 0.45), (0.22, 0.12, 0.22)), 0.04), (0.93, 0.74, 0.64))
    cat.face(eye_r=0.055, eye_dx=0.18, blush=(0.92, 0.55, 0.50))
    return [part("body", m)]


def norwegian_forest():
    DARK = (0.20, 0.12, 0.08)
    m = Model(k=0.08)
    cat = Cat(m, body=((0, 0.05, 0.45), (0.62, 0.55, 0.45)), head=((0, -0.12, 0.85), (0.52, 0.46, 0.42)), color=DARK, k=0.18)
    cat.ears(inner=(0.55, 0.40, 0.35), size=1.1)
    for c, r in (((-0.60, 0.05, 0.50), (0.24, 0.32, 0.30)), ((0.60, 0.05, 0.50), (0.24, 0.32, 0.30)), ((0, 0.55, 0.55), (0.40, 0.22, 0.35)),
                 ((-0.50, -0.25, 0.78), (0.18, 0.20, 0.15)), ((0.50, -0.25, 0.78), (0.18, 0.20, 0.15)), ((0, 0.0, 0.12), (0.62, 0.55, 0.16))):
        m.add(ellipsoid_at(c, r), DARK, 0.14)  # fluff
    cat.paws(WHITE)
    cat.tail(r0=0.14, r1=0.10)
    m.paint(region(ellipsoid_at((0, -0.52, 0.40), (0.26, 0.16, 0.30)), 0.04), WHITE)  # chest bib
    m.paint(region(ellipsoid_at(cat.front(0, 0.74, -0.02), (0.20, 0.12, 0.13)), 0.03), WHITE)  # muzzle
    cat.whiskers(WHITE, z=0.80)
    cat.face(blush=None, eye_ring=WHITE)
    return [part("body", m)]


def catuccino():
    """A calico peeking out of a white cup on a saucer, paws on the rim."""
    cup = Model(k=0.02, color_softness=0.01)
    outer = cylinder_at((0, 0, 0.42), 0.56, 0.41, rounding=0.03)
    inner = cylinder_at((0, 0, 0.50), 0.49, 0.40)
    cup.add(lambda p: sdf.subtract(outer(p), inner(p)), WHITE)
    cup.add(torus_at((0.60, 0, 0.44), 0.17, 0.05, rot=((1, 0, 0), np.pi / 2)), WHITE, 0.03)
    cup.add(cylinder_at((0, 0, 0.02), 0.78, 0.03, rounding=0.015), WHITE, 0.01)
    cup.add(cylinder_at((0, 0, 0.60), 0.49, 0.03), COFFEE, 0.005)
    m = Model(k=0.05)
    cat = Cat(m, body=((0, 0.02, 0.62), (0.40, 0.36, 0.30)), head=((0, -0.04, 1.00), (0.44, 0.40, 0.36)), k=0.10)
    cat.ears(colors=(ORANGE, BROWN), spread=0.26)
    for sx in (-1, 1):
        m.add(ellipsoid_at((sx * 0.25, -0.50, 0.85), (0.13, 0.11, 0.09)), WHITE, 0.04)
    calico(m, seeds=(4, 9))
    cat.face(eye_dx=0.15)
    return [part("cup", cup, "ceramic"), part("cat", m)]


def wanderer():
    """Calico daydreaming under three floating flowers."""
    m = Model(k=0.05)
    cat, _ = standard_cat(m)
    calico(m, seeds=(6, 7))
    for c, col in (((-0.38, -0.20, 1.60), BLUE), ((0, -0.26, 1.76), PINK), ((0.38, -0.20, 1.60), BLUE)):
        add_flower(m, c, col)
    cat.face(eyes="closed")
    return [part("body", m)]


def day_cat():
    """Calico with clusters of little blue flowers overhead."""
    m = Model(k=0.05)
    cat, _ = standard_cat(m)
    calico(m, seeds=(11, 12))
    for c in ((-0.42, -0.18, 1.55), (-0.14, -0.30, 1.72), (0.20, -0.22, 1.78), (0.46, -0.15, 1.58)):
        for i in range(6):
            off = np.array([np.cos(i * 2.4) * 0.075, np.sin(i * 1.7) * 0.04, np.sin(i * 2.4) * 0.075], F)
            m.add(sphere_at(_v(c) + off, 0.055), BLUE, 0.02)
    cat.face(eyes="x")
    return [part("body", m)]


def investigator_one():
    """Head-first into a paper bag; only the back half is out."""
    bag = Model(k=0.01)
    bag.add(hollow_box((-0.62, 0.05, 0.42), (0.55, 0.42, 0.40), wall=0.05, rounding=0.03, open_axis=0, open_sign=1), CARDBOARD)
    FUR = (0.48, 0.38, 0.30)
    m = Model(k=0.05)
    Cat(m, body=((0.30, 0.05, 0.40), (0.52, 0.45, 0.40)), head=((-0.30, 0.05, 0.45), (0.40, 0.36, 0.34)), color=FUR, k=0.14)
    m.add(ellipsoid_at((0.55, -0.32, 0.10), (0.13, 0.12, 0.09)), FUR, 0.05)
    m.add(ellipsoid_at((0.55, 0.42, 0.10), (0.13, 0.12, 0.09)), FUR, 0.05)
    tail_pts = bezier((0.75, 0.10, 0.40), (1.15, 0.15, 0.55), (1.05, 0.05, 1.05), 10)
    m.add(chain(tail_pts, 0.08, 0.05), FUR, 0.05, tag="tail")
    m.anatomy["tail"] = tail_pts
    m.paint(both(bands(0, -0.10, 0.14, edge=0.012), above(0.5, 0.08)), (0.35, 0.27, 0.20))
    return [part("bag", bag, bounds=((-1.3, -0.6, -0.15), (0.2, 0.7, 1.0))), part("body", m, bounds=((-0.6, -0.6, -0.15), (1.3, 0.7, 1.3)))]


def lucky_cat():
    """Maneki-neko: upright, one paw raised, red collar with a gold bell, koban coin."""
    m = Model(k=0.05)
    cat = Cat(m, body=((0, 0.02, 0.50), (0.52, 0.45, 0.50)), head=((0, -0.08, 1.05), (0.50, 0.44, 0.42)), k=0.12)
    cat.ears(colors=(ORANGE, ORANGE), inner=RED)
    body = m.snapshot()  # body + head + ears only: the collar band hugs this surface
    m.add(ellipsoid_at((-0.34, 0.30, 0.11), (0.16, 0.14, 0.10)), WHITE, 0.05)
    m.add(chain([(-0.34, -0.20, 0.72), (-0.58, -0.30, 1.20)], 0.12, 0.11), WHITE, 0.06)
    m.add(ellipsoid_at((-0.62, -0.36, 1.32), (0.15, 0.11, 0.14)), WHITE, 0.04)
    cat.tail()

    def collar(p):
        zt = p[..., 2] - F(0.22) * p[..., 1]
        return np.maximum(np.abs(zt - F(0.86)) - F(0.045), body(p) - F(0.03))

    m.add(collar, RED, 0.005)
    bell = cat.front(0, 0.72, 0.03)
    m.add(sphere_at(bell + [0, -0.03, -0.06], 0.08), GOLD, 0.01)
    m.paint(region(ellipsoid_at((0.28, -0.02, 1.36), (0.24, 0.30, 0.17)), 0.02), ORANGE)
    m.paint(region(ellipsoid_at((0.18, 0.32, 0.80), (0.32, 0.28, 0.26)), 0.02), ORANGE)
    m.paint(region(ellipsoid_at((-0.30, 0.18, 1.18), (0.20, 0.30, 0.16)), 0.02), ORANGE)
    cat.face(blush=None)
    cat.whiskers(RED, z=1.08, width=0.014)
    m.add(ellipsoid_at((0.36, -0.58, 0.30), (0.14, 0.10, 0.10)), WHITE, 0.04)
    coin = Model(k=0.02)
    coin.add(ellipsoid_at((0.42, -0.50, 0.42), (0.24, 0.05, 0.30), rot=((0, 1, 0), np.radians(-12))), GOLD)
    coin.paint(stroke([(0.42, -0.56, 0.66), (0.42, -0.56, 0.18)], 0.03), (0.70, 0.50, 0.10))
    return [part("body", m), part("coin", coin, "gold")]


def explorer():
    """An orange cat inside a glass fishbowl."""
    bowl = Model(k=0.01)

    def bowl_fn(p):
        shell = sdf.shell(sdf.sphere(p, 0.72, (0, 0, 0.74)), 0.025)
        opening = sdf.cylinder(p, 0.38, 0.40, (0, 0, 1.60))
        return np.maximum(sdf.subtract(shell, opening), F(0.04) - p[..., 2])

    bowl.add(bowl_fn, (0.85, 0.95, 1.0))
    m = Model(k=0.05)
    cat, _ = standard_cat(m, color=ORANGE)
    m.paint(region(ellipsoid_at((0, -0.52, 0.52), (0.30, 0.20, 0.34)), 0.04), WHITE)
    m.paint(region(ellipsoid_at((0.30, 0.10, 1.12), (0.26, 0.28, 0.16)), 0.03), WHITE)
    cat.face(eye_dx=0.16)
    return [part("bowl", bowl, "glass"), part("cat", m, scale=0.62, offset=(0, 0, 0.09))]


def dozer():
    """Orange tabby asleep in a cardboard box, paws over the front edge."""
    box = Model(k=0.01)
    box.add(hollow_box((0, 0.05, 0.36), (0.80, 0.70, 0.36), wall=0.06, rounding=0.03, open_axis=2, open_sign=1), CARDBOARD)
    m = Model(k=0.05)
    cat, _ = standard_cat(m, color=ORANGE, paws=False)
    tabby(m, DARK_ORANGE)
    for sx in (-1, 1):
        m.add(chain([(sx * 0.24, -0.35, 0.50), (sx * 0.24, -0.78, 0.76)], 0.09, 0.08), ORANGE, 0.05)
        m.add(ellipsoid_at((sx * 0.24, -0.80, 0.78), (0.13, 0.11, 0.09)), ORANGE, 0.04)
    cat.face(eyes="closed")
    return [part("box", box), part("cat", m, scale=0.85, offset=(0, 0, 0.06))]


def stretcher():
    """Front down, rear up: the play-bow stretch."""
    m = Model(k=0.05)
    cat = Cat(m, body=((0, 0.20, 0.55), (0.48, 0.55, 0.34)), head=((0, -0.42, 0.40), (0.40, 0.36, 0.32)), color=FUR_BROWN, k=0.12,
              body_rot=((1, 0, 0), np.radians(28)))
    cat.ears(spread=0.26, size=0.9)
    for sx in (-1, 1):
        m.add(chain([(sx * 0.20, -0.35, 0.32), (sx * 0.24, -0.88, 0.10)], 0.09, 0.08), FUR_BROWN, 0.05)
        m.add(sphere_at((sx * 0.25, -0.92, 0.09), 0.10), FUR_BROWN, 0.04)
        m.add(ellipsoid_at((sx * 0.32, 0.62, 0.10), (0.14, 0.12, 0.09)), FUR_BROWN, 0.05)
    tail_pts = bezier((0.05, 0.72, 0.78), (0.15, 0.88, 1.12), (0.36, 0.72, 1.32), 8)
    m.add(chain(tail_pts, 0.07, 0.05), FUR_BROWN, 0.05, tag="tail")
    m.anatomy["tail"] = tail_pts
    tabby(m, DARK_FUR, gate=above(0.45, 0.08))
    cat.face(eyes="closed", eye_dx=0.14)
    return [part("body", m)]


def show_off():
    """Tail straight up, rear to the camera. And no farting."""
    m = Model(k=0.05)
    cat, _ = standard_cat(m, color=FUR_BROWN, tail=False)
    tail_pts = bezier((0, 0.45, 0.35), (0, 0.62, 0.85), (0.08, 0.50, 1.25), 8)
    m.add(chain(tail_pts, 0.08, 0.05), FUR_BROWN, 0.05, tag="tail")
    m.anatomy["tail"] = tail_pts
    by = float(cat.bc[1] + cat.br[1])
    for s in (-1, 1):
        m.paint(stroke([(s * 0.035, by + 0.01, 0.435), (-s * 0.035, by + 0.01, 0.365)], 0.012), BLACK)
    tabby(m, DARK_FUR)
    cat.face()
    return {"parts": [part("body", m)], "yaw": 150}


def box_tester():
    """A tabby loaf on top of a sandwich."""
    sw = Model(k=0.01, color_softness=0.006)
    BREAD, CRUST, HAM, LETTUCE, CHEESE = (0.92, 0.78, 0.52), (0.68, 0.42, 0.20), (0.95, 0.55, 0.55), (0.45, 0.75, 0.25), (0.98, 0.80, 0.30)
    for z in (0.08, 0.36):
        sw.add(box_at((0, 0, z), (0.72, 0.62, 0.075), rounding=0.05), BREAD)
    sw.add(box_at((0, 0, 0.19), (0.68, 0.60, 0.025), rounding=0.02), HAM, 0.01)
    leaf = box_at((0, 0, 0.235), (0.76, 0.68, 0.015), rounding=0.01)
    sw.add(lambda p: leaf(p + np.stack([0 * p[..., 0], 0 * p[..., 0], 0.02 * np.sin(p[..., 0] * 14) * np.sin(p[..., 1] * 11)], -1)), LETTUCE, 0.01)
    sw.add(box_at((0, 0, 0.275), (0.62, 0.62, 0.012), rounding=0.01, rot=((0, 0, 1), np.radians(30))), CHEESE, 0.01)

    def crust(p):
        q = np.abs(p[..., :2]) - np.array([0.72, 0.62], F)
        d2 = np.linalg.norm(np.maximum(q, 0), axis=-1) + np.minimum(q.max(-1), 0)
        in_bread = np.maximum(soft(np.abs(p[..., 2] - 0.08) - 0.07, 0.01), soft(np.abs(p[..., 2] - 0.36) - 0.07, 0.01))
        return soft(-0.05 - d2, 0.02) * in_bread

    sw.paint(crust, CRUST)
    m = Model(k=0.05)
    cat, _ = standard_cat(m, color=FUR_BROWN)
    tabby(m, DARK_FUR)
    cat.face()
    return [part("sandwich", sw), part("cat", m, scale=0.82, offset=(0, 0, 0.42))]


def nature_lover():
    """Brown-hooded cat with a bouquet of roses and a butterfly."""
    BR = (0.45, 0.26, 0.12)
    m = Model(k=0.05)
    cat, _ = standard_cat(m, ear_colors=(BR, BR))
    m.paint(either(above(0.98, 0.05), behind(0.12, 0.05)), BR)
    for off in ((0, 0, 0), (0.12, -0.02, 0.06), (-0.11, -0.02, 0.07), (0.05, -0.05, 0.15), (-0.06, -0.04, 0.16)):
        m.add(sphere_at(_v((0.36, -0.60, 0.62)) + _v(off), 0.085), (0.80, 0.08, 0.12), 0.015)
    for off in (-0.04, 0.0, 0.04):
        m.add(chain([(0.36 + off, -0.58, 0.58), (0.30 + off, -0.52, 0.22)], 0.018, 0.02), LEAF, 0.01)
    m.add(ellipsoid_at((0.22, -0.60, 0.38), (0.06, 0.02, 0.09), rot=((0, 1, 0), np.radians(30))), LEAF, 0.01)
    m.add(ellipsoid_at((0.30, -0.60, 0.30), (0.13, 0.11, 0.09)), WHITE, 0.04)  # paw holding the stems
    bc = _v((-0.62, -0.30, 1.35))
    for s in (-1, 1):
        m.add(ellipsoid_at(bc + [s * 0.07, 0, 0.02], (0.07, 0.02, 0.055), rot=((0, 1, 0), s * np.radians(25))), (0.98, 0.72, 0.20), 0.01)
    m.add(chain([bc + [0, 0, -0.05], bc + [0, 0, 0.06]], 0.014, 0.012), BLACK, 0.005)
    cat.face(eyes="happy")
    return [part("body", m)]


def large_hearted():
    """A brown-and-white cat in front of a big red heart."""
    heart = Model(k=0.03)
    heart.add(heart_at((0, 0.58, 1.12), 0.74, depth=0.20), (0.85, 0.10, 0.15))
    m = Model(k=0.05)
    cat, _ = standard_cat(m, ear_colors=((0.50, 0.30, 0.15), (0.50, 0.30, 0.15)))
    m.paint(either(above(1.0, 0.05), behind(0.15, 0.05)), (0.50, 0.30, 0.15))
    cat.face(eyes="happy")
    return [part("heart", heart, bounds=((-1.2, -0.2, -0.15), (1.2, 1.3, 2.2))), part("body", m)]


def kitty_roll():
    """A cat as the filling of a maki roll."""
    roll = Model(k=0.01, color_softness=0.006)
    RICE, NORI = (0.97, 0.97, 0.95), (0.12, 0.20, 0.12)
    roll.add(cylinder_at((0, 0, 0.55), 0.55, 0.45, rounding=0.04, rot=((1, 0, 0), np.pi / 2)), RICE)
    roll.paint(lambda p: soft(F(0.505) - np.hypot(p[..., 0], p[..., 2] - 0.55), 0.01) * soft(np.abs(p[..., 1]) - F(0.43), 0.01), NORI)
    roll.paint(lambda p: noise_patches(28, 0.22, 5, edge=0.10)(p) * soft(F(0.43) - np.abs(p[..., 1]), 0.01), (0.86, 0.86, 0.84))
    roll.add(ellipsoid_at((0.30, -0.44, 0.40), (0.13, 0.05, 0.10)), (0.55, 0.75, 0.30), 0.01)
    roll.add(ellipsoid_at((-0.30, -0.44, 0.42), (0.14, 0.05, 0.11)), (0.98, 0.55, 0.35), 0.01)
    roll.add(ellipsoid_at((0.0, -0.44, 0.22), (0.16, 0.05, 0.07)), (0.55, 0.75, 0.30), 0.01)
    m = Model(k=0.05)
    cat, _ = standard_cat(m, color=ORANGE, tail=False, paws=False)
    m.paint(region(ellipsoid_at((0, -0.52, 0.55), (0.30, 0.20, 0.34)), 0.04), WHITE)
    cat.face(eye_dx=0.16)
    return [part("roll", roll), part("cat", m, scale=0.55, offset=(0, -0.40, 0.12))]


def angel_cat():
    """Pink cat with magenta feather wings and a gold halo."""
    m = Model(k=0.05)
    cat, _ = standard_cat(m, color=(0.98, 0.72, 0.80), ear_inner=HOT_PINK)
    for sx in (-1, 1):
        m.add(wing_feather(sx), MAGENTA, 0.03)
    m.add(torus_at((0, -0.05, 1.56), 0.22, 0.035, rot=((1, 0, 0), np.radians(12))), GOLD, 0.005)
    cat.face(eyes="happy")
    return [part("body", m)]


def devil_cat():
    """Dark cat with red horns, bat wings and an arrow-tipped tail."""
    DARK = (0.20, 0.18, 0.21)
    m = Model(k=0.05)
    cat, _ = standard_cat(m, color=DARK, tail=False, ear_inner=RED)
    for sx in (-1, 1):
        m.add(cone_at((sx * 0.18, -0.14, 1.12), (sx * 0.28, -0.16, 1.38), 0.06, 0.012), RED, 0.02)
        m.add(wing_bat(sx), (0.80, 0.08, 0.10), 0.02)
    tail_pts = bezier((0.42, 0.42, 0.25), (0.88, 0.45, 0.30), (0.82, 0.20, 0.88), 10)
    m.add(chain(tail_pts, 0.06, 0.04), DARK, 0.05, tag="tail")
    m.anatomy["tail"] = tail_pts
    m.add(cone_at((0.80, 0.18, 0.84), (0.88, 0.14, 1.06), 0.10, 0.006), RED, 0.01, tag="tail")
    cat.face(eye_ring=(0.92, 0.90, 0.80))
    return [part("body", m)]


def unimeow():
    """White loaf with a spiral rainbow horn, a magenta mane and a rainbow tail."""
    m = Model(k=0.05)
    cat = Cat(m)
    cat.ears()
    cat.paws()
    tail_pts = cat.tail()
    m.paint(lambda p: soft(polyline_param(p, tail_pts)[0] - F(0.12), 0.02) * soft(F(0.12) - polyline_param(p, tail_pts)[1], 0.05),
            lambda p: rainbow(polyline_param(p, tail_pts)[1]))
    m.paint(disc((-0.44, -0.06, 1.46), 0.16, 0.03), CYAN)
    m.paint(disc((0.44, -0.06, 1.46), 0.16, 0.03), ORANGE)
    base, tip = np.array([0, -0.30, 1.08], F), np.array([0, -0.50, 1.62], F)
    m.add(horn(base, tip, 0.10, 0.012, turns=3.0), CREAM, 0.03)
    u = (tip - base) / np.linalg.norm(tip - base)
    m.paint(region(cone_at(base + u * 0.04, tip, 0.105, 0.02), 0.008), lambda p: rainbow(((p - base) @ u) / 0.54))
    for (th, ph), col in zip(((-45, 55), (-15, 32), (2, 8), (20, -16)), (HOT_PINK, PINK, PURPLE, HOT_PINK)):
        m.add(ellipsoid_at(cat.on_head(th, ph, -0.25), (0.15, 0.14, 0.12)), col, 0.05)
    cat.face()
    return [part("body", m)]


def bumble_cat():
    """Black loaf with yellow bands, antennae, a stinger and translucent wings."""
    m = Model(k=0.05)
    cat = Cat(m, color=BLACK)
    cat.ears(inner=YELLOW)
    cat.paws()
    cat.tail()
    for sx in (-1, 1):
        m.add(chain([(sx * 0.16, -0.16, 1.10), (sx * 0.26, -0.28, 1.42)], 0.022, 0.018), BLACK, 0.02)
        m.add(sphere_at((sx * 0.27, -0.29, 1.45), 0.05), BLACK, 0.01)
    m.add(cone_at((0, 0.50, 0.40), (0, 0.80, 0.36), 0.09, 0.01), BLACK, 0.03)
    m.paint(bands(1, -0.02, 0.17, edge=0.01), YELLOW)
    m.paint(region(ellipsoid_at((0, -0.56, 0.74), (0.34, 0.16, 0.24)), 0.02), WHITE)
    cat.face(eye_dx=0.15, eye_z=0.83)
    wings = Model(k=0.02)
    for sx in (-1, 1):
        wings.add(ellipsoid_at((sx * 0.36, 0.12, 1.00), (0.38, 0.16, 0.10), rot=((0, 1, 0), sx * np.radians(-28))), CYAN)
    return [part("body", m), part("wings", wings, "wing")]


def holiday_kitty():
    """Orange cat in a Santa hat and striped scarf, with a little snowman."""
    m = Model(k=0.05)
    cat, _ = standard_cat(m, color=ORANGE, ears=False)
    m.paint(both(noise_patches(3.0, 0.18, seed=15), either(above(0.9, 0.06), behind(0.1, 0.06))), DARK_ORANGE)
    body = m.snapshot()
    m.add(cone_at((0.04, -0.08, 1.02), (0.44, -0.02, 1.54), 0.38, 0.03), RED, 0.03)
    m.add(torus_at((0.03, -0.08, 1.06), 0.36, 0.075, rot=((0, 1, 0), np.radians(-10))), WHITE, 0.01)
    m.add(sphere_at((0.48, -0.01, 1.57), 0.10), WHITE, 0.01)

    def scarf(p):
        zt = p[..., 2] - F(0.22) * p[..., 1]
        return np.maximum(np.abs(zt - F(0.60)) - F(0.06), body(p) - F(0.035))

    m.add(scarf, RED, 0.005)
    m.paint(both(bands(0, -0.03, 0.10, edge=0.008), region(scarf, 0.02)), GREEN)
    end = box_at((0.30, -0.52, 0.42), (0.09, 0.03, 0.17), rounding=0.02)
    m.add(end, RED, 0.01)
    m.paint(both(bands(2, 0.28, 0.06, edge=0.006), region(end, 0.02)), GREEN)
    cat.face(eyes="happy")
    snow = Model(k=0.02)
    snow.add(sphere_at((-0.95, -0.15, 0.15), 0.15), WHITE)
    snow.add(sphere_at((-0.95, -0.15, 0.38), 0.11), WHITE)
    snow.add(cone_at((-0.95, -0.26, 0.40), (-0.95, -0.42, 0.38), 0.02, 0.004), ORANGE, 0.004)
    for sx in (-1, 1):
        snow.add(sphere_at((-0.95 + sx * 0.04, -0.25, 0.43), 0.014), BLACK, 0.002)
    for z in (0.10, 0.17, 0.24):
        snow.add(sphere_at((-0.95, -0.295, z), 0.013), BLACK, 0.002)
    return [part("body", m), part("snowman", snow, bounds=((-1.25, -0.6, -0.1), (-0.65, 0.2, 0.7)))]


def accountcat():
    """Grey tabby with a blue tie and a briefcase."""
    m = Model(k=0.05)
    cat, _ = standard_cat(m, color=GREY, ear_inner=(0.80, 0.60, 0.62))
    tabby(m, DARK_GREY, width=0.11, start=-0.42)
    m.paint(region(ellipsoid_at((0, -0.50, 0.42), (0.28, 0.18, 0.30)), 0.04), (0.82, 0.82, 0.84))

    def tie(p):  # a triangle on the chest, painted only on the front surface
        half = F(0.025) + F(0.075) * np.clip((F(0.60) - p[..., 2]) / F(0.34), 0, 1)
        return soft(np.abs(p[..., 0]) - half, 0.006) * soft(p[..., 2] - F(0.62), 0.008) * soft(F(0.24) - p[..., 2], 0.008) * before(-0.3, 0.05)(p)

    m.paint(tie, LIGHT_BLUE)
    m.paint(lambda p: soft(np.linalg.norm(p[..., [0, 2]] - _v((0, 0.64)), axis=-1) - F(0.045), 0.006) * before(-0.3, 0.05)(p), (0.35, 0.58, 0.85))
    cat.face(mouth_width=0.024)
    case = Model(k=0.01)
    case.add(box_at((0.82, -0.28, 0.24), (0.30, 0.10, 0.22), rounding=0.03), (0.45, 0.28, 0.15))
    case.add(torus_at((0.82, -0.28, 0.47), 0.10, 0.022, rot=((1, 0, 0), np.pi / 2)), (0.35, 0.20, 0.10), 0.01)
    case.add(box_at((0.82, -0.39, 0.30), (0.04, 0.012, 0.025), rounding=0.008), GOLD, 0.004)
    return [part("body", m), part("case", case, bounds=((0.4, -0.6, -0.1), (1.25, 0.1, 0.65)))]


CHARACTERS = [
    ("Mascot", mascot), ("Siamese", siamese), ("Sphynx", sphynx), ("NorwegianForest", norwegian_forest), ("Catuccino", catuccino),
    ("Wanderer", wanderer), ("DayCat", day_cat), ("InvestigatorOne", investigator_one), ("LuckyCat", lucky_cat), ("Explorer", explorer),
    ("Dozer", dozer), ("Stretcher", stretcher), ("ShowOff", show_off), ("BoxTester", box_tester), ("NatureLover", nature_lover),
    ("LargeHearted", large_hearted), ("KittyRoll", kitty_roll), ("AngelCat", angel_cat), ("DevilCat", devil_cat), ("Unimeow", unimeow),
    ("BumbleCat", bumble_cat), ("HolidayKitty", holiday_kitty), ("Accountcat", accountcat),
]

# Group scene: rows from front to back; wide props sit at row ends so nothing collides.
HANGOUT_ROWS = [
    ["Catuccino", "LuckyCat", "Mascot", "Unimeow", "AngelCat", "DevilCat", "KittyRoll"],
    ["InvestigatorOne", "HolidayKitty", "BumbleCat", "LargeHearted", "NatureLover", "Siamese", "Sphynx", "Accountcat"],
    ["Explorer", "Dozer", "NorwegianForest", "Wanderer", "DayCat", "Stretcher", "BoxTester", "ShowOff"],
]


def hangout_layout(seed=3, spacing=2.05, row_gap=1.9):
    """name -> (x, y, yaw_degrees) for the group scene."""
    rng = np.random.default_rng(seed)
    out = {}
    for r, row in enumerate(HANGOUT_ROWS):
        n = len(row)
        for i, name in enumerate(row):
            x = (i - (n - 1) / 2) * spacing + rng.uniform(-0.12, 0.12)
            y = r * row_gap + 0.05 * x * x + rng.uniform(-0.15, 0.15)
            yaw = rng.uniform(-28, 28)
            out[name] = (float(x), float(y), float(yaw))
    return out
