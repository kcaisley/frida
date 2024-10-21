# -*- coding: utf-8 -*-
import pytest

# import pytest
import polygon


def test_py2round():
    inout = [(0, 0), (0.49999999, 0), (0.5, 1), (0.50000000001, 1), (0.9, 1),
             (0, 0), (-0.49999999, 0), (-0.5, -1), (-0.50000000001, -1), (-0.9, -1),
             (1, 1), (1.49999999, 1), (1.5, 2), (1.50000000001, 2), (1.9, 2),
             (-1, -1), (-1.49999999, -1), (-1.5, -2), (-1.50000000001, -2), (-1.9, -2),
             (2, 2), (2.49999999, 2), (2.5, 3), (2.50000000001, 3), (2.9, 3),
             (-2, -2), (-2.49999999, -2), (-2.5, -3), (-2.50000000001, -3), (-2.9, -3)]
    for i, o in inout:
        assert polygon.py2round(i) == o


def test_polygon2round():
    inout = [(0, 0), (0.49999999, 0), (0.5, 1), (0.50000000001, 1), (0.9, 1),
             (0, 0), (-0.49999999, 0), (-0.5, 0), (-0.50000000001, -1), (-0.9, -1),
             (1, 1), (1.49999999, 1), (1.5, 2), (1.50000000001, 2), (1.9, 2),
             (-1, -1), (-1.49999999, -1), (-1.5, -1), (-1.50000000001, -2), (-1.9, -2),
             (2, 2), (2.49999999, 2), (2.5, 3), (2.50000000001, 3), (2.9, 3),
             (-2, -2), (-2.49999999, -2), (-2.5, -2), (-2.50000000001, -3), (-2.9, -3)]
    for i, o in inout:
        assert polygon.polygonround(i) == o


def test_sincos90():
    inout = [(0, (0, 1)), (90, (1, 0)), (180, (0, -1)), (270, (-1, 0)), (360, (0, 1)),
             (450, (1, 0)), (540, (0, -1)), (-180, (0, -1)), (-90, (-1, 0)),
             (0.05, (0, 1)), (90.05, (1, 0)), (180.05, (0, -1)), (270.05, (-1, 0)), (360.05, (0, 1)),
             (-0.05, (0, 1)), (89.95, (1, 0)), (179.95, (0, -1)), (269.95, (-1, 0)), (359.95, (0, 1)),
             (0.125, (0, 1)), (90.125, (1, 0)), (180.125, (0, -1)), (270.125, (-1, 0)), (360.125, (0, 1))]
    for i, o in inout:
        assert polygon.sincos90(i) == o


def test_layer_init():
    lay0 = polygon.Layer()
    assert isinstance(lay0, polygon.Layer)
    assert isinstance(lay0.name, str)
    assert isinstance(lay0.LEditname, str)
    assert isinstance(lay0.LEditpurpose, (type(None)))
    assert lay0.name == ''
    assert lay0.LEditname == ''
    assert lay0.LEditpurpose is None
    lay1 = polygon.Layer('', '', '')
    assert isinstance(lay1, polygon.Layer)
    assert isinstance(lay1.name, str)
    assert isinstance(lay1.LEditname, str)
    assert isinstance(lay1.LEditpurpose, str)
    assert lay1.name == ''
    assert lay1.LEditname == ''
    assert lay1.LEditpurpose == ''
    lay2 = polygon.Layer('a', 'b', 'c')
    assert isinstance(lay2, polygon.Layer)
    assert isinstance(lay2.name, str)
    assert isinstance(lay2.LEditname, str)
    assert isinstance(lay2.LEditpurpose, str)
    assert lay2.name == 'a'
    assert lay2.LEditname == 'b'
    assert lay2.LEditpurpose == 'c'


def test_layer_eq():
    lay1 = polygon.Layer('a', 'b', 'c')
    lay2 = polygon.Layer('a', 'b', 'c')
    assert lay1 == lay2
    assert lay1 is not lay2


def test_layer_repr():
    lay1 = polygon.Layer('a', 'b')
    lay2 = eval(repr(lay1))
    assert lay1 == lay2
    assert lay1 is not lay2
    assert isinstance(lay2, polygon.Layer)
    lay1 = polygon.Layer('a', 'b', 'c')
    lay2 = eval(repr(lay1))
    assert lay1 == lay2
    assert lay1 is not lay2
    assert isinstance(lay2, polygon.Layer)


def test_layer_copy():
    lay1 = polygon.Layer('a', 'b', 'c')
    lay2 = lay1.copy()
    lay3 = lay1.copy()
    lay4 = lay1.copy()
    lay5 = lay1
    lay6 = lay2
    lay7 = lay3
    assert lay1 == lay4
    assert lay2 == lay4
    assert lay3 == lay4
    assert lay5.name == 'a'
    assert lay6.LEditname == 'b'
    assert lay7.LEditpurpose == 'c'
    lay1.name += 'f'
    assert lay1 != lay4
    lay2.LEditname += 'g'
    assert lay2 != lay4
    lay3.LEditpurpose += 'h'
    assert lay3 != lay4
    assert lay5.name == 'af'
    assert lay6.LEditname == 'bg'
    assert lay7.LEditpurpose == 'ch'


def test_vertex_init():
    v1 = polygon.Vertex([1, 2])
    assert isinstance(v1, polygon.Vertex)
    assert v1.x == 1
    assert v1.y == 2
    v2 = polygon.Vertex(v1)
    assert v2.x == v1.x
    assert v2.y == v1.y
    v1.x = 5
    assert v2.x != 5


def test_vertex_eq_copy():
    v1 = polygon.Vertex([1, 2])
    assert v1 == [1, 2]
    v2 = polygon.Vertex(v1)
    assert v1 == v2
    assert v1 is not v2
    v3 = v1.copy()
    assert v1 == v3
    assert v1 is not v3
    v4 = v1
    assert v1 == v4
    assert v1 is v4
    v1.x = 6
    assert v1 != v2
    assert v1 != v3
    assert v1 == v4


def test_vertex_repr():
    v1 = polygon.Vertex([1, 2])
    v2 = eval(repr(v1))
    assert v1 == v2
    assert v1 is not v2
    assert isinstance(v2, polygon.Vertex)


def test_rotate_180():
    inout = [([3, 3], [0, 0], [-3, -3]),
             ([-3, -3], [0, 0], [3, 3]),
             ([4, -2], [0, 0], [-4, 2]),
             ([7, 0], [3, 2], [-1, 4]),
             ([0, -1], [3, 2], [6, 5]),
             ([6, 5], [3, 2], [0, -1])]

    # deprecate edit_rotate180()
    if False:
        for i, c, o in inout:
            v = polygon.Vertex(i)
            v.edit_rotate180(c)
            assert v == o
            if c == [0, 0]:
                v = polygon.Vertex(i)
                v.edit_rotate180()
                assert v == o

    for i, c, o in inout:
        v = polygon.Vertex(i)
        v.edit_rotate(180, c)
        assert v == o
        if c == [0, 0]:
            v = polygon.Vertex(i)
            v.edit_rotate(180)
            assert v == o

    for i, c, o in inout:
        v = polygon.Vertex(i)
        v.edit_rotate(180, c, snap90=False)
        # It's not that it is not allowed to be equal, but
        # it is the case in a minority of cases. So, disabled following assert:
        # assert v != o
        # The following line fails, replacing with other approx uses
        # assert pytest.approx(o) == v
        assert pytest.approx(o[0]) == v.x
        assert pytest.approx(o[1]) == v.y
        assert pytest.approx(o) == eval(str(v))
        if c == [0, 0]:
            v = polygon.Vertex(i)
            v.edit_rotate(180, snap90=False)
            # assert v != o
            assert pytest.approx(o[0]) == v.x
            assert pytest.approx(o[1]) == v.y


def test_line_init():
    l1 = polygon.Line([1, 2], [3, 4])
    assert isinstance(l1, polygon.Line)
    assert l1.s == [1, 2]
    assert l1.e == [3, 4]
    l2 = polygon.Line(l1.s, l1.e)
    assert l2.s.x == l1.s.x
    assert l2.s.y == l1.s.y
    assert l2.e.x == l1.e.x
    assert l2.e.y == l1.e.y
    l1.s.x = 5
    assert l2.s.x != 5


def test_line_eq_copy():
    l1 = polygon.Line([1, 2], [3, 4])
    assert l1 == [[1, 2], [3, 4]]
    l2 = polygon.Line(l1.s, l1.e)
    assert l1 == l2
    assert l1 is not l2
    l3 = l1.copy()
    assert l1 == l3
    assert l1 is not l3
    l4 = l1
    assert l1 == l4
    assert l1 is l4
    l1.s.x = 6
    assert l1 != l2
    assert l1 != l3
    assert l1 == l4


def test_line_repr():
    l1 = polygon.Line([1, 2], [3, 4])
    l2 = eval(repr(l1))
    assert l1 == l2
    assert l1 is not l2
    assert isinstance(l2, polygon.Line)


def test_polygon_init():
    p1 = polygon.Polygon()
    assert isinstance(p1, polygon.Polygon)
    v1 = polygon.Vertex([1, 2])
    v2 = polygon.Vertex([3, 2])
    v3 = polygon.Vertex([2, 0])
    p2 = polygon.Polygon([v1, v2, v3])
    assert isinstance(p2, polygon.Polygon)
    p3 = polygon.Polygon([[1, 2], [3, 2], [2, 0]])
    assert isinstance(p3, polygon.Polygon)
    p4 = polygon.Polygon(p1)
    assert isinstance(p4, polygon.Polygon)


def test_polygon_len():
    p1 = polygon.Polygon()
    assert len(p1) == 0
    v1 = polygon.Vertex([1, 2])
    v2 = polygon.Vertex([3, 2])
    v3 = polygon.Vertex([2, 0])
    p2 = polygon.Polygon([v1, v2, v3])
    assert len(p2) == 3


def test_polygon_eq():
    v1 = polygon.Vertex([1, 2])
    v2 = polygon.Vertex([3, 2])
    v3 = polygon.Vertex([2, 0])
    p1 = polygon.Polygon([v1, v2, v3])
    p2 = polygon.Polygon([v1, v2, v3])
    assert p1 == p2
    assert p1 is not p2
    assert p1 == [[1, 2], [3, 2], [2, 0]]


def test_polygon_repr():
    p1 = polygon.Polygon([[1, 2], [3, 2], [2, 0]])
    p2 = eval(repr(p1))
    assert p1 == p2
    assert p1 is not p2
    assert isinstance(p2, polygon.Polygon)


def test_polygon_vcount():
    p1 = polygon.Polygon()
    assert p1.vertexcount() == 0
    v1 = polygon.Vertex([1, 2])
    v2 = polygon.Vertex([3, 2])
    v3 = polygon.Vertex([2, 0])
    p2 = polygon.Polygon([v1, v2, v3])
    assert p2.vertexcount() == 3


def test_polygon_add_v():
    p1 = polygon.Polygon()
    v1 = polygon.Vertex([1, 2])
    v2 = polygon.Vertex([3, 2])
    v3 = polygon.Vertex([2, 0])
    p1.add_vertex(v1)
    p1.add_vertex(v2)
    p1.add_vertex(v3)
    assert p1.vertexcount() == 3
    # check that vertices become independent, if not, this could lead to
    # annoying bugs.
    p2 = polygon.Polygon([v1, v2, v3])
    assert p2.vertexcount() == 3
    vertex_1_x = p1.vertices[0].x
    vertex_2_x = p1.vertices[0].x
    assert vertex_1_x == 1
    assert vertex_2_x == 1
    v1.x = 5
    vertex_1_x = p1.vertices[0].x
    vertex_2_x = p1.vertices[0].x
    assert vertex_1_x == 1
    assert vertex_2_x == 1


def test_polygon_extend_p():
    p1 = polygon.Polygon()
    v1 = polygon.Vertex([1, 2])
    v2 = polygon.Vertex([3, 2])
    v3 = polygon.Vertex([2, 0])
    p2 = polygon.Polygon([v1, v2, v3])
    p1.extend_polygon(p2)
    # check that vertices become independent, if not, this could lead to
    # annoying bugs.
    assert p1.vertexcount() == 3
    vertex_1_x = p1.vertices[0].x
    vertex_2_x = p2.vertices[0].x
    assert vertex_1_x == 1
    assert vertex_2_x == 1
    v1.x = 5
    vertex_1_x = p1.vertices[0].x
    vertex_2_x = p2.vertices[0].x
    assert vertex_1_x == 1
    assert vertex_2_x == 1
    p2.vertices[0].x = 5
    vertex_1_x = p1.vertices[0].x
    vertex_2_x = p2.vertices[0].x
    assert vertex_1_x == 1
    assert vertex_2_x == 5


def test_polygon_simplify():
    inout = (([[1, 1], [2, 2], [3, 3]], [[1, 1], [3, 3]]),
             ([[1, 1], [2, 2], [2, 2], [2, 0]], [[1, 1], [2, 2], [2, 0]]),
             ([[1, 1], [2, 2], [2, 0], [1, 1]], [[1, 1], [2, 2], [2, 0]]),
             ([[1, 1], [2, 2], [2, 0], [-1, -1]], [[2, 2], [2, 0], [-1, -1]]),
             ([[1, 1], [2, 2], [2, 0], [-1, -1]], [[2, 2], [2, 0], [-1, -1]]),
             )
    for i, o in inout:
        p1 = polygon.Polygon(i)
        p1.edit_simplify()
        assert p1 == o


def test_polygon_mbb():
    inout = (([[1, 1], [1, 3], [3, 3], [3, 1]],
              [[-1, -1], [-1, 1], [1, 1], [1, -1]],
              [-2, -2]),
             ([[-3, -3], [-3, -1], [-1, -1], [-1, -3]],
              [[-1, -1], [-1, 1], [1, 1], [1, -1]],
              [2, 2])
             )

    for i, o, v in inout:
        p = polygon.Polygon(i)
        vector = p.edit_mbb_origin()
        assert p == o
        assert vector == v
    # vector.edit_ongrid(gridq)
    # poly = [[1900, 1200],
    #         [2000, 1700],
    #         [2500, 2600],
    #         [3300, 3400],
    #         [4300, 4200],
    #         [4500, 5100],
    #         [1100, 6000],
    #         [ 900, 5100],
    #         [1300, 3900],
    #         [1600, 2800],
    #         [1600, 1800],
    #         [1400, 1300]
    #         ]
    # vector = q.edit_mbb_origin()


def linefortest(point):
    """returns polygon.Line, with start (0,0) and end of (x,y) where:
    x and y are one of [0,1,2,3,4,7,8,9]
    x is thatlist[point % 7]
    y is thatlist[floor(point / 7)]

    Y
    ^
    .56.57.58.59.60.  .  .61.62.63
    .48.49.50.51.52.  .  .53.54.55
    .40.41.42.43.44.  .  .45.46.47
    .  .  .  .  .  .  .  .  .  .
    .  .  .  .  .  .  .  .  .  .
    .32.33.34.35.36.  .  .37.38.39
    .24.25.26.27.28.  .  .29.30.31
    .16.17.18.19.20.  .  .21.22.23
    .8 .9 .10.11.12.  .  .13 14.15
    .0 .1 .2 .3 .4 .  .  .5 .6 .7  > X
    """
    thatlist = [0, 1, 2, 3, 4, 7, 8, 9]
    x = thatlist[point % len(thatlist)]
    y = thatlist[int(point / len(thatlist))]
    return polygon.Line([0, 0], [x, y])


def test_line_fracture_ends_old():
    ins = (([0, 0], [800, 400]),
           ([0, 0], [400, 800]),
           ([0, 0], [-400, 800]),
           ([0, 0], [-800, 400]),
           ([0, 0], [-800, -400]),
           ([0, 0], [-400, -800]),
           ([0, 0], [400, -800]),
           ([0, 0], [800, -400]),
           ([0, 0], [800, -400]),
           ([0, 0], [8000, -400]),
           )
    for s, e in ins:
        l1 = polygon.Line(s, e)
        grid = 100
        p = l1.fracture_ongrid_centered(grid, True)
        assert isinstance(p, polygon.Polygon)
        assert p[0] == s
        assert p[-1] == e


def test_line_fracture_ends():
    ins = [linefortest(x) for x in range(64)]
    fracturefunctions = [polygon.Line.fracture_ongrid_centered,
                         polygon.Line.fracture_ongrid_always_up,
                         polygon.Line.fracture_ongrid
                         ]
    for ff in fracturefunctions:
        print(ff)
        for l1 in ins:
            print("l1: " + str(l1))
            s = l1.s
            e = l1.e
            grid = 1
            p = ff(l1, grid, True)
            assert isinstance(p, polygon.Polygon)
            assert p[0] == s
            assert p[-1] == e


def test_line_fracture_v_ongrid():
    """Symmetry cannot be a requirement, it will fail on 90°, (0,0),(1,1) in the long run
    for 45° angles, the issue raises at (0,0),(1,2)"""
    ins = [linefortest(x) for x in range(64)]


def test_line_fracture_check():
    inout = (([0, 0], [400, 800],
              [[0, 0], [100, 100], [100, 200],
               [200, 300], [200, 500], [300, 600],
               [300, 700], [400, 800]]),
             )
    for s, e, o in inout:
        l1 = polygon.Line(s, e)
        grid = 100
        p = l1.fracture_ongrid_centered(grid, True)
        assert isinstance(p, polygon.Polygon)
        assert p == o
