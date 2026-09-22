"""nodes_sdf.py - the *native* route: an SDF built entirely from Blender 5.x geometry nodes.

Nothing here runs at evaluation time; the whole distance function lives in the node tree, so every
parameter is a live slider on the modifier and the mesh updates interactively in the viewport.

Pipeline (all built-in nodes, Blender 5.2):
    Position -> Math nodes (blob ∩ gyroid) -> Field to Grid      # any field becomes a float grid
    -> Grid to Mesh -> Mesh to SDF Grid                          # round trip = proper level set
    -> SDF Grid Fillet -> Grid to Mesh -> Set Shade Smooth       # SDF-only ops need a level set

Note: Field to Grid yields a generic float grid. The SDF-specific nodes (Fillet, Offset, Boolean)
refuse it with "Input grid is not a valid level set", so the mesh round trip is required before
using them. Points to SDF Grid and Mesh to SDF Grid produce valid level sets directly.
Also: Grid to Mesh's Threshold does not default to 0. Leave it and a narrow-band level set (a few
voxels wide) has no such isosurface, so the node silently returns an empty mesh. Set it to 0.
"""
import bpy


def build_node_group(name="SDF Blob Lattice"):
    nt = bpy.data.node_groups.new(name, "GeometryNodeTree")
    nt.is_modifier = True
    iface = nt.interface
    iface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    iface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    def param(label, default, lo, hi, kind="NodeSocketFloat"):
        s = iface.new_socket(label, in_out="INPUT", socket_type=kind)
        s.default_value, s.min_value, s.max_value = default, lo, hi
        return s

    param("Resolution", 160, 16, 400, "NodeSocketInt")
    param("Blob Radius", 0.8, 0.1, 1.25)
    param("Wobble Scale", 1.6, 0.1, 10.0)
    param("Wobble Amount", 0.35, 0.0, 1.0)
    param("Gyroid Scale", 9.0, 1.0, 30.0)
    param("Gyroid Thickness", 0.09, 0.01, 0.5)
    param("Voxel Size", 0.015, 0.005, 0.1)
    param("Fillet Iterations", 3, 0, 20, "NodeSocketInt")
    param("Adaptivity", 0.1, 0.0, 1.0)

    nodes, links = nt.nodes, nt.links
    gi, go = nodes.new("NodeGroupInput"), nodes.new("NodeGroupOutput")

    def wire(sock, v):
        if isinstance(v, bpy.types.NodeSocket):
            links.new(v, sock)
        elif v is not None:
            sock.default_value = v

    def math(op, a, b=None):
        n = nodes.new("ShaderNodeMath")
        n.operation = op
        wire(n.inputs[0], a)
        wire(n.inputs[1], b)
        return n.outputs[0]

    def vmath(op, a, b=None, scale=None):
        n = nodes.new("ShaderNodeVectorMath")
        n.operation = op
        wire(n.inputs[0], a)
        wire(n.inputs[1], b)
        if scale is not None:
            wire(n.inputs["Scale"], scale)
        return n.outputs["Value"] if op in {"LENGTH", "DOT_PRODUCT", "DISTANCE"} else n.outputs["Vector"]

    P = gi.outputs
    pos = nodes.new("GeometryNodeInputPosition").outputs[0]

    # grid domain -------------------------------------------------------------------------
    topo = nodes.new("GeometryNodeCubeGridTopology")
    topo.inputs["Bounds Min"].default_value = (-1.3, -1.3, -1.3)
    topo.inputs["Bounds Max"].default_value = (1.3, 1.3, 1.3)
    for ax in "XYZ":
        links.new(P["Resolution"], topo.inputs[f"Resolution {ax}"])

    # blob: a sphere whose radius wobbles with noise --------------------------------------
    noise = nodes.new("ShaderNodeTexNoise")
    links.new(pos, noise.inputs["Vector"])
    links.new(P["Wobble Scale"], noise.inputs["Scale"])
    noise.inputs["Detail"].default_value = 3.0
    noise.inputs["Roughness"].default_value = 0.55
    wobble = math("MULTIPLY", math("SUBTRACT", noise.outputs["Fac"], 0.5), P["Wobble Amount"])
    blob = math("ADD", math("SUBTRACT", vmath("LENGTH", pos), P["Blob Radius"]), wobble)

    # gyroid lattice: |sin x cos y + sin y cos z + sin z cos x| / scale - thickness --------
    sep = nodes.new("ShaderNodeSeparateXYZ")
    links.new(vmath("SCALE", pos, scale=P["Gyroid Scale"]), sep.inputs[0])
    x, y, z = sep.outputs
    g = math("ADD", math("ADD", math("MULTIPLY", math("SINE", x), math("COSINE", y)),
                         math("MULTIPLY", math("SINE", y), math("COSINE", z))),
             math("MULTIPLY", math("SINE", z), math("COSINE", x)))
    gyroid = math("SUBTRACT", math("DIVIDE", math("ABSOLUTE", g), P["Gyroid Scale"]), P["Gyroid Thickness"])

    # intersect (max) -> float grid -> mesh -> level set -> fillet -> mesh ------------------
    f2g = nodes.new("GeometryNodeFieldToGrid")
    f2g.grid_items.new("FLOAT", "sdf")
    links.new(topo.outputs["Topology"], f2g.inputs["Topology"])
    links.new(math("MAXIMUM", blob, gyroid), f2g.inputs["sdf"])

    rough = nodes.new("GeometryNodeGridToMesh")
    rough.inputs["Threshold"].default_value = 0.0  # default is not 0: a level set's zero crossing would be missed
    links.new(f2g.outputs["sdf"], rough.inputs["Grid"])
    m2sdf = nodes.new("GeometryNodeMeshToSDFGrid")
    links.new(rough.outputs["Mesh"], m2sdf.inputs["Mesh"])
    links.new(P["Voxel Size"], m2sdf.inputs["Voxel Size"])
    m2sdf.inputs["Band Width"].default_value = 4

    fillet = nodes.new("GeometryNodeSDFGridFillet")
    links.new(m2sdf.outputs["SDF Grid"], fillet.inputs["Grid"])
    links.new(P["Fillet Iterations"], fillet.inputs["Iterations"])

    g2m = nodes.new("GeometryNodeGridToMesh")
    g2m.inputs["Threshold"].default_value = 0.0
    links.new(fillet.outputs["Grid"], g2m.inputs["Grid"])
    links.new(P["Adaptivity"], g2m.inputs["Adaptivity"])
    smooth = nodes.new("GeometryNodeSetShadeSmooth")
    links.new(g2m.outputs["Mesh"], smooth.inputs["Geometry"])
    setmat = nodes.new("GeometryNodeSetMaterial")
    links.new(smooth.outputs[0], setmat.inputs["Geometry"])
    links.new(setmat.outputs[0], go.inputs[0])

    _layout(nt)
    return nt, setmat


def _layout(nt):
    """Left-to-right layout by link depth so the tree is readable when opened."""
    depth = {n: 0 for n in nt.nodes}
    for _ in range(len(nt.nodes)):
        for l in nt.links:
            depth[l.to_node] = max(depth[l.to_node], depth[l.from_node] + 1)
    rows = {}
    for n in nt.nodes:
        i = rows.get(depth[n], 0)
        rows[depth[n]] = i + 1
        n.location = (depth[n] * 230, -i * 150)


def add_object(name="NodeSDF", material=None, location=(0, 0, 0)):
    ob = bpy.data.objects.new(name, bpy.data.meshes.new(name))
    bpy.context.scene.collection.objects.link(ob)
    ob.location = location
    mod = ob.modifiers.new("SDF", "NODES")
    mod.node_group, setmat = build_node_group()
    if material is not None:
        setmat.inputs["Material"].default_value = material
    return ob


def set_param(ob, label, value):
    """Set a modifier input by its label, e.g. set_param(ob, "Gyroid Scale", 14)."""
    mod = ob.modifiers["SDF"]
    for item in mod.node_group.interface.items_tree:
        if item.item_type == "SOCKET" and item.in_out == "INPUT" and item.name == label:
            # Blender 5.x: modifier inputs live on mod.properties.inputs, keyed by socket identifier
            getattr(mod.properties.inputs, item.identifier).value = value
            ob.update_tag()
            return
    raise KeyError(label)


def evaluated_vertex_count(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    return len(ob.evaluated_get(dg).data.vertices)
