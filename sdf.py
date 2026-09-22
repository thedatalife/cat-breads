"""sdf.py - a small numpy signed-distance-field toolkit for Blender 5.x.

Conventions
  * points  p : float32 array of shape (N, 3)
  * distance  : float32 array of shape (N,), negative inside the surface
  * everything is vectorised; compose functions freely, then call mesh()/add_object()

Meshing uses the OpenVDB module that ships inside Blender's Python (import openvdb),
so no extra packages are needed. Works headless (blender -b --python ...) and inside
a live Blender session (e.g. via the Blender MCP execute_blender_code tool).
"""
import functools
import numpy as np

F = np.float32


def _v(x):
    return np.asarray(x, dtype=F)


def _len(v):
    return np.sqrt(np.einsum("...i,...i->...", v, v))


# --------------------------------------------------------------------------- primitives
def sphere(p, r=1.0, center=(0, 0, 0)):
    return _len(p - _v(center)) - F(r)


def box(p, size, center=(0, 0, 0)):
    """size = half extents."""
    q = np.abs(p - _v(center)) - _v(size)
    return _len(np.maximum(q, 0)) + np.minimum(q.max(axis=-1), 0)


def rounded_box(p, size, radius, center=(0, 0, 0)):
    return box(p, _v(size) - F(radius), center) - F(radius)


def ellipsoid(p, radii, center=(0, 0, 0)):
    r = _v(radii)
    q = p - _v(center)
    k0 = _len(q / r)
    k1 = _len(q / (r * r))
    return k0 * (k0 - 1) / np.maximum(k1, F(1e-7))


def torus(p, R, r, center=(0, 0, 0)):
    """Ring of radius R around the z axis, tube radius r."""
    q = p - _v(center)
    a = np.hypot(q[..., 0], q[..., 1]) - F(R)
    return np.hypot(a, q[..., 2]) - F(r)


def capsule(p, a, b, r):
    a, b = _v(a), _v(b)
    pa, ba = p - a, b - a
    h = np.clip((pa @ ba) / float(ba @ ba), 0, 1).astype(F)
    return _len(pa - ba * h[..., None]) - F(r)


def cone_capsule(p, a, b, ra, rb):
    """Capsule whose radius tapers from ra at a to rb at b (approximate SDF)."""
    a, b = _v(a), _v(b)
    pa, ba = p - a, b - a
    h = np.clip((pa @ ba) / float(ba @ ba), 0, 1).astype(F)
    return _len(pa - ba * h[..., None]) - (F(ra) + (F(rb) - F(ra)) * h)


def cylinder(p, r, half_height, center=(0, 0, 0)):
    q = p - _v(center)
    d = np.stack([np.hypot(q[..., 0], q[..., 1]) - F(r), np.abs(q[..., 2]) - F(half_height)], -1)
    return np.minimum(d.max(-1), 0) + _len(np.maximum(d, 0))


def plane(p, normal=(0, 0, 1), offset=0.0):
    n = _v(normal)
    n = n / np.linalg.norm(n)
    return p @ n - F(offset)


# --------------------------------------------------------------------------- TPMS lattices
# Triply periodic minimal surfaces. Approximate distances, which is fine for meshing.
def gyroid(p, scale=6.0, thickness=0.1):
    q = p * F(scale)
    x, y, z = q[..., 0], q[..., 1], q[..., 2]
    g = np.sin(x) * np.cos(y) + np.sin(y) * np.cos(z) + np.sin(z) * np.cos(x)
    return np.abs(g) / F(scale) - F(thickness)


def schwarz_p(p, scale=6.0, thickness=0.1):
    q = p * F(scale)
    g = np.cos(q[..., 0]) + np.cos(q[..., 1]) + np.cos(q[..., 2])
    return np.abs(g) / F(scale) - F(thickness)


def schwarz_d(p, scale=6.0, thickness=0.1):
    q = p * F(scale)
    sx, sy, sz = np.sin(q[..., 0]), np.sin(q[..., 1]), np.sin(q[..., 2])
    cx, cy, cz = np.cos(q[..., 0]), np.cos(q[..., 1]), np.cos(q[..., 2])
    g = sx * sy * sz + sx * cy * cz + cx * sy * cz + cx * cy * sz
    return np.abs(g) / F(scale) - F(thickness)


# --------------------------------------------------------------------------- combinators
def union(*ds):
    return functools.reduce(np.minimum, ds)


def intersect(*ds):
    return functools.reduce(np.maximum, ds)


def subtract(a, b):
    """a minus b."""
    return np.maximum(a, -b)


def smooth_union(a, b, k):
    k = F(k)
    h = np.clip(F(0.5) + F(0.5) * (b - a) / k, 0, 1)
    return b + (a - b) * h - k * h * (1 - h)


def smooth_intersect(a, b, k):
    k = F(k)
    h = np.clip(F(0.5) - F(0.5) * (b - a) / k, 0, 1)
    return b + (a - b) * h + k * h * (1 - h)


def smooth_subtract(a, b, k):
    """a minus b with a rounded seam."""
    k = F(k)
    h = np.clip(F(0.5) - F(0.5) * (b + a) / k, 0, 1)
    return a + (-b - a) * h + k * h * (1 - h)


def shell(d, thickness):
    """Hollow a solid into a surface skin of the given thickness."""
    return np.abs(d) - F(thickness)


def inflate(d, r):
    return d - F(r)


# --------------------------------------------------------------------------- domain operators
def translate(p, v):
    return p - _v(v)


def rotate_vec(v, axis, angle):
    k = _v(axis)
    k = k / np.linalg.norm(k)
    v = _v(v)
    c, s = np.cos(angle), np.sin(angle)
    return (v * c + np.cross(k, v) * s + k * (k @ v) * (1 - c)).astype(F)


def rotate(p, axis, angle):
    """Rotate the *shape* by angle (radians) about axis through the origin."""
    k = _v(axis)
    k = k / np.linalg.norm(k)
    c, s = F(np.cos(-angle)), F(np.sin(-angle))
    return p * c + np.cross(k, p) * s + k * (p @ k)[..., None] * (1 - c)


def twist(p, rate):
    """Twist about z: rotation angle grows linearly with height."""
    a = F(rate) * p[..., 2]
    c, s = np.cos(a), np.sin(a)
    x = c * p[..., 0] - s * p[..., 1]
    y = s * p[..., 0] + c * p[..., 1]
    return np.stack([x, y, p[..., 2]], -1)


def bend(p, rate):
    """Bend along x (curls the x axis around y)."""
    a = F(rate) * p[..., 0]
    c, s = np.cos(a), np.sin(a)
    x = c * p[..., 0] - s * p[..., 2]
    z = s * p[..., 0] + c * p[..., 2]
    return np.stack([x, p[..., 1], z], -1)


def repeat(p, period):
    """Infinite tiling of the domain."""
    per = _v(period)
    return np.mod(p + per * F(0.5), per) - per * F(0.5)


def mirror(p, axes=(1, 1, 1)):
    q = p.copy()
    for i, m in enumerate(axes):
        if m:
            q[..., i] = np.abs(q[..., i])
    return q


def warp(p, amplitude, frequency, seed=0, octaves=1):
    """Domain warp by vector noise: the single most useful 'make it organic' knob."""
    return p + F(amplitude) * noise_vec3(p * F(frequency), seed=seed, octaves=octaves)


def fibonacci_sphere(n):
    i = np.arange(n) + 0.5
    phi = np.arccos(1 - 2 * i / n)
    theta = np.pi * (1 + 5 ** 0.5) * i
    return np.stack([np.cos(theta) * np.sin(phi), np.sin(theta) * np.sin(phi), np.cos(phi)], -1).astype(F)


# --------------------------------------------------------------------------- noise
_GRAD = np.array(
    [[1, 1, 0], [-1, 1, 0], [1, -1, 0], [-1, -1, 0], [1, 0, 1], [-1, 0, 1], [1, 0, -1], [-1, 0, -1],
     [0, 1, 1], [0, -1, 1], [0, 1, -1], [0, -1, -1], [1, 1, 0], [-1, 1, 0], [0, -1, 1], [0, -1, -1]], F)


@functools.lru_cache(maxsize=64)
def _perm(seed):
    p = np.random.default_rng(seed).permutation(256).astype(np.int32)
    return np.concatenate([p, p])


def perlin3(p, seed=0):
    """Classic 3D Perlin gradient noise, vectorised. Output roughly in [-1, 1]."""
    perm = _perm(int(seed))
    pi = np.floor(p)
    pf = (p - pi).astype(F)
    pi = pi.astype(np.int32) & 255
    X, Y, Z = pi[..., 0], pi[..., 1], pi[..., 2]
    fx, fy, fz = pf[..., 0], pf[..., 1], pf[..., 2]

    def fade(t):
        return t * t * t * (t * (t * F(6) - F(15)) + F(10))

    def grad(h, x, y, z):
        g = _GRAD[h & 15]
        return g[..., 0] * x + g[..., 1] * y + g[..., 2] * z

    def lerp(a, b, t):
        return a + t * (b - a)

    u, v, w = fade(fx), fade(fy), fade(fz)
    A = perm[X] + Y
    B = perm[X + 1] + Y
    AA, AB = perm[A] + Z, perm[A + 1] + Z
    BA, BB = perm[B] + Z, perm[B + 1] + Z
    x1 = lerp(grad(perm[AA], fx, fy, fz), grad(perm[BA], fx - 1, fy, fz), u)
    x2 = lerp(grad(perm[AB], fx, fy - 1, fz), grad(perm[BB], fx - 1, fy - 1, fz), u)
    x3 = lerp(grad(perm[AA + 1], fx, fy, fz - 1), grad(perm[BA + 1], fx - 1, fy, fz - 1), u)
    x4 = lerp(grad(perm[AB + 1], fx, fy - 1, fz - 1), grad(perm[BB + 1], fx - 1, fy - 1, fz - 1), u)
    return lerp(lerp(x1, x2, v), lerp(x3, x4, v), w).astype(F)


def fbm3(p, octaves=3, lacunarity=2.0, gain=0.5, seed=0):
    total, amp, freq, norm = 0, F(1), F(1), F(0)
    for i in range(octaves):
        total = total + amp * perlin3(p * freq + F(17.31 * i), seed + i)
        norm += amp
        amp *= F(gain)
        freq *= F(lacunarity)
    return total / norm


def noise_vec3(p, seed=0, octaves=1):
    return np.stack([fbm3(p, octaves, seed=seed),
                     fbm3(p + F(31.7), octaves, seed=seed + 10),
                     fbm3(p - F(17.3), octaves, seed=seed + 20)], -1)


# --------------------------------------------------------------------------- sampling + meshing
def sample(fn, bounds=(-1, 1), res=128, chunk=2_000_000):
    lo, hi = bounds
    lo, hi = np.broadcast_to(_v(lo), (3,)).copy(), np.broadcast_to(_v(hi), (3,)).copy()
    res = np.broadcast_to(np.asarray(res, int), (3,)).copy()  # an int, or one per axis
    axes = [np.linspace(lo[i], hi[i], int(res[i]), dtype=F) for i in range(3)]
    X, Y, Z = np.meshgrid(*axes, indexing="ij")
    P = np.stack([X.ravel(), Y.ravel(), Z.ravel()], -1)
    out = np.empty(len(P), F)
    for s in range(0, len(P), chunk):
        out[s:s + chunk] = fn(P[s:s + chunk])
    return out.reshape(*res), lo, (hi - lo) / (res - 1)


def _signed_volume(pts, quads, tris):
    t = np.concatenate([quads[:, [0, 1, 2]], quads[:, [0, 2, 3]], tris]) if len(quads) else tris
    a, b, c = pts[t[:, 0]], pts[t[:, 1]], pts[t[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6)


def mesh(fn, bounds=(-1, 1), res=128, adaptivity=0.0, chunk=2_000_000):
    """Evaluate fn on a grid and extract the zero isosurface with OpenVDB.

    Returns (points (n,3) float32, quads (q,4) int32, tris (t,3) int32), outward-facing.
    """
    import openvdb

    arr, lo, voxel = sample(fn, bounds, res, chunk)
    g = openvdb.FloatGrid()
    g.copyFromArray(np.ascontiguousarray(arr, dtype=F), ijk=(0, 0, 0))
    g.gridClass = openvdb.GridClass.LEVEL_SET
    g.transform = openvdb.createLinearTransform(voxelSize=1.0)  # mesh in index space ...
    pts, tris, quads = g.convertToPolygons(isovalue=0.0, adaptivity=float(adaptivity))
    pts = (np.asarray(pts, F) * voxel + lo).astype(F)  # ... then scale per axis, so bounds need not be cubic
    quads = np.asarray(quads, np.int32).reshape(-1, 4)
    tris = np.asarray(tris, np.int32).reshape(-1, 3)
    if _signed_volume(pts, quads, tris) < 0:
        quads, tris = np.ascontiguousarray(quads[:, ::-1]), np.ascontiguousarray(tris[:, ::-1])
    return pts, quads, tris


# --------------------------------------------------------------------------- Blender glue
def to_blender_mesh(name, pts, quads, tris, colors=None):
    """Build a Mesh datablock. colors: optional (n,3) array in [0,1] stored as a 'Col' attribute."""
    import bpy

    me = bpy.data.meshes.new(name)
    me.vertices.add(len(pts))
    me.vertices.foreach_set("co", np.ascontiguousarray(pts, F).ravel())
    nq, nt = len(quads), len(tris)
    loops = np.concatenate([quads.ravel(), tris.ravel()]).astype(np.int32)
    starts = np.concatenate([np.arange(nq) * 4, nq * 4 + np.arange(nt) * 3]).astype(np.int32)
    me.loops.add(len(loops))
    me.loops.foreach_set("vertex_index", loops)
    me.polygons.add(nq + nt)
    me.polygons.foreach_set("loop_start", starts)
    try:
        me.polygons.foreach_set("loop_total", np.concatenate([np.full(nq, 4), np.full(nt, 3)]).astype(np.int32))
    except Exception:
        pass  # derived automatically in Blender 4.x+
    me.update(calc_edges=True)
    me.validate(clean_customdata=False)
    try:
        me.shade_smooth()
    except Exception:
        me.polygons.foreach_set("use_smooth", np.ones(nq + nt, bool))
    if colors is not None:
        rgba = np.ones((len(pts), 4), F)
        rgba[:, :3] = np.clip(np.asarray(colors, F), 0, 1)
        me.color_attributes.new("Col", "FLOAT_COLOR", "POINT").data.foreach_set("color", rgba.ravel())
    return me


def add_object(name, fn, bounds=(-1, 1), res=128, adaptivity=0.0, smooth=(0.5, 2), collection=None, color_fn=None):
    """Mesh an SDF function and add it to the current scene. Returns the object.

    color_fn: optional points -> (n,3) rgb, evaluated at the mesh vertices and stored as vertex colours.
    """
    import bpy

    pts, quads, tris = mesh(fn, bounds, res, adaptivity)
    colors = color_fn(pts) if color_fn is not None else None
    ob = bpy.data.objects.new(name, to_blender_mesh(name, pts, quads, tris, colors))
    (collection or bpy.context.scene.collection).objects.link(ob)
    if smooth:
        mod = ob.modifiers.new("Smooth", "SMOOTH")
        mod.factor, mod.iterations = smooth
    return ob
