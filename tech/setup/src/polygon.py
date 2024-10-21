import math
import time
import csv
from typing import Optional, Any

import general
import laygen


# import sys
# import re
# import timestamp
#
import logging      # in case you want to add extra logging
# import general
# import LTBfunctions
import LTBsettings
# import settings

class PolygonError(general.LTBError):
    pass


def py2round(x):
    """in Python2, the round function was to the nearest integer, and away from 
    0 when exactly in-between 2 integers."""
    return int(math.copysign(math.floor(abs(x) + 0.5), x))

def polygonround(x, grid=1):
    """polygonround(x, grid=1) does rounding of x/grid towards +infinity.
    A grid-by-grid sized polygon is in that case always rounded to the grid
    without resizing the resulting polygon. Which it would with py3 and py2
    rounding strategies."""
    return int(math.floor(x/grid + .5))*grid

def sincos90(angle):
    """sincos90(self, angle) returns sin and cos value for straiught angles
    to exact 1 and 0.
    angle must be a multiple of 90 degrees (+-0.125 degree)"""
    assert isinstance(angle, (float, int))
    assert not(.125 < angle % 90 < 89.875)

    ang = round(angle % 360 / 90)
    if ang in [0, 4]:
        sin = 0
        cos = 1
    elif ang == 1:
        sin = 1
        cos = 0
    elif ang == 2:
        sin = 0
        cos = -1
    elif ang == 3:
        sin = -1
        cos = 0
    else:
        assert False
    return sin, cos


class Layer:
    def __init__(self, name=None, leditname=None, leditpurpose=None):
        if leditname is None:
            leditname = ''
        assert isinstance(leditname, str)
        assert isinstance(leditpurpose, (type(None), str))
        if name is None:
            if leditpurpose is None:
                name = leditname
            else:
                name = leditname + '_' + leditpurpose
        assert isinstance(name, str)
        self.name = name
        self.LEditname = leditname
        self.LEditpurpose = leditpurpose

    def __str__(self):
        return (self.name + ' (L-Edit: ' + self.LEditname + ', ' +
                str(self.LEditpurpose) + ')')

    def __repr__(self):
        return ('polygon.Layer(' + repr(self.name) + ', ' + repr(self.LEditname) +
                ((', ' + repr(self.LEditpurpose)) if self.LEditpurpose is not None else '') + ')')

    def __eq__(self, other):
        return isinstance(other, Layer) and \
               self.name == other.name and \
               self.LEditname == other.LEditname and \
               self.LEditpurpose == other.LEditpurpose

    def copy(self):
        # make and return a new instance Layer that is fully separate from self
        other = Layer(self.name, self.LEditname, self.LEditpurpose)
        return other

    def export_autogen(self):
        batchtext = 'LLayer ' + self.name + ';\n'
        if self.LEditpurpose is None:
            batchtext += (self.name + ' = LLayer_Find(activefile,"' +
                          self.LEditname + '");\n')
        else:
            batchtext += (self.name + ' = LLayer_FindByNames(activefile,"' +
                          self.LEditname + '", "' + self.LEditpurpose +
                          '");\n')
        return batchtext


class Vertex:
    """Vertex is a point defined in the 2D x/y space as a list of 2 
    numeric (float/int) elements, representing x and y respectively."""

    def __init__(self, xylist):
        if not isinstance(xylist, Vertex):
            assert isinstance(xylist, list)
            assert len(xylist) == 2
            assert isinstance(xylist[0], (float, int))
            assert isinstance(xylist[1], (float, int))
            self.x = xylist[0]
            self.y = xylist[1]
        else:
            self.x = xylist.x
            self.y = xylist.y

    def __str__(self):
        return '[' + ', '.join(str(x) for x in [self.x, self.y]) + ']'

    def __repr__(self):
        return 'polygon.Vertex([' + ', '.join(str(x) for x in [self.x, self.y]) + '])'

    def __eq__(self, other):
        if not isinstance(other, Vertex):
            vother = Vertex(other)
            return self.x == vother.x and self.y == vother.y
        return self.x == other.x and self.y == other.y

    def copy(self):
        # make and return a new instance Vertex that is fully separate from self
        other = Vertex([self.x, self.y])
        return other

    def isongrid(self, grid, accuracy=0.):
        """isongrid() returns whether X and Y coordinates are on grid within a
        accuracy allows for a little offset as fraction of the gridsize.
        accuracy > .5 makes little sense."""
        assert isinstance(accuracy, float)
        xoff = self.x % grid
        yoff = self.y % grid
        xon = not (grid * accuracy < xoff < grid * (1 - accuracy))
        yon = not (grid * accuracy < yoff < grid * (1 - accuracy))
        return [xon, yon]

    def edit_ongrid(self, grid):
        self.x = polygonround(self.x, grid)
        self.y = polygonround(self.y, grid)

    # def ongridxy(self, gridx, gridy):
    #     return [py2round(self.x / gridx) * gridx, py2round(self.y / gridy) * gridy]

    def edit_mirror(self, axis, center=None):
        """edit_mirror(self, axis, center=None) edits the vertex so that the
        resulting vertex will be mirrored around the X- ,Y- or diagonal axis
        through a center point which is by default (0,0).
        axis should be one of ['X', 'Y', 'XY', '-XY']
        'X', mirroring around X-axis
        'Y', mirroring around Y-axis
        'XY', mirroring around XY-diagonal, with slope 1
        '-XY', mirroring around XY-diagonal, with slope -1
        """
        assert isinstance(axis, str)
        assert axis.upper() in ['X', 'Y', 'XY', '-XY']

        if center is None:
            center = Vertex([0, 0])
        assert isinstance(center, (Vertex, list))
        if isinstance(center, list):
            c = Vertex(center)
        else:
            c = center

        if axis.upper() == 'X':
            y = c.y - (self.y - c.y)
            x = self.x
        elif axis.upper() == 'Y':
            x = c.x - (self.x - c.x)
            y = self.y
        elif axis.upper() == 'XY':
            # (c.x-c.y) cutting point on x-axis
            x = self.y + (c.x - c.y)
            y = self.x - (c.x - c.y)
        elif axis.upper() == '-XY':
            # (c.x+c.y) cutting point on x-axis
            x = -self.y + (c.x + c.y)
            y = -self.x + (c.x + c.y)
        else:
            assert False  # shouldn't happen
        self.x = x
        self.y = y

    def edit_translate(self, vector, mult=1):
        """edit_translate(self, vector, multiplier) edits the vertex so that the
        resulting vertex will be translated along a vector * mult."""
        assert isinstance(vector, (Vertex, list))
        if isinstance(vector, list):
            vr = Vertex(vector)
        else:
            vr = vector
        # print('translate before: ' + str(self))
        self.x = self.x + vr.x * mult
        self.y = self.y + vr.y * mult
        # print('translate after: ' + str(self))

    # def edit_rotate180(self, center=None):
    #     """edit_rotate180(self, center=None) edits the vertex so that
    #     the resulting vertex will be rotated 180 degrees around a center point
    #     which is by default (0,0)."""
    #     if center is None:
    #         center = Vertex([0, 0])
    #     assert isinstance(center, (Vertex, list))
    #     if isinstance(center, list):
    #         c = Vertex(center)
    #     else:
    #         c = center
    #     self.x = -1 * self.x + c.x*2
    #     self.y = -1 * self.y + c.y*2

    def edit_rotate(self, angle, center=None, snap90=True):
        """edit_rotate(self, angle, center=None, snap90=True) edits the polygon
        so that the resulting polygon is will be rotated with a certain
        counter-clock-wise angle (degrees) around a defined center of rotation,
        which is by default (0,0).
        if snap90 is True, sin and cos are exact [-1, 0, -1] if the angle is
        90° +- 0.125°."""
        if center is None:
            center = Vertex([0, 0])
        assert isinstance(angle, (float, int))
        assert isinstance(center, (Vertex, list))
        assert isinstance(snap90, bool)
        if isinstance(center, list):
            c = Vertex(center)
        else:
            c = center

        if snap90 and not(.125 < angle % 90 < 89.875):
            sin, cos = sincos90(angle)
        else:
            sin = math.sin(math.radians(angle))
            cos = math.cos(math.radians(angle))
        xx = c.x - self.x
        yy = c.y - self.y
        xx_new = xx * cos - yy * sin
        yy_new = yy * cos + xx * sin
        self.x = c.x - xx_new
        self.y = c.y - yy_new


class Line:
    """Line is defined by a start and end Vertex."""
    def __init__(self, v0, v1):
        self.s = Vertex(v0)
        self.e = Vertex(v1)

    def __str__(self):
        return str(self.s) + '->' + str(self.e)

    def __eq__(self, other):
        if not isinstance(other, Line):
            assert len(other) == 2
            lother = Line(other[0], other[1])
            return self.s == lother.s and self.e == lother.e
        return self.s == other.s and self.e == other.e

    def __repr__(self):
        return 'polygon.Line(' + str(self.s) + ', ' + str(self.e) + ')'

    def copy(self):
        # make and return a new instance Vertex that is fully separate from self
        other = Line(self.s.copy(), self.e.copy())
        return other

    def isinxrange(self, x):
        return min(self.s.x, self.e.x) <= x <= max(self.s.x, self.e.x)

    def isinyrange(self, y):
        return min(self.s.y, self.e.y) <= y <= max(self.s.y, self.e.y)

    def isonline(self, vertex, extend=False):
        """isonline(vertex, extend=False) returns whether this vertex is exactly
        on the line
        if extend is False, also returns None if outside the line boundaries.
        """
        if not isinstance(vertex, Vertex):
            vertex = Vertex(vertex)

        if extend or (self.isinxrange(vertex.x) and self.isinyrange(vertex.y)):
            other = Line(self.s, vertex)
            return other.slope() == self.slope()
        return False

    def ispoint(self):
        return self.s.x == self.e.x and self.s.y == self.e.y

    def isorthogonal(self):
        if self.ispoint():
            return False
        return self.s.x == self.e.x or self.s.y == self.e.y

    def isdiagonal(self):
        if self.ispoint():
            return False
        return abs(self.s.x - self.e.x) == abs(self.s.y - self.e.y)

    def slope(self):
        if self.s.x != self.e.x:
            return (self.e.y - self.s.y) / (self.e.x - self.s.x)
        else:
            return None

    def invslope(self):
        if self.s.y != self.e.y:
            return (self.e.x - self.s.x) / (self.e.y - self.s.y)
        else:
            return None

    def y_atx(self, x, extend=False):
        """y_atx(x, extend=False) returns the y value of the line on the give 
        x-position. Returns None for vertical lines.
        if extend is False, also returns None if outside of the line boundaries.
        """
        if self.s.x == self.e.x:
            return None
        if not extend and not self.isinxrange(x):
            return None
        if x in (self.s.x, self.e.x):
            return self.s.y if (x == self.s.x) else self.e.y
        else:
            return self.s.y + (x - self.s.x) * self.slope()

    def x_aty(self, y, extend=False):
        """x_aty(y, extend=False) returns the x value of the line on the give 
        y-position. Returns None for horizontal lines.
        if extend is False, also returns None if outside of the line boundaries.
        """
        if self.s.y == self.e.y:
            return None
        if not extend and not self.isinyrange(y):
            return None
        if y in (self.s.y, self.e.y):
            return self.s.x if (y == self.s.y) else self.e.x
        else:
            return self.s.x + (y - self.s.y) * self.invslope()

    def edit_reverse(self):
        """edit_reverse(self) edits the line so that the
        resulting line's start and end are swapped."""
        tmp = self.s
        self.s = self.e
        self.e = tmp

    def edit_ongrid(self, grid):
        """put start and end of line on grid"""
        self.s.edit_ongrid(grid)
        self.e.edit_ongrid(grid)

    def edit_mirror(self, axis, center=None):
        """edit_mirror(self, axis, center=None) edits the line so that the
        resulting line will be mirrored around the X- ,Y- or diagonal axis
        through a center point which is by default (0,0).
        axis should be one of ['X', 'Y', 'XY', '-XY']
        'X', mirroring around X-axis
        'Y', mirroring around Y-axis
        'XY', mirroring around XY-diagonal, with slope 1
        '-XY', mirroring around XY-diagonal, with slope -1
        """
        for v in (self.s, self.e):
            v.edit_mirror(axis, center)

    def edit_translate(self, vector, mult=1):
        """edit_translate(self, vector, multiplier) edits the line so that the
        resulting line will be translated along a vector * mult."""
        for v in [self.s, self.e]:
            v.edit_translate(vector, mult)

    def fracture_ongrid_always_up(self, grid, angle45):
        """fracture line into polygon (part), where rounding halfway th grid
        happens """
        polygon = Polygon()
        other = self.copy()
        other.edit_ongrid(grid)
        if other.ispoint():
            polygon.add_vertex(other.s)
            return polygon
        if other.isorthogonal():
            polygon.add_vertex(other.s)
            polygon.add_vertex(other.e)
            return polygon

        polygon.add_vertex(other.s)
        slope = other.slope()

        if slope > 0:
            thisfloor = math.floor
            print('floor')
        else:
            thisfloor = math.ceil
            print('ceil')

        xstep = grid * (1 if other.e.x > other.s.x else -1)
        ystep = grid * (1 if other.e.y > other.s.y else -1)
        print([xstep, ystep])

        if abs(slope) > 1.:
            for xpoint in range(int(round(abs(other.e.x - other.s.x) / grid))):
                midpoint = other.s.x + (xpoint + .5) * xstep
                ymid = self.y_atx(midpoint)
                if angle45:
                    polygon.add_vertex([other.s.x + xpoint * xstep, thisfloor(ymid / grid) * grid])
                    polygon.add_vertex([other.s.x + (xpoint + 1) * xstep, thisfloor(ymid / grid) * grid + ystep])
                else:
                    polygon.add_vertex([other.s.x + xpoint * xstep, py2round(ymid / grid) * grid])
                    polygon.add_vertex([other.s.x + (xpoint + 1) * xstep, py2round(ymid / grid) * grid])
        else:
            for ypoint in range(int(round(abs(other.e.y - other.s.y) / grid))):
                midpoint = other.s.y + (ypoint + .5) * ystep
                xmid = self.x_aty(midpoint)
                if angle45:
                    polygon.add_vertex([thisfloor(xmid / grid) * grid, other.s.y + ypoint * ystep])
                    polygon.add_vertex([(thisfloor(xmid / grid)) * grid + ystep, other.s.y + (ypoint + 1) * xstep])
                else:
                    polygon.add_vertex([py2round(xmid / grid) * grid, other.s.y + ypoint * ystep])
                    polygon.add_vertex([py2round(xmid / grid) * grid, other.s.y + (ypoint + 1) * ystep])

        polygon.add_vertex(other.e)
        return polygon

    def fracture_ongrid_centered(self, grid, angle45):
        """fracture line into polygon, symmetric from the middle out."""
        if str(self) in ['[1000, -5000]->[3000, -4000]', '[4000, -3000]->[5000, -1000]']:
            verbose = True
            verbose and print('*************** ************ **********')
        else:
            verbose = False
        verbose and print('fracture_centered')
        polygon = Polygon()
        other = self.copy()
        other.edit_ongrid(grid)
        verbose and print(self)
        if other.ispoint():
            polygon.add_vertex(other.s)
            verbose and print('point')
            return polygon
        if other.isorthogonal():
            polygon.add_vertex(other.s)
            polygon.add_vertex(other.e)
            verbose and print('ortho')
            return polygon
        if other.isdiagonal():
            polygon.add_vertex(other.s)
            polygon.add_vertex(other.e)
            verbose and print('dia')
            return polygon
        verbose and print('sloped line: ', end='')

        verbose and print('other: ' + str(other))
        slope = other.slope()
        sup = slope > 0  # slope upwards (looking to it, from left to right)
        steep = abs(slope) > 1  # steep slope (delta Y > delta X)
        l2r = other.s.x < other.e.x  # from left to right
        if not l2r:
            verbose and print('L <- R, ', end='')
        else:
            verbose and print('L -> R, ', end='')
        if not sup:
            verbose and print(r'\, ', end='')
        else:
            verbose and print(r'/, ', end='')
        if not steep:
            verbose and print(r'<45°')
        else:
            verbose and print(r'>45°')

        if not l2r:
            other.edit_reverse()
            verbose and print('other after reverse: ' + str(other))
        if not sup:
            other.edit_mirror('X')
            verbose and print('other after mirrorX: ' + str(other))
        if not steep:
            other.edit_mirror('XY')
            verbose and print('other after mirrorXY: ' + str(other))

        vector = Vertex([(other.e.x + other.s.x) / 2,
                         (other.e.y + other.s.y) / 2])
        verbose and print('real center: ' + str(vector))
        offgrid = [not x for x in vector.isongrid(grid, .01)]
        vector.edit_translate([offgrid[0] * -1 * grid/2, offgrid[1] * -1 * grid/2])
        verbose and print('vector: ' + str(vector))
        other.edit_translate(vector, -1)
        verbose and print('other: ' + str(other))

        case = offgrid[0] * 1 + offgrid[1] * 2
        halfpolygon = Polygon()

        if case in ([0, 2]):
            xstart = 0
            # halfpolygon.add_vertex([0, 0])
        elif case == 1:
            xstart = 1
            halfpolygon.add_vertex([grid, 0])
        elif case == 3:
            xstart = 1
            if angle45:
                halfpolygon.add_vertex([grid, grid])
            else:
                halfpolygon.add_vertex([grid, 0])
        else:
            assert False
        verbose and print('xstart: ' + str(xstart))
        verbose and print('int(round(other.e.x / grid)): ' + str(int(round(other.e.x / grid))))
        for xpoint in range(xstart, int(round(other.e.x / grid))):
            verbose and print('xpoint: ' + str(xpoint))
            midpoint = (xpoint + .5) * grid
            verbose and print('midpoint: ' + str(midpoint))
            ymid = other.y_atx(midpoint)
            verbose and print('ymid: ' + str(ymid))
            if angle45:
                halfpolygon.add_vertex([xpoint * grid, math.floor(ymid / grid) * grid])
                halfpolygon.add_vertex([(xpoint + 1) * grid, (math.floor(ymid / grid)+1) * grid])
            else:
                halfpolygon.add_vertex([xpoint * grid, py2round(ymid / grid) * grid])
                halfpolygon.add_vertex([(xpoint + 1) * grid, py2round(ymid / grid) * grid])
        else:
            halfpolygon.add_vertex(other.e)
        verbose and print('halfpolygon: ' + str(halfpolygon))
        halfpolygon2 = halfpolygon.copy()
        halfpolygon2.edit_rotate(180, [offgrid[0] * .5 * grid, offgrid[1] * .5 * grid])
        halfpolygon2.edit_reverse()
        if case == 3 and not angle45:
            halfpolygon2.vertices[-1].edit_translate([0, -1*grid])
        halfpolygon2.extend_polygon(halfpolygon)

        halfpolygon2.edit_translate(vector)
        if not steep:
            halfpolygon2.edit_mirror('XY')
        if not sup:
            halfpolygon2.edit_mirror('X')
        if not l2r:
            halfpolygon2.edit_reverse()
        verbose and print('fractured polygon: ' + str(halfpolygon2))
        return halfpolygon2

    def fracture_ongrid_polygonround(self, grid, angle45):
        """
        returns polygon part on grid using polygonround as rounding strategy.

        returns a polygon
        """
        polygon = Polygon()
        other = self.copy()
        other.edit_ongrid(grid)
        polygon.add_vertex(other.s)
        if other.ispoint():
            return polygon
        if other.isorthogonal() or (angle45 and other.isdiagonal()):
            polygon.add_vertex(other.e)
            return polygon

        slope = self.slope()
        steep = abs(slope) > abs(1.)  # steep slope (delta Y > delta X)
        xstep = math.copysign(grid, self.e.x - self.s.x)
        ystep = math.copysign(grid, self.e.y - self.s.y)

        if steep:
            xmid = other.s.x + xstep/2
            steps = round((other.e.x-other.s.x)/xstep)
            # while self.isinxrange(xmid):
            for xcheck in range(steps):
                ymid = self.y_atx(xmid)
                if angle45:
                    v1 = Vertex([xmid-xstep/2, ymid-ystep/2])
                    v2 = Vertex([xmid+xstep/2, ymid+ystep/2])
                    if xcheck == 0 and not self.isinyrange(v1.y):
                        # can happen first time
                        v1.y = ymid + ystep / 2
                    if xcheck == steps-1 and not self.isinyrange(v2.y):
                        # can happen last time
                        v2.y = ymid - ystep/2
                else:
                    v1 = Vertex([xmid-xstep/2, ymid])
                    v2 = Vertex([xmid+xstep/2, ymid])
                polygon.add_vertex(v1)
                polygon.add_vertex(v2)
                xmid += xstep
        else:
            ymid = other.s.y + ystep/2
            steps = round((other.e.y-other.s.y)/ystep)
            # while self.isinyrange(ymid):
            for ycheck in range(steps):
                xmid = self.x_aty(ymid)
                if angle45:
                    v1 = Vertex([xmid-xstep/2, ymid-ystep/2])
                    v2 = Vertex([xmid+xstep/2, ymid+ystep/2])
                    if ycheck == 0 and not self.isinxrange(v1.x):
                        # can happen first time
                        v1.x = xmid + xstep / 2
                    if ycheck == steps-1 and not self.isinxrange(v2.x):
                        # can happen last time
                        v2.x = xmid - xstep/2
                else:
                    v1 = Vertex([xmid, ymid-ystep/2])
                    v2 = Vertex([xmid, ymid+ystep/2])
                polygon.add_vertex(v1)
                polygon.add_vertex(v2)
                ymid += ystep

        polygon.add_vertex(other.e)
        polygon.edit_ongrid(grid)
        polygon.edit_simplify()
        return polygon

    def fracture_ongrid(self, grid, angle45):
        # return self.fracture_ongrid_always_up(grid, angle45)
        # return self.fracture_ongrid_centered(grid, angle45)
        return self.fracture_ongrid_polygonround(grid, angle45)


class Polygon:
    def __init__(self, list_of_vertices=None):
        if list_of_vertices is None:
            list_of_vertices = []
        assert isinstance(list_of_vertices, (list, Polygon))
        self.vertices = []
        for i in range(len(list_of_vertices)):
            self.add_vertex(list_of_vertices[i])

    def __str__(self):
        text = 'Polygon (' + str(self.vertexcount()) + ' vertices:[ '
        if self.vertexcount() < 16:
            for i in range(self.vertexcount()):
                if i % 4 == 0:
                    text += '\n      '
                text += str(self.vertices[i]) + ', '
            text += '\n         ] )'
            return text
        else:
            for i in range(8):
                if i % 4 == 0:
                    text += '\n      '
                text += str(self.vertices[i]) + ', '
            text += '\n... , \n      '
            for i in range(-8, 0):
                if i % 4 == 0:
                    text += '\n      '
                text += str(self.vertices[i]) + ', '
            text += '\n         ] )'
            return text

    def __len__(self):
        return len(self.vertices)

    def __getitem__(self, index):
        return self.vertices[index]

    def __eq__(self, other):
        if len(self) != len(other):
            return False
        for i in range(len(self)):
            if self.vertices[i] != other[i]:
                return False
        return True

    def __repr__(self):
        return 'polygon.Polygon([' + ', '.join(str(x) for x in self.vertices) + '])'

    def isvalid(self):
        return self.vertexcount() > 2

    def copy(self):
        # make and return a new instance Polygon, with new instances of vertices
        # that are fully separate from the ones in self
        other = Polygon()
        for v in self.vertices:
            other.add_vertex(v.copy())
        return other

    def erase(self, vertexrange=None):
        if vertexrange is None:
            vertexrange = [0, self.vertexcount() - 1]
        assert isinstance(vertexrange, list)
        assert len(vertexrange) == 2
        assert all(isinstance(x, int) for x in vertexrange)
        self.vertices = self.vertices[:vertexrange[0]] + self.vertices[vertexrange[1] + 1:]

    def vertexcount(self):
        return len(self.vertices)

    def add_vertex(self, vertex):
        """add_vertex(vertex) adds vertex to the polygon.
        However, if the vertex equals the last vertex, this is omitted."""
        v = Vertex(vertex)
        if len(self.vertices) == 0 or self.vertices[-1] != v:
            self.vertices.append(v)

    def extend_polygon(self, polygon):
        self.vertices.extend(Polygon(polygon).vertices)

    def edit_reverse(self):
        """edit_reverse(self) edits the polygon so that the
        resulting polygon is the same in shape, but in opposite order."""
        self.vertices.reverse()

    def edit_mbb_origin(self):
        """edit_MBB_origin(self) edits the polygon so that the
        resulting polygon will be translated so that the Minimum Bounding Box
        around the polygon is centered around (0,0).
        returns the translation vector used"""
        # print(self.vertices)
        xmax = max([v.x for v in self.vertices])
        ymax = max([v.y for v in self.vertices])
        xmin = min([v.x for v in self.vertices])
        ymin = min([v.y for v in self.vertices])
        # print('Xmax: ' + str(xmax))
        # print('Ymax: ' + str(ymax))
        # print('Xmin: ' + str(xmin))
        # print('Ymin: ' + str(ymin))
        vector = Vertex([-1*(xmax + xmin) / 2, -1*(ymax + ymin) / 2])
        self.edit_translate(vector)
        return vector

    def edit_translate(self, vector, mult=1):
        """edit_translate(self, vector, multiplier) edits the polygon so that the
        resulting polygon will be translated along a vector * mult."""
        for v in self.vertices:
            v.edit_translate(vector, mult)

    def edit_mirror(self, axis, center=None):
        """edit_mirror(self, axis, center=None) edits the polygon so that the
        resulting polygon is will be mirrored around the X- ,Y- or diagonal axis
        through a center point which is by default (0,0).
        axis should be one of ['X', 'Y', 'XY', '-XY']
        'X', mirroring around X-axis
        'Y', mirroring around Y-axis
        'XY', mirroring around XY-diagonal, with slope 1
        '-XY', mirroring around XY-diagonal, with slope -1
        """
        for v in self.vertices:
            v.edit_mirror(axis, center)

    # def edit_rotate180(self, center=None):
    #     """edit_rotate180_origin(self, center=None) edits the polygon so that
    #     the resulting polygon is will be rotated 180 degrees around a center point
    #     which is by default (0,0)."""
    #     for v in self.vertices:
    #         v.edit_rotate180(center)

    def edit_rotate(self, angle, center=None, snap90=True):
        """edit_rotate(self, angle, center) edits the polygon so that the
        resulting polygon is will be rotated with a certain counter-clock-wise
        angle (degrees) around a defined center of rotation."""
        for v in self.vertices:
            v.edit_rotate(angle, center, snap90)

    # def edit_rotate_cache_sin_cos(self, angle, center):
    #     """edit_rotate(self, angle, center) edits the polygon so that the
    #     resulting polygon is will be rotated with a certain counter-clock-wise
    #     angle (degrees) around a defined center of rotation."""
    #     assert isinstance(angle, (float, int))
    #     assert isinstance(center, (Vertex, list))
    #     if isinstance(center, list):
    #         c = Vertex(center)
    #     else:
    #         c = center
    #
    #     cos = math.cos(math.radians(angle))
    #     sin = math.sin(math.radians(angle))
    #     for i, v in enumerate(self.vertices):
    #         xx = c.x - v.x
    #         yy = c.y - v.y
    #         xx_new = xx * cos - yy * sin
    #         yy_new = yy * cos + xx * sin
    #         self.vertices[i] = Vertex([c.x - xx_new, c.y - yy_new])

    # def duplicate_rotated(self, angle, center):
    #     """returns new polygon that is a copy of this polygon, though rotated
    #     with a certain counter-clock-wise angle around a defined center of
    #     rotation."""
    #     assert isinstance(center, (Vertex, list))
    #     if isinstance(center, list):
    #         c = Vertex(center)
    #     else:
    #         c = center
    #
    #     other = Polygon()
    #     cos = math.cos(math.radians(angle))
    #     sin = math.sin(math.radians(angle))
    #     for vertex in self.vertices:
    #         xx = c.x - vertex.x
    #         yy = c.y - vertex.y
    #         xx_new = xx * cos - yy * sin
    #         yy_new = yy * cos + xx * sin
    #         other.add_vertex([c.x - xx_new, c.y - yy_new])
    #     return other

    def edit_ongrid(self, grid):
        """edit_ongrid(self, grid) edits the polygon so that the
        resulting polygon has all vertices on grid."""
        for v in self.vertices:
            v.edit_ongrid(grid)

    def edit_fracture(self, grid, angle45=True):
        """edit_fracture(self, grid, angle45=True) edits the polygon so that the
        resulting polygon has all vertices on grid and off-grid lines in the
        original polygon are approximated with on-grid vertices on 'grid'
        accuracy. If angle45 is True, line approximation allows small 45°
        lines to exist, otherwise the line will be staircase-shaped"""
        self.edit_ongrid(grid)
        origvertices = list(self.vertices)
        vc = self.vertexcount()

        self.erase()

        for count in range(vc):
            if count == vc - 1:
                line = Line(origvertices[count], origvertices[0])
            else:
                line = Line(origvertices[count], origvertices[count + 1])
            self.extend_polygon(line.fracture_ongrid(grid, angle45))

    # def duplicate_ongrid(self, grid, angle45=True):
    #     """returns new polygon that is a copy of this polygon, though vertices
    #     are 'pixelized' on a grid matrix."""
    #     other = Polygon()
    #     vc = self.vertexcount()
    #     for count in range(vc):
    #         if count == vc:
    #             line = Line(self.vertices[count], self.vertices[0])
    #         else:
    #             line = Line(self.vertices[count], self.vertices[count + 1])
    #         other.extend_polygon(line.fracture_ongrid(grid, angle45))
    #     return other

    def edit_simplify(self):
        """removes vertices that lay exactly inbetween the previous and next vertex"""
        other = Polygon()
        vc = self.vertexcount()
        for count in range(vc):
            if count == vc-1:
                line = Line(self.vertices[count], self.vertices[0])
                overline = Line(self.vertices[count - 1], self.vertices[0])
            else:
                line = Line(self.vertices[count], self.vertices[count + 1])
                overline = Line(self.vertices[count - 1], self.vertices[count + 1])
            if line.ispoint():
                continue
            if overline.isonline(self.vertices[count]):
                continue
            other.add_vertex(self.vertices[count])
        self.vertices = other.vertices

    def export_autogen(self, polygonvariablename=None):
        if polygonvariablename is None:
            polygonvariablename = 'Polygon'
        assert isinstance(polygonvariablename, str)
        leditgrid = 1  # units/nm
        batchtext = ''
        # vc = self.vertexcount()
        for count, v in enumerate(self.vertices):
            batchtext += ('\t\t' + polygonvariablename + ' [' + str(count) +
                          '] = LPoint_Set ( ' +
                          str(int(py2round(v.x * leditgrid))) + ',' +
                          str(int(py2round(v.y * leditgrid))) + ' );\n')
        return batchtext


class LEditPolygon:
    def __init__(self, polygon=None, layer=None):
        if polygon is None:
            polygon = Polygon([])
        if layer is None:
            layer = Layer()
        assert isinstance(polygon, Polygon)
        assert isinstance(layer, Layer)

        self.polygon = polygon
        self.layer = layer

    def __str__(self):
        text = 'LEditPolygon (Layer: ' + str(self.layer.name) + ', \n'
        text += '              ' + str(self.polygon)
        text += '              )'
        return text

    def copy(self):
        # make and return a new instance Polygon, with new instances of vertices
        # and layer that are fully separate from the ones in self
        other = LEditPolygon()
        other.polygon = self.polygon.copy()
        other.layer = self.layer.copy()
        return other

    def export_autogen(self, cellname=None, polygonvariablename=None):
        if cellname is None:
            cellname = 'activecell'
        if polygonvariablename is None:
            polygonvariablename = 'Polygon'
        assert isinstance(cellname, str)
        assert isinstance(polygonvariablename, str)
        batchtext = self.polygon.export_autogen()
        vc = len(self.polygon)
        batchtext += ('\t\tLPolygon_New( ' + cellname + ', ' + self.layer.name +
                      ', ' + polygonvariablename + ', ' + str(vc) + ');\n')
        return batchtext

    # lots of operations are supposed to just do the polygon-operation, without
    # having to refer to '.polygon'
    def erase(self, vertexrange=None):
        self.polygon.erase(vertexrange)

    def vertexcount(self):
        return self.polygon.vertexcount()

    def add_vertex(self, vertex):
        self.polygon.add_vertex(vertex)

    def extend_polygon(self, polygon):
        self.polygon.extend_polygon(polygon)

    def edit_reverse(self):
        self.polygon.edit_reverse()

    def edit_mbb_origin(self):
        return self.polygon.edit_mbb_origin()

    def edit_translate(self, vector, mult=1):
        self.polygon.edit_translate(vector, mult)

    def edit_mirror(self, axis, center=None):
        self.polygon.edit_mirror(axis, center)

    def edit_rotate(self, angle, center=None, snap90=True):
        self.polygon.edit_rotate(angle, center, snap90)

    def edit_ongrid(self, grid):
        self.polygon.edit_ongrid(grid)

    def edit_fracture(self, grid, angle45=True):
        self.polygon.edit_fracture(grid, angle45)

    def edit_simplify(self):
        self.polygon.edit_simplify()

    def import_csv_lw(self, csvfilename):
        self.polygon.import_csv_lw(csvfilename)


def import_csv_lw(csvfilename):
    # for eiffel-tower pixel stuff
    halfpolygon = Polygon()
    with open(csvfilename, newline='', encoding='utf-8-sig') as f:
        dialect = csv.Sniffer().sniff(f.read(1024))
        f.seek(0)
        reader = csv.reader(f, dialect)
        headerchecked = False
        for row in reader:
            if row[0].startswith('sep='):
                # This is a way to set delimiters correct to be read in Excel
                # this is potentially existing as the very first line of a csv
                continue
            if not headerchecked:
                if len(row) == 2 and \
                        row[0].upper() == 'HEIGHT' and \
                        row[1].upper() == 'WIDTH':
                    headerchecked = True
                    continue
                else:
                    break

            if len(row) == 2:
                halfpolygon.add_vertex([float(row[1]) / 2, float(row[0])])
            else:
                print("skipped row number:" + str(row))
                continue
        else:  # for loop has finished without 'break'
            # complete the other half of the polygon on the left side of the vertical axis
            other = halfpolygon.copy()
            other.edit_mirror('Y')
            other.edit_reverse()
            halfpolygon.extend_polygon(other)
            return halfpolygon  # this is now fullpolygon


def import_csv_layer_xy(csvfilename):
    # for eiffel-tower pixel stuff
    poly = LEditPolygon()
    layer = Layer()
    with open(csvfilename, newline='', encoding='utf-8-sig') as f:
        try:
            dialect = csv.Sniffer().sniff(f.read(1024), delimiters=",;")
        except csv.Error:
            print("failed to use CSV Sniffer, I'll count and compare commas with semicolons")
            f.seek(0)
            delimcnt = f.read(1024)
            delim = ',' if delimcnt.count(',') > delimcnt.count(';') else ';'
            f.seek(0)
            reader = csv.reader(f, delimiter=delim)
        else:
            print(dialect)
            print(repr(dialect.delimiter))
            f.seek(0)
            reader = csv.reader(f, dialect)
        for row in reader:
            if row[0].startswith('sep='):
                # This is a way to set delimiters correct to be read in Excel
                # this is potentially existing as the very first line of a csv
                continue
            if row[0].startswith('Layer'):
                if poly.vertexcount() > 0:
                    poly.layer = layer
                    yield poly
                    poly.erase()
                layer = Layer(row[1], row[2])
                continue
            if len(row) == 2:
                if row[0].upper() == 'X' and row[1].upper() == 'Y':
                    if poly.vertexcount() > 0:
                        poly.layer = layer
                        yield poly
                        poly.erase()
                else:
                    poly.add_vertex([float(row[0]), float(row[1])])
            else:
                print("skipped row number :" + str(row))
                continue
        else:  # for loop has finished without 'break'
            if poly.vertexcount() > 0:
                poly.layer = layer
                yield poly
                poly.erase()


def export_autogen(allpolygons, cellname):
    assert isinstance(allpolygons, list)
    assert all(isinstance(x, LEditPolygon) for x in allpolygons)

    polygonsize = max(p.vertexcount() for p in allpolygons)
    layers = []
    for p in allpolygons:
        if p.layer not in layers:
            layers.append(p.layer)

    batchtext = "// From polygon.py\n"
    batchtext += "// Created: " + time.ctime() + ")\n\n"
    batchtext += r"""module draw_polygon
{
#include <stdlib.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <ctype.h>
#include <math.h>

#define EXCLUDE_LEDIT_LEGACY_UPI
#include <ldata.h>
//#include "X:\LEdit\technology\settings.c"
//#include "X:\LEdit\general\update2newcell.c"

"""
    batchtext += '''void layoutbatch()
{
    LFile activefile = LFile_GetVisible();
    LCell activecell = LCell_GetVisible();
    LPoint Polygon ['''
    batchtext += str(polygonsize)
    batchtext += '''];

'''
    for layer in layers:
        batchtext += layer.export_autogen()

    for p in allpolygons:
        batchtext += p.export_autogen()

    batchtext += '''
    LDisplay_Refresh();
}
}

layoutbatch();
'''
    return batchtext


def polygon_fracture(grid, angle45, infile=None, outfile=None, backup=True):
    if infile is None:
        infile = LTBsettings.laygenfilepath() + 'polygon_in.csv'
    if outfile is None:
        outfile = LTBsettings.laygenfilepath() + 'polygon_out.c'

    polygons = []
    for p in import_csv_layer_xy(infile):
        print(p.vertexcount())
        p.edit_fracture(grid, angle45)
        polygons.append(p.copy())
    batchtext = export_autogen(polygons, 'polygons')
    general.write(outfile, batchtext, backup)
    laygen.laygenstandalone2bound(outfile)


def polygon_rotate(center, angle, number, infile=None, outfile=None, backup=True):
    if infile is None:
        infile = LTBsettings.laygenfilepath() + 'polygon_in.csv'
    if outfile is None:
        outfile = LTBsettings.laygenfilepath() + 'polygon_out.c'

    polygons = []
    for p in import_csv_layer_xy(infile):
        print(p.vertexcount())
        for n in range(1, number+1):
            q = p.copy()
            q.edit_rotate(angle*n, center, snap90=True)
            polygons.append(q.copy())
    batchtext = export_autogen(polygons, 'polygons')
    general.write(outfile, batchtext, backup)
    laygen.laygenstandalone2bound(outfile)


def polygon_sunshine(x, y, r, w, ss, sw, g, n, layer=None, outfile=None, backup=True):
    for element in [x, y, r, w, ss, sw, g]:
        assert isinstance(element, float)
    for element in [n]:
        assert isinstance(element, int)
    if outfile is None:
        outfile = LTBsettings.laygenfilepath() + 'polygon_out.c'
    print('outfile: ' + repr(outfile))
    assert isinstance(outfile, str)
    if layer is None:
        layer = 'PIMP_drawing'
    assert isinstance(layer, str)
    lay = Layer(layer, layer)
    sunray = LEditPolygon(None, lay)
    sunradius = r*1000
    raywidth = w*1000

    pixelwidth = x*1000
    pixelheigth = y*1000
    drcwidth = sw*1000
    drcspace = ss * 1000
    grid = g*1000

    rayradius = math.sqrt((pixelwidth/2)**2+(pixelheigth/2)**2)
    if sunradius > rayradius:
        #raise PolygonError
        logging.warning('sun surface radius defined larger than able to fit in x*y.')
    alpha = math.pi/n
    arc = rayradius * alpha
    if arc < raywidth/2:
        #raise PolygonError
        logging.warning('Too many rays, or minimal width per ray too big, or total area x*y too small.')
    wbase = 2* sunradius * alpha
    if wbase < drcspace:
        #raise PolygonError
        logging.warning('width of ray at base smaller than end, sun radius too small, or too many rays.')


    invwbase = 1/wbase
    invwrayend = 1 / raywidth

    points = int((rayradius-sunradius)/drcwidth)+1
    surfacepoint = False
    for point in range(1,points+1):
        radius = sunradius + drcwidth * point
        invw = invwbase + (invwrayend - invwbase)*point/points
        thisw = 1/invw
        arc = radius * alpha
        arcfraction = (arc - thisw / 2) / arc
        vx = radius * math.cos(arcfraction * alpha)
        vy = radius * math.sin(arcfraction * alpha)

        if not surfacepoint:
            if vy > drcwidth*math.sqrt(3)/2:
                realsurface = sunradius + drcwidth * (point - .5)
                sunray.add_vertex([realsurface,0])
                if point != 1:
                    logging.warning('sun ray at base too thin to pass DRC, sun radius increased.')
                surfacepoint = True
                sunray.add_vertex([vx, vy])
        else:
            sunray.add_vertex([vx, vy])
    sunray_bottom = sunray.polygon.copy()
    sunray_bottom.edit_reverse()
    sunray_bottom.edit_mirror(axis= 'X')
    sunray.extend_polygon(sunray_bottom)

    polygons = []

    for p in range(n):
        q = sunray.copy()
        if p != 0:
            q.edit_rotate(360/n*p, [0,0], snap90=False)
        # alpha =

        q.edit_fracture(grid, True)
        polygons.append(q.copy())

    canvas = LEditPolygon(None, lay)
    xi = pixelwidth/2
    yi = pixelheigth/2
    xo = xi + drcwidth
    yo = yi + drcwidth
    canvas.extend_polygon([[-xo,-yo], [-xo,yo], [xo,yo], [xo,-yo], [-xi,-yo],
                           [-xi,-yi], [xi,-yi], [xi,yi], [-xi,yi], [-xi,-yo]])
    polygons.append(canvas)
    batchtext = export_autogen(polygons, 'polygons')
    general.write(outfile, batchtext, backup)
    laygen.laygenstandalone2bound(outfile)


def claudia3_test(infile=None, outfile=None, backup=True):
    if infile is None:
        infile = r'U:\Desktop\eiffel.csv'
    if outfile is None:
        outfile = r'L:\projects\claudia3\layout\eiffel.c'
    assert all(isinstance(x, str) for x in (infile, outfile))
    layer_nimp = Layer('nimp', 'NIMP_drawing')
    layer_pimp = Layer('pimp', 'PIMP_drawing')
    layer_err = Layer('err', 'Error Layer')
    gridq = 100
    gridr = 5
    angle45 = True
    p = LEditPolygon(None, layer_err)
    p.import_csv_lw(infile)
    allp = [p]
    q = p.copy()
    vector = q.edit_mbb_origin()
    print(vector)
    vector.edit_ongrid(gridq)
    print(vector)
    q.edit_fracture(gridq, angle45)
    q.edit_translate(vector, -1)
    q.layer = layer_pimp
    allp.append(q)
    for a in range(1, 10):
        p1 = p.copy()
        p1.edit_rotate(5 * a, [0, 0])
        allp.append(p1)
        q = p1.copy()
        vector = q.edit_mbb_origin()
        vector.edit_ongrid(gridq)
        q.edit_fracture(gridq, angle45)
        q.edit_translate(vector, -1)
        q.layer = layer_pimp
        allp.append(q)
        r = p1.copy()
        vector = r.edit_mbb_origin()
        vector.edit_ongrid(gridr)
        r.edit_fracture(gridr, angle45)
        r.edit_translate(vector, -1)
        r.layer = layer_nimp
        allp.append(r)

    batchtext = export_autogen(allp, 'eiffel')
    general.write(outfile, batchtext, backup)
    laygen.laygenstandalone2bound(outfile)


def claudia3_test2(infile=None, outfile=None, backup=True):
    if infile is None:
        infile = r'U:\Desktop\csv.csv'
    if outfile is None:
        outfile = r'L:\projects\claudia3\layout\eiffel.c'
    assert all(isinstance(x, str) for x in (infile, outfile))
    layer_nimp = Layer('nimp', 'NIMP_drawing')
    layer_pimp = Layer('pimp', 'PIMP_drawing')
    layer_err = Layer('err', 'Error Layer')
    layer_m1 = Layer('M1', 'MET1_drawing')
    layer_m2 = Layer('M2', 'MET2_drawing')
    layer_m3 = Layer('M3', 'MET3_drawing')
    layer_m4 = Layer('M4', 'MET4_drawing')
    layer_m5 = Layer('M5', 'MET5_drawing')
    grid = 100
    angle45 = True
    p = LEditPolygon(None, layer_err)
    p.import_csv_lw(infile)
    allp = [p]
    p1 = p.copy()
    p1.edit_rotate(15, [0, -5000])
    allp.append(p1)
    p2 = p1.copy()
    p2.layer = layer_m1
    vector = p2.edit_mbb_origin()
    vector.edit_ongrid(grid)
    allp.append(p2)
    p3 = p2.copy()
    p3.layer = layer_m2
    p3.edit_fracture(grid, angle45)
    allp.append(p3)
    p4 = p3.copy()
    p4.layer = layer_m3
    p4.edit_translate(vector, -1)
    allp.append(p4)

    batchtext = export_autogen(allp, 'eiffel')
    general.write(outfile, batchtext, backup)
    laygen.laygenstandalone2bound(outfile)


def argparse_setup(subparsers):
    parser_pol_frc = subparsers.add_parser(
        'polygon_fracture', help=('Creates c-file for execution in L-Edit to ' +
                                  'generate new polygons on grid with based ' +
                                  'on polygon csv.exports'))
    parser_pol_frc.add_argument(
        '-i', '--infile', default=None,
        help=('the path to the input CSV file (default: ' +
              LTBsettings.laygenfilepath() + 'polygon_in.csv)'))
    parser_pol_frc.add_argument(
        '-o', '--outfile', default=None,
        help=('the path to the output C file (default: ' +
              LTBsettings.laygenfilepath() + 'polygon_out.c)'))
    parser_pol_frc.add_argument(
        '-g', '--grid', default=None, type=float,
        help=('grid setting to which the polygon has to stick. This must be a' +
              'number. Typically the unit is nm.'))
    parser_pol_frc.add_argument(
        '-45', '--angle45', default=False, action='store_true',
        help='if set, polygoons are allowed to contain 45 degree angles')
    parser_pol_frc.add_argument(
        '--nobackup', dest='backup', default=True, action='store_false',
        help='Avoids creation of backup files of previous output files.')
    parser_pol_rot = subparsers.add_parser(
        'polygon_rotate', help=('Creates c-file for execution in L-Edit to ' +
                                'generate new polygons rotated around a given ' +
                                'point, based on polygon csv.exports'))
    parser_pol_rot.add_argument(
        '-i', '--infile', default=None,
        help=('the path to the input CSV file (default: ' +
              LTBsettings.laygenfilepath() + 'polygon_in.csv)'))
    parser_pol_rot.add_argument(
        '-o', '--outfile', default=None,
        help=('the path to the output C file (default: ' +
              LTBsettings.laygenfilepath() + 'polygon_out.c)'))
    parser_pol_rot.add_argument(
        '-c', '--center', type=float, nargs=2, metavar=('X', 'Y'),
        help=('grid setting to which the polygon has to stick. This must be a' +
              'number. Typically the unit is nm.'))
    parser_pol_rot.add_argument(
        '-n', '--number', default=None, type=int,
        help=('number of repetitions.'))
    parser_pol_rot.add_argument(
        '-a', '--angle', default=None, type=float, 
        help='angle step size')
    parser_pol_rot.add_argument(
        '--nobackup', dest='backup', default=True, action='store_false',
        help='Avoids creation of backup files of previous output files.')
    parser_pol_sun = subparsers.add_parser(
        'polygon_sunshine', help=('Creates c-file for execution in L-Edit to ' +
                                  'generate a sunshine pattern in a rectangle'))
    parser_pol_sun.add_argument(
        '-x', required=True, type=float,
        help=('the width of the pixel (micron)'))
    parser_pol_sun.add_argument(
        '-y', required=True, type=float,
        help=('the height of the pixel (micron)'))
    parser_pol_sun.add_argument(
        '-r', required=True, type=float,
        help=('the radius of the sun surface'))
    parser_pol_sun.add_argument(
        '-w', required=True, type=float,
        help=('The minimal width of the sun ray at its farthest point ' +
              '(better be >= srqt(2) * min sky space)'))
    parser_pol_sun.add_argument(
        '-ss', required=True, type=float,
        help=('The minimal space between sky regions (probably a DRC rule)'))
    parser_pol_sun.add_argument(
        '-sw', required=True, type=float,
        help=('The minimal width of sky region (probably a DRC rule)'))
    parser_pol_sun.add_argument(
        '-g', required=True, type=float,
        help=('The grid (micron)'))
    parser_pol_sun.add_argument(
        '-n', required=True, type=int,
        help=('number of sun rays.'))
    parser_pol_sun.add_argument(
        '-l', default=None,
        help=('the layer name of the sky'))
    parser_pol_sun.add_argument(
        '-o', '--outfile', default=None,
        help=('the path to the output C file (default: ' +
              LTBsettings.laygenfilepath() + 'polygon_out.c)'))
    parser_pol_sun.add_argument(
        '--nobackup', dest='backup', default=True, action='store_false',
        help='Avoids creation of backup files of previous output files.')


def argparse_eval(args):
    # make a dict of args
    dictargs = vars(args)
    print(repr(args))
    funcdict = {'polygon_fracture': (polygon_fracture,
                                     [dictargs.get('grid'),
                                      dictargs.get('angle45'),
                                      dictargs.get('infile'),
                                      dictargs.get('outfile'),
                                      dictargs.get('backup')]),
                'polygon_rotate': (polygon_rotate,
                                   [dictargs.get('center'),
                                    dictargs.get('angle'),
                                    dictargs.get('number'),
                                    dictargs.get('infile'),
                                    dictargs.get('outfile'),
                                    dictargs.get('backup')]),
                'polygon_sunshine': (polygon_sunshine,
                                     [dictargs.get('x'),
                                      dictargs.get('y'),
                                      dictargs.get('r'),
                                      dictargs.get('w'),
                                      dictargs.get('ss'),
                                      dictargs.get('sw'),
                                      dictargs.get('g'),
                                      dictargs.get('n'),
                                      dictargs.get('l'),
                                      dictargs.get('outfile'),
                                      dictargs.get('backup')])
                }
    return funcdict


if __name__ == "__main__":
    general.logsetup()
    general.myargparse(argparse_setup, argparse_eval, 'v20240312')
