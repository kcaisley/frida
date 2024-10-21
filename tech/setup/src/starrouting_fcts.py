import time
import random
from matplotlib import pyplot as plt


class Layer():
    def __init__(self, name, level, Rsq):
        self.name = name
        self.level = level
        self.Rsq = Rsq

    def __eq__(self, other):
        # equality can only be the case if both are an instance of Netname
        if not isinstance(other, Layer):
            return False
        if self.name == other.name:
            return True
        return False

    def __lt__(self, other):
        # Netname is uncomparable with other types
        if not isinstance(other, Layer):
            raise TypeError("'<' not supported between instances of '" +
                            str(type(self).__name__) + "' and '" +
                            str(type(other).__name__) + "'")
        # if equal, not lower than
        if self == other:
            return False
        # IT IS NOT EQUAL

        # one unnamed net
        return self.level < other.level

    def __ne__(self, other):
        return not self == other

    def __gt__(self, other):
        return other < self

    def __ge__(self, other):
        return not self < other

    def __le__(self, other):
        return not other < self


class Layers():
    def __init__(self, name, layerlist):
        self.name = name
        self.layerlist = layerlist
        self.Rsq = r_parallel(layerlist)


class StarpointProp():
    def __init__(self, xcenter, maxwidth, space, ytop, length, layerlist):
        self.xcenter = xcenter
        self.maxwidth = maxwidth
        self.space = space
        self.ytop = ytop
        self.length = length
        self.layerlist = layerlist
        self.Rsq = r_parallel(layerlist)


class RampProp():
    def __init__(self, sp2rheight, layerlist):
        self.sp2rheight = sp2rheight
        self.layerlist = layerlist
        self.Rsq = r_parallel(layerlist)


class HighwayProp():
    def __init__(self, ytop, maxwidth, space, layerlist):
        self.ytop = ytop
        self.maxwidth = maxwidth
        self.space = space
        self.layerlist = layerlist
        self.Rsq = r_parallel(layerlist)


class LastmileProp():
    def __init__(self, ybottom, x0center, width, pitch, layerlist):
        self.ybottom = ybottom
        self.x0center = x0center
        self.width = width
        self.pitch = pitch
        self.layerlist = layerlist
        self.Rsq = r_parallel(layerlist)


class Starroute():
    def __init__(self, n, starpoint, ramp, highway, lastmile):
        self.n = n
        self.sp = starpoint
        self.ra = ramp
        self.hw = highway
        self.lm = lastmile

        self.reset()

    def reset(self):
        # Reset all varaiable parameters
        # star point rel. widths
        self.sp_rw = [0 for x in range(self.n)]
        # Highway rel. widths (for every track @ each lastmile points)
        self.hw_rw = [[0 for x in range(self.n)] for y in range(self.n)]

        # empty placeholders for calculation
        # star point widths (for each track)
        self.sp_w = [None for x in range(self.n)]
        # star point centers (for each track)
        self.sp_c = [None for x in range(self.n)]
        # last mile centers (for each track)
        self.lm_c = [None for x in range(self.n)]
        self.calc_lastmilecenters()  # actually geometrical parameter
        # highway widths (for each track @ each lm point)
        self.hw_w = [[None for x in range(self.n)] for y in range(self.n)]
        # ramp lengths (for each track)
        self.ra_l = [None for x in range(self.n)]
        # highway y-coords (for each track @ each lm point)
        self.hw_y = [[None for x in range(self.n)] for y in range(self.n)]
        # highway resistor begin (for each track @ each lm point)
        self.hw_rb = [[None for x in range(self.n)] for y in range(self.n)]
        # highway box begin (for each track @ each lm point)
        self.hw_bb = [[None for x in range(self.n)] for y in range(self.n)]
        # highway resistor end (for each track @ each lm point)
        self.hw_re = [[None for x in range(self.n)] for y in range(self.n)]
        # highway box end (for each track @ each lm point)
        self.hw_be = [[None for x in range(self.n)] for y in range(self.n)]
        # last mile lengths (for each track)
        self.lm_l = [None for x in range(self.n)]

        # clear resistance values
        self.Rsp = [0 for x in range(self.n)]
        self.Rra = [0 for x in range(self.n)]
        self.Rhw = [[0 for x in range(self.n)] for y in range(self.n)]
        self.Rhwtot = [0 for x in range(self.n)]
        self.Rlm = [0 for x in range(self.n)]
        self.Rtot = [0 for x in range(self.n)]

    def calc_starpoint(self):
        # calculate star point track centers and widths based on
        # star point relative widths
        self.sp_w = [x * self.sp.maxwidth for x in self.sp_rw]
        totalwidth = sum(self.sp_w) + (self.n-1) * self.sp.space

        # calculate track centers
        trc = []
        leftedge = self.sp.xcenter - totalwidth / 2
        for tracknr in range(self.n):
            # calculate track center from left edge (of this track)
            trc.append(leftedge + self.sp_w[tracknr]/2)
            # calculate next track left edge
            leftedge += self.sp_w[tracknr] + self.sp.space

        self.sp_c = trc

    def calc_lastmilecenters(self):
        # calculate star point track centers and widths based on
        # star point relative widths
        self.lm_c = [self.lm.x0center + self.lm.pitch * x
                     for x in range(self.n)]

    def def_middle(self):
        # define middle track (or last left)
        lastleft = -1
        firstright = self.n
        for tracknr in range(self.n):
            # calculate left side of this track's last mile
            lmleft = self.lm_c[tracknr] - self.lm.width/2
            lmrght = self.lm_c[tracknr] + self.lm.width/2

            # calculate right side of this track's star point
            spleft = self.sp_c[tracknr] - self.sp_w[tracknr]/2
            sprght = self.sp_c[tracknr] + self.sp_w[tracknr]/2
            if lmleft < spleft:
                lastleft = tracknr
            if lmrght > sprght:
                firstright = tracknr
                break    # for tracknr in range(self.n):
        if lastleft == firstright:
            # lastmile width > star point width and lastmile exceeds star point
            # track left and right
            self.middle = lastleft
            self.middledir = 2
        elif lastleft + 1 == firstright:
            # typical situation with a part fully left, part fully right
            self.middle = lastleft
            self.middledir = -1
        elif lastleft + 2 == firstright:
            # lastmile width < star point width and star point exceeds lastmile
            # track left and right
            self.middle = lastleft + 1
            self.middledir = 0
        else:
            assert False

    def calc_highwaywidths(self):
        # calculate star point track centers and widths based on
        # star point relative widths
        self.hw_w = [[x * self.hw.maxwidth for x in self.hw_rw[y]]
                     for y in range(self.n)]

    def calc_ramplengths_left(self, incl_middle):
        incl = 1 if incl_middle else 0

        ramp_start_l = self.sp.ytop - self.sp.length - self.hw.ytop
        ramp_actual_l = ramp_start_l
        for tracknr in range(self.middle + incl):
            self.ra_l[tracknr] = (ramp_actual_l +
                                  self.hw_w[tracknr][self.middle]/2)
            ramp_actual_l += self.hw_w[tracknr][self.middle] + self.hw.space

        return ramp_actual_l

    def calc_ramplengths_right(self, incl_middle):
        incl = 1 if incl_middle else 0

        ramp_start_l = self.sp.ytop - self.sp.length - self.hw.ytop
        ramp_actual_l = ramp_start_l
        for tracknr in range(self.n-1, self.middle+1 - incl, -1):
            self.ra_l[tracknr] = (ramp_actual_l +
                                  self.hw_w[tracknr][self.middle+1]/2)
            ramp_actual_l += self.hw_w[tracknr][self.middle+1] + self.hw.space

        return ramp_actual_l

    def calc_ramplengths_middle(self, actual_l):
        # if middledir == 2:  # highway width starts after actual l
        ramp_actual_l = actual_l
        if self.middledir == 0:  # ramp_actual_l equals actual_l hereafter
            ramp_actual_l -= (self.hw_w[self.middle][self.middle] +
                              self.hw.space)

        self.ra_l[self.middle] = (ramp_actual_l +
                                  self.hw_w[self.middle][self.middle]/2)

    def calc_ramplengths(self):
        # For given StarRoute geometrical properties and
        # a set parameters for star point and highway relative widths

        if self.middledir == -1:  # middle is on left side
            self.calc_ramplengths_left(True)
            self.calc_ramplengths_right(True)
        elif self.middledir == 1:  # middle is on right side
            # theoretically possible, but never defined this way in
            # def_middle()
            assert False
        # elif self.middledir == 0:
            # last mile fully in or equal to star point track
        # elif self.middledir == 2:
            # last mile exceeds star point track @ both sides
        elif self.middledir in [0, 2]:
            actual_l_left = self.calc_ramplengths_left(False)
            # TODO : test right, I think arg must be True
            actual_l_rght = self.calc_ramplengths_right(False)
            actual_l = max(actual_l_left, actual_l_rght)
            self.calc_ramplengths_middle(actual_l)
        else:
            assert False

    def calc_highwaytracks_left(self, incl_middle):
        excl = 0 if incl_middle else 1

        # print('self.hw_w: ' + str(self.hw_w))
        # print('self.hw_y: ' + str(self.hw_y))
        # find y for each highwaytrack

        # travel through tracks from middle to left
        for lmnr in range(self.middle - excl, -1, -1):
            # print('lmnr: ' + str(lmnr))
            for tracknr in range(lmnr, -1, -1):
                # print('tracknr: ' + str(tracknr))
                actual_y = self.hw.ytop
                # print('actual_y: ' + str(actual_y))
                for highertrack in range(tracknr):
                    actual_y -= self.hw_w[highertrack][lmnr] + self.hw.space
                    # print('actual_y: ' + str(actual_y))
                self.hw_y[tracknr][lmnr] = (actual_y -
                                            self.hw_w[tracknr][lmnr]/2)
            # print('self.hw_y: ' + str(self.hw_y))
        # print('self.hw_y: ' + str(self.hw_y))

        # find begin of each hwtrack
        firstlm = True
        for lmnr in range(self.middle - excl, -1, -1):
            for tracknr in range(lmnr, -1, -1):
                if firstlm:
                    # resistor begin
                    self.hw_rb[tracknr][lmnr] = self.sp_c[tracknr]
                    # box begin
                    self.hw_bb[tracknr][lmnr] = (self.sp_c[tracknr] +
                                                 self.sp_w[tracknr]/2)
                else:
                    self.hw_rb[tracknr][lmnr] = self.hw_re[tracknr][lmnr+1]
                    self.hw_bb[tracknr][lmnr] = (self.hw_re[tracknr][lmnr+1] +
                                                 self.hw_w[tracknr][lmnr+1]/2)
                if tracknr == lmnr:
                    # resistor end
                    self.hw_re[tracknr][lmnr] = self.lm_c[tracknr]
                    # box end
                    self.hw_be[tracknr][lmnr] = (self.lm_c[tracknr] -
                                                 self.lm.width/2)
                else:
                    actual_e = (self.lm_c[lmnr] - self.lm.width/2 -
                                self.hw.space)
                    for lowertrack in range(lmnr - 1, tracknr, -1):
                        actual_e -= (self.hw_w[lowertrack][lmnr] +
                                     self.hw.space)
                    self.hw_re[tracknr][lmnr] = (actual_e -
                                                 self.hw_w[tracknr][lmnr]/2)
                    self.hw_be[tracknr][lmnr] = (actual_e -
                                                 self.hw_w[tracknr][lmnr])
            firstlm = False

    def calc_highwaytracks_right(self, incl_middle):
        excl = 0 if incl_middle else 1

        # find y for each highwaytrack

        # travel through tracks from middle to right
        for lmnr in range(self.middle+1 + excl, self.n):
            for tracknr in range(lmnr, self.n):
                actual_y = self.hw.ytop
                for highertrack in range(self.n-1, tracknr, -1):
                    actual_y -= self.hw_w[highertrack][lmnr] + self.hw.space
                self.hw_y[tracknr][lmnr] = (actual_y -
                                            self.hw_w[tracknr][lmnr]/2)

        # find begin of each hwtrack
        firstlm = True
        for lmnr in range(self.middle+1 + excl, self.n):
            for tracknr in range(lmnr, self.n):
                if firstlm:
                    # resistor begin
                    self.hw_rb[tracknr][lmnr] = self.sp_c[tracknr]
                    # box begin
                    self.hw_bb[tracknr][lmnr] = (self.sp_c[tracknr] -
                                                 self.sp_w[tracknr]/2)
                else:
                    self.hw_rb[tracknr][lmnr] = self.hw_re[tracknr][lmnr-1]
                    self.hw_bb[tracknr][lmnr] = (self.hw_re[tracknr][lmnr-1] -
                                                 self.hw_w[tracknr][lmnr-1]/2)
                if tracknr == lmnr:
                    # resistor end
                    self.hw_re[tracknr][lmnr] = self.lm_c[tracknr]
                    # box end
                    self.hw_be[tracknr][lmnr] = (self.lm_c[tracknr] +
                                                 self.lm.width/2)
                else:
                    actual_e = (self.lm_c[lmnr] + self.lm.width/2 +
                                self.hw.space)
                    for lowertrack in range(lmnr + 1, tracknr):
                        actual_e += (self.hw_w[lowertrack][lmnr] +
                                     self.hw.space)
                    self.hw_re[tracknr][lmnr] = (actual_e +
                                                 self.hw_w[tracknr][lmnr]/2)
                    self.hw_be[tracknr][lmnr] = (actual_e +
                                                 self.hw_w[tracknr][lmnr])
            firstlm = False

    def calc_highwaytracks_middle(self):
        self.hw_y[self.middle][self.middle] = (self.sp.ytop - self.sp.length -
                                               self.ra_l[self.middle])

        # resistor begin
        self.hw_rb[self.middle][self.middle] = self.sp_c[self.middle]
        # resistor end
        self.hw_re[self.middle][self.middle] = self.lm_c[self.middle]

        # box begin (left side)
        self.hw_bb[self.middle][self.middle] = min(self.sp_c[self.middle] -
                                                   self.sp_w[self.middle]/2,
                                                   self.lm_c[self.middle] -
                                                   self.lm.width/2)
        self.hw_be[self.middle][self.middle] = max(self.sp_c[self.middle] +
                                                   self.sp_w[self.middle]/2,
                                                   self.lm_c[self.middle] +
                                                   self.lm.width/2)

    def calc_highwaytracks(self):
        # widths are straightforward
        self.calc_highwaywidths()

        if self.middledir == -1:  # middle is on left side
            self.calc_highwaytracks_left(True)
            self.calc_highwaytracks_right(True)
        elif self.middledir == 1:  # middle is on right side
            # theoretically possible, but never defined this way in
            # def_middle()
            assert False
        # elif middledir == 0:
            # last mile fully in or equal to star point track
        # elif middledir == 2:
            # last mile exceeds star point track @ both sides
        elif self.middledir in [0, 2]:
            self.calc_ramplengths_left(False)
            # TODO : test right, I think arg must be True
            self.calc_ramplengths_right(False)
            self.calc_highwaytracks_middle()
        else:
            assert False

    def calc_lastmilelengths(self):
        for tracknr in range(self.n):
            self.lm_l[tracknr] = self.hw_y[tracknr][tracknr] - self.lm.ybottom

    def calc_all_params(self):
        self.calc_starpoint()

        # last mile track centers
        self.calc_lastmilecenters()

        self.def_middle()

        self.calc_highwaywidths()
        self.calc_ramplengths()
        # highway track parameters (all None to initialize)
        # self.hw_w = [[None] * self.n] * self.n
        self.calc_highwaytracks()

        self.calc_lastmilelengths()

    def W_equalwidth(self):
        # each star point track equal width, relative to total width
        realspwidth = self.sp.maxwidth - (self.sp.space * (self.n - 1))
        sptrackwidth = realspwidth / self.n
        relsptrackwidth = sptrackwidth / self.sp.maxwidth
        self.sp_rw = [relsptrackwidth] * self.n

        # calculate star point track centers (and widths)
        # self.sp_c =
        self.calc_starpoint()
        # each highway track equal width,
        # highest tracks/hw (either left or right) defines width

        left = 0
        right = 0
        for tracknr in range(self.n):
            # calculate sides of this track's last mile
            lmleft = self.lm_c[tracknr] - self.lm.width/2
            lmrght = self.lm_c[tracknr] + self.lm.width/2

            # calculate sides of this track's star point
            spleft = self.sp_c[tracknr] - self.sp_w[tracknr]/2
            sprght = self.sp_c[tracknr] + self.sp_w[tracknr]/2
            if lmleft < spleft:
                left += 1
            if lmrght > sprght:
                right += 1
        maxtracks_lr = max(left, right)
        realhwwidth = self.hw.maxwidth - (self.hw.space * (maxtracks_lr - 1))
        hwtrackwidth = realhwwidth / maxtracks_lr
        relhwtrackwidth = hwtrackwidth / self.hw.maxwidth
        self.hw_rw = [[relhwtrackwidth] * self.n] * self.n

        allparams = [list(self.sp_rw)]
        for tracknr in range(self.n):
            allparams.append(list(self.hw_rw[tracknr]))
        return allparams

    def W_set_allparams(self, allparams):
        self.sp_rw = allparams[0]
        self.hw_rw = allparams[1:]

    def R_evaluate(self, verbose=False):
        for tracknr in range(self.n):
            # L/W * Rsq
            self.Rsp[tracknr] = (self.sp.length / self.sp_w[tracknr] *
                                 self.sp.Rsq)
            self.Rra[tracknr] = (self.ra_l[tracknr] / self.sp_w[tracknr] *
                                 self.ra.Rsq)
            for lmnr in range(self.n):
                if None not in [self.hw_rb[tracknr][lmnr],
                                self.hw_re[tracknr][lmnr]]:
                    L = abs(self.hw_re[tracknr][lmnr] -
                            self.hw_rb[tracknr][lmnr])
                    self.Rhw[tracknr][lmnr] = (L / self.hw_w[tracknr][lmnr] *
                                               self.hw.Rsq)
                else:
                    self.Rhw[tracknr][lmnr] = 0
            self.Rhwtot[tracknr] = sum(self.Rhw[tracknr])
            self.Rlm[tracknr] = (self.lm_l[tracknr] / self.lm.width *
                                 self.lm.Rsq)
            self.Rtot[tracknr] = (self.Rsp[tracknr] + self.Rra[tracknr] +
                                  self.Rhwtot[tracknr] + self.Rlm[tracknr])
        if verbose:
            print('Rsp: ' + str([int(x*100)/100 for x in self.Rsp]))
            print('Rra: ' + str([int(x*100)/100 for x in self.Rra]))
            print('Rhwtot: ' + str([int(x*100)/100 for x in self.Rhwtot]))
            print('Rlm: ' + str([int(x*100)/100 for x in self.Rlm]))
            print('Rtot: ' + str([int(x*100)/100 for x in self.Rtot]))

    def plot(self):
        xb = []
        xe = []
        yb = []
        ye = []
        for tracknr in range(self.n):
            # star point
            xb.append(self.sp_c[tracknr])
            yb.append(self.sp.ytop)
            xe.append(self.sp_c[tracknr])
            ye.append(self.sp.ytop - self.sp.length)
            # high way
            for lmnr in range(self.n):
                if None not in [self.hw_rb[tracknr][lmnr],
                                self.hw_re[tracknr][lmnr]]:
                    xb.append(self.hw_rb[tracknr][lmnr])
                    yb.append(self.hw_y[tracknr][lmnr])
                    xe.append(self.hw_re[tracknr][lmnr])
                    ye.append(self.hw_y[tracknr][lmnr])
            # last mile
            xb.append(self.lm_c[tracknr])
            yb.append(self.lm.ybottom)
            xe.append(self.lm_c[tracknr])
            ye.append(self.hw_y[tracknr][tracknr])

        plt.plot([xb, xe], [yb, ye], '-x')

    def cost(self, verbose=False):
        e_98 = 2.775
        power = 2
        # power = 3
        Rsum = sum(self.Rtot)
        Rmax = max(self.Rtot)
        Rmin = min(self.Rtot)
        Rhwmax = max(self.Rhwtot)
        Rhwmin = min(self.Rhwtot)
        if verbose:
            print('Rmax: ' + str(Rmax))
            print('Rmin: ' + str(Rmin))

        Wsp = sum(self.sp_w) + (self.n-1) * self.sp.space
        if Wsp < self.sp.maxwidth:
            Wsp_penalty = Wsp / self.sp.maxwidth * 10
        else:
            Wsp_penalty = 1 + e_98**((Wsp/self.sp.maxwidth)**power)
            Wsp_penalty = 1000 * (Wsp/self.sp.maxwidth)
        # Wsp_penalty = abs((Wsp-self.sp.maxwidth)**power)
        if verbose:
            print('Wsp: ' + str(Wsp) + '  max: ' + str(self.sp.maxwidth))
            print('Wsp_penalty: ' + str(Wsp_penalty))

        cleanup = 0
        Whw = [0] * self.n
        Whw_penalty = [0] * self.n
        Whw_totpenalty = 0
        for lmnr in range(self.n):
            for tracknr in range(self.n):
                if self.hw_y[tracknr][lmnr] is not None:
                    Whw[lmnr] += self.hw_w[tracknr][lmnr] + self.hw.space
                else:
                    cleanup += self.hw_w[tracknr][lmnr]
            Whw[lmnr] -= self.hw.space

            if Whw[lmnr] < self.hw.maxwidth:
                Whw_penalty[lmnr] = 0
            else:
                # Whw_penalty[lmnr] = (1 + e_98**(
                #                      (Whw[lmnr]/self.hw.maxwidth)**power))
                Whw_penalty[lmnr] = 1000 * (Whw[lmnr]/self.hw.maxwidth)
            if verbose:
                print('Whw[' + str(lmnr) + ']: ' + str(Whw[lmnr]) +
                      '  max: ' + str(self.hw.maxwidth))
            Whw_totpenalty += Whw_penalty[lmnr]
            # print('Whw[' + str(lmnr) + ']: ' + str(Whw[lmnr]) + '  max: ' +
            #       str(self.hw.maxwidth))
            if verbose:
                print('Whw_penalty[' + str(lmnr) + ']:' +
                      str(Whw_penalty[lmnr]))
                print('cleanup: ' + str(cleanup))

        # widths must become wider going away from middle
        # left side
        layoutcost = 0
        for tracknr in range(self.middle, -1, -1):
            width = 0
            for lmnr in range(self.middle, tracknr-1, -1):
                if self.hw_w[tracknr][lmnr]-1 < width:
                    layoutcost += (width - (self.hw_w[tracknr][lmnr]-1)) * 10
                    # layoutcost += 10
                width = self.hw_w[tracknr][lmnr]
        # right side
        for tracknr in range(self.middle + 1, self.n):
            width = 0
            for lmnr in range(self.middle, tracknr+1):
                if self.hw_w[tracknr][lmnr]-1 < width:
                    layoutcost += (width - (self.hw_w[tracknr][lmnr]-1)) * 10
                    # layoutcost += 10
                width = self.hw_w[tracknr][lmnr]

        # left side
        layoutcost2 = 0
        for lmnr in range(self.middle - 1, -1, -1):
            for tracknr in range(lmnr + 1):
                top = self.hw_y[tracknr][lmnr] + self.hw_w[tracknr][lmnr]/2
                bot = self.hw_y[tracknr][lmnr+1] - self.hw_w[tracknr][lmnr+1]/2
                if top-1 < bot:
                    layoutcost2 += (bot - (top-1)) * 10
                    # layoutcost2 += 10
        # right side
        for lmnr in range(self.middle + 2, self.n):
            for tracknr in range(self.n - 1, lmnr - 1, -1):
                top = self.hw_y[tracknr][lmnr] + self.hw_w[tracknr][lmnr]/2
                bot = self.hw_y[tracknr][lmnr-1] - self.hw_w[tracknr][lmnr-1]/2
                if top-1 < bot:
                    layoutcost2 += (bot - (top-1)) * 10
                    # layoutcost2 += 10

        Rcost = Rsum
        # Rdiffcost = (Rmax-Rmin)*1000
        Rdiff = 0
        for diff in range(self.n):
            # Rdiff += Rmax - self.Rtot[diff]
            # Rdiff += self.Rtot[diff]-Rmin
            Rdiff += abs(Rmin + (Rmax-Rmin)/2 - self.Rtot[diff])**3
        Rdiffcost = (Rdiff)*100
        Rhwdiff = 0
        for diff in range(self.n):
            # Rdiff += Rmax - self.Rtot[diff]
            # Rdiff += self.Rtot[diff]-Rmin
            Rhwdiff += abs(Rhwmin + (Rhwmax-Rhwmin)/2 - self.Rhwtot[diff])**3
        Rhwdiffcost = (Rhwdiff)*100
        cost = (Rcost + Rdiffcost + Rhwdiffcost + Wsp_penalty + layoutcost +
                layoutcost2 + Whw_totpenalty + cleanup)
        if verbose:
            print('Wsp_penalty: ' + str(Wsp_penalty))
            print('Whw_totpenalty: ' + str(Whw_totpenalty))
            print('cleanup: ' + str(cleanup))
            print('layoutcost: ' + str(layoutcost))
            print('layoutcost2: ' + str(layoutcost2))
            print('Rcost: ' + str(Rcost))
            print('Rdiffcost: ' + str(Rdiffcost))
            print('Rhwdiffcost: ' + str(Rhwdiffcost))
            print('cost: ' + str(cost))

        return cost

    def cost_for_param(self, allparams):
        self.W_set_allparams(allparams)
        self.calc_all_params()
        self.R_evaluate()
        return self.cost()

    def autogen(self, project, netname):
        now = time.strftime("%Y%m%d_%H%M%S")
        autogenfilename = ('T:\\LayoutToolbox\\projects\\' + project +
                           r'\layout\autogen\starroute_' + netname + '_' +
                           now + '.c')

        with open(autogenfilename, 'w') as agfile:
            # export header
            agfile.write(r"""// From starroute.py ()

module batch_module
{
#include <stdlib.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <ctype.h>
#include <math.h>

#define EXCLUDE_LEDIT_LEGACY_UPI
#include <ldata.h>
#include "X:\LEdit\general\globals.c"
#include "X:\LEdit\technology\project.c"
#include "S:\technologies\setup\tech2layoutparams\tech2layoutparams.c"
#include "X:\LEdit\general\snap_to_design_grid.c"
#include "X:\LEdit\general\via.c"

void layoutbatch()
{
LFile activefile;
LCell newCell;
LObject Boxlow, Boxhigh;
char info[512];
activefile = LFile_GetVisible();
""")
            cellname = "starroute_" + netname + '_' + now
            agfile.write('''
newCell = LCell_Find(activefile, "''' + cellname + '''");
if (newCell == NULL) {
    newCell  = LCell_New(activefile, "''' + cellname + '''");
''')
            for tracknr in range(self.n):
                # star point
                x0 = self.sp_c[tracknr] - self.sp_w[tracknr]/2
                y0 = self.sp.ytop
                x1 = self.sp_c[tracknr] + self.sp_w[tracknr]/2
                y1 = self.sp.ytop - self.sp.length

                for layer in self.sp.layerlist:
                    agfile.write('LBox_New(newCell, tech2layer("' +
                                 layer.name + '"), ' +
                                 str(int(100 * x0) * 10) + ', ' +
                                 str(int(100 * y0) * 10) + ', ' +
                                 str(int(100 * x1) * 10) + ', ' +
                                 str(int(100 * y1) * 10) + ');\n')

                # ramp
                x0 = self.sp_c[tracknr] - self.sp_w[tracknr]/2
                y0 = self.sp.ytop - self.sp.length
                x1 = self.sp_c[tracknr] + self.sp_w[tracknr]/2
                y1 = self.sp.ytop - self.sp.length - self.ra_l[tracknr]
                for layer in self.ra.layerlist:
                    agfile.write('LBox_New(newCell, tech2layer("' +
                                 layer.name + '"), ' +
                                 str(int(100 * x0) * 10) + ', ' +
                                 str(int(100 * y0) * 10) + ', ' +
                                 str(int(100 * x1) * 10) + ', ' +
                                 str(int(100 * y1) * 10) + ');\n')

                # star point 2 ramp
                lowlayer = min(min(self.sp.layerlist), min(self.ra.layerlist))
                highlayer = max(max(self.sp.layerlist), max(self.ra.layerlist))
                x0 = self.sp_c[tracknr] - self.sp_w[tracknr]/2
                y0 = self.sp.ytop - self.sp.length + self.ra.sp2rheight/2
                x1 = self.sp_c[tracknr] + self.sp_w[tracknr]/2
                y1 = self.sp.ytop - self.sp.length - self.ra.sp2rheight/2
                agfile.write('Boxlow = LBox_New(newCell, tech2layer("' +
                             lowlayer.name + '"), ' +
                             str(int(100 * x0) * 10) + ', ' +
                             str(int(100 * y0) * 10) + ', ' +
                             str(int(100 * x1) * 10) + ', ' +
                             str(int(100 * y1) * 10) + ');\n')
                agfile.write('Boxhigh = LBox_New(newCell, tech2layer("' +
                             highlayer.name + '"), ' +
                             str(int(100 * x0) * 10) + ', ' +
                             str(int(100 * y0) * 10) + ', ' +
                             str(int(100 * x1) * 10) + ', ' +
                             str(int(100 * y1) * 10) + ');\n')
                agfile.write('viaIntersection_2Boxes(Boxlow, Boxhigh);\n')

                # high way
                for lmnr in range(self.n):
                    if None not in [self.hw_bb[tracknr][lmnr],
                                    self.hw_be[tracknr][lmnr]]:
                        x0 = self.hw_bb[tracknr][lmnr]
                        y0 = (self.hw_y[tracknr][lmnr] -
                              self.hw_w[tracknr][lmnr]/2)
                        x1 = self.hw_be[tracknr][lmnr]
                        y1 = (self.hw_y[tracknr][lmnr] +
                              self.hw_w[tracknr][lmnr]/2)
                        for layer in self.hw.layerlist:
                            agfile.write('LBox_New(newCell, tech2layer("' +
                                         layer.name + '"), ' +
                                         str(int(100 * x0) * 10) + ', ' +
                                         str(int(100 * y0) * 10) + ', ' +
                                         str(int(100 * x1) * 10) + ', ' +
                                         str(int(100 * y1) * 10) + ');\n')

                # ramp 2 highway
                lowlayer = min(min(self.ra.layerlist), min(self.hw.layerlist))
                highlayer = max(max(self.ra.layerlist), max(self.hw.layerlist))

                if self.middledir == -1:
                    if tracknr <= self.middle:
                        ra2hwcorner = self.middle
                    else:
                        ra2hwcorner = self.middle + 1
                elif self.middledir == 0:
                    if tracknr < self.middle:
                        ra2hwcorner = self.middle - 1
                    elif tracknr > self.middle:
                        ra2hwcorner = self.middle + 1
                    elif tracknr == self.middle:
                        ra2hwcorner = self.middle
                elif self.middledir == 2:
                    ra2hwcorner = self.middle

                x0 = self.sp_c[tracknr] - self.sp_w[tracknr]/2
                y0 = (self.hw_y[tracknr][ra2hwcorner] -
                      self.hw_w[tracknr][ra2hwcorner]/2)
                x1 = self.sp_c[tracknr] + self.sp_w[tracknr]/2
                y1 = (self.hw_y[tracknr][ra2hwcorner] +
                      self.hw_w[tracknr][ra2hwcorner]/2)
                agfile.write('Boxlow = LBox_New(newCell, tech2layer("' +
                             lowlayer.name + '"), ' +
                             str(int(100 * x0) * 10) + ', ' +
                             str(int(100 * y0) * 10) + ', ' +
                             str(int(100 * x1) * 10) + ', ' +
                             str(int(100 * y1) * 10) + ');\n')
                agfile.write('Boxhigh = LBox_New(newCell, tech2layer("' +
                             highlayer.name + '"), ' +
                             str(int(100 * x0) * 10) + ', ' +
                             str(int(100 * y0) * 10) + ', ' +
                             str(int(100 * x1) * 10) + ', ' +
                             str(int(100 * y1) * 10) + ');\n')
                agfile.write('viaIntersection_2Boxes(Boxlow, Boxhigh);\n')

                # last mile
                x0 = self.lm_c[tracknr] - self.lm.width/2
                y0 = self.lm.ybottom
                x1 = self.lm_c[tracknr] + self.lm.width/2
                y1 = self.hw_y[tracknr][tracknr]
                for layer in self.lm.layerlist:
                    agfile.write('LBox_New(newCell, tech2layer("' +
                                 layer.name + '"), ' +
                                 str(int(100 * x0) * 10) + ', ' +
                                 str(int(100 * y0) * 10) + ', ' +
                                 str(int(100 * x1) * 10) + ', ' +
                                 str(int(100 * y1) * 10) + ');\n')

                # highway 2 last mile
                lowlayer = min(min(self.hw.layerlist), min(self.lm.layerlist))
                highlayer = max(max(self.hw.layerlist), max(self.lm.layerlist))
                x0 = self.lm_c[tracknr] - self.lm.width/2
                y0 = (self.hw_y[tracknr][tracknr] -
                      self.hw_w[tracknr][tracknr]/2)
                x1 = self.lm_c[tracknr] + self.lm.width/2
                y1 = (self.hw_y[tracknr][tracknr] +
                      self.hw_w[tracknr][tracknr]/2)
                agfile.write('Boxlow = LBox_New(newCell, tech2layer("' +
                             lowlayer.name + '"), ' +
                             str(int(100 * x0) * 10) + ', ' +
                             str(int(100 * y0) * 10) + ', ' +
                             str(int(100 * x1) * 10) + ', ' +
                             str(int(100 * y1) * 10) + ');\n')
                agfile.write('Boxhigh = LBox_New(newCell, tech2layer("' +
                             highlayer.name + '"), ' +
                             str(int(100 * x0) * 10) + ', ' +
                             str(int(100 * y0) * 10) + ', ' +
                             str(int(100 * x1) * 10) + ', ' +
                             str(int(100 * y1) * 10) + ');\n')
                agfile.write('viaIntersection_2Boxes(Boxlow, Boxhigh);\n')
            agfile.write('}\n}\n}\n\nlayoutbatch();\n')


def r_parallel(layerlist):
    S = 0
    for layer in layerlist:
        S += 1/layer.Rsq
    return 1/S


def printlist(array2d):
    print('[', end='')
    for x in range(len(array2d)):
        print('[', end='')
        for y in range(len(array2d[x])):
            if y+1 == len(array2d[x]):
                if array2d[x][y] is None:
                    print(' - ', end='')
                else:
                    print('{:.2f}'.format(array2d[x][y]), end='')
            else:
                if array2d[x][y] is None:
                    print(' - , ', end='')
                else:
                    print('{:.2f}, '.format(array2d[x][y]), end='')
        print(']', end='\n ')
    print(']')


def elfis2_adc():
    # DEFINE LAYERS

    #  class Layer()
    #    def __init__(self, name, level, Rsq):
    M1 = Layer("M1", 1, 0.19)
    M2 = Layer("M2", 2, 0.14)
    M3 = Layer("M3", 3, 0.14)
    M4 = Layer("M4", 4, 0.14)
    M5 = Layer("M5", 5, 0.14)
    M6 = Layer("M6", 6, 0.06)

    offset_io = 155
    # starpoint center
    VS_spc = 2610 + offset_io
    VD_spc = 2790 + offset_io

    # DEFINE GEOMETRICAL PROPERTIES

    #  class StarpointProp()
    #    def __init__(self, xcenter, maxwidth, space, ytop, length, layerlist):
    VS_sp = StarpointProp(VS_spc, 116, 1, 990, 97, [M1, M2])
    VD_sp = StarpointProp(VD_spc, 116, 1, 990, 97, [M1, M2])

    #  class RampProp()
    #    def __init__(self, sp2rheight, layerlist):
    VS_ra = RampProp(4, [M4])
    VD_ra = RampProp(4, [M4])

    #  class HighwayProp()
    #    def __init__(self, ytop, maxwidth, space, layerlist):
    VS_hw = HighwayProp(895, 70, 1, [M5, M6])
    VD_hw = HighwayProp(822, 70, 1, [M5, M6])

    #  class LastmileProp()
    #    def __init__(self, ybottom, x0center, width, pitch, layerlist):
    VS_lm = LastmileProp(750, 302.15, 6, 700, [M4])
    VD_lm = LastmileProp(750, 310.15, 6, 700, [M4])

    #  class Starroute()
    #    def __init__(self, n, starpoint, ramp, highway, lastmile):
    VSSU = Starroute(8, VS_sp, VS_ra, VS_hw, VS_lm)
    VDDU = Starroute(8, VD_sp, VD_ra, VD_hw, VD_lm)

    # LET THE BEAST GO

    VS_startparam = VSSU.W_equalwidth()
    print('VS_startparam: ')
    printlist(VS_startparam)
    granularity = 1/7000
    VS_better = hillclimb(VSSU, VS_startparam, 0 + granularity, 1, granularity)

    VD_startparam = VDDU.W_equalwidth()
    print('VD_startparam: ')
    printlist(VD_startparam)
    granularity = 1/7000
    VD_better = hillclimb(VDDU, VD_startparam, 0 + granularity, 1, granularity)

    print('VS_better: ')
    printlist(VS_better)

    print('VD_better: ')
    printlist(VD_better)

    VS_bettercost = VSSU.cost_for_param(VS_better)
    print(VS_bettercost)
    VSSU.R_evaluate(True)
    VSSU.cost(True)
    VSSU.plot()
    VSSU.autogen('elfis2', 'VSSU')

    VD_bettercost = VDDU.cost_for_param(VD_better)
    print(VD_bettercost)
    VDDU.R_evaluate(True)
    VDDU.cost(True)
    VDDU.plot()
    VDDU.autogen('elfis2', 'VDDU')

    return VSSU, VDDU


def slope(instance, initparams, x, y, minval, maxval, granularity):
    initcost = instance.cost_for_param(initparams)
    down = [lx.copy() for lx in initparams.copy()]
    up = [lx.copy() for lx in initparams.copy()]
    down[x][y] = max(minval, initparams[x][y]-granularity)
    up[x][y] = min(maxval, initparams[x][y]+granularity)
    downcost = instance.cost_for_param(down)
    upcost = instance.cost_for_param(up)
    if upcost < initcost and downcost < initcost:
        # print('local max: params[' + str(x) + '][' + str(y) + ']: ' +
        #       str(initparams[x][y]))
        dirtogo = 0
    elif upcost >= initcost and downcost >= initcost:
        # print('local min: params[' + str(x) + '][' + str(y) + ']: ' +
        #       str(initparams[x][y]))
        dirtogo = 0
    elif upcost < downcost:
        dirtogo = 1
    elif downcost < upcost:
        dirtogo = -1
    else:
        assert False
    # if dirtogo == 1 and initparams[x][y] == maxval:
    #     dirtogo = 0
    # if dirtogo == -1 and initparams[x][y] == minval:
    #     dirtogo = 0

    return dirtogo


def localhillclimb(instance, initparams, x, y, minval, maxval, granularity):
    if (maxval - minval) < 0:
        assert False
    if (maxval - minval) < granularity:
        print('gran: {}-{} < {}'.format(maxval, minval, granularity))
        print('gran: {} < {}'.format(maxval - minval, granularity))
        return initparams

    best = [lx.copy() for lx in initparams.copy()]
    # bestcost = instance.cost_for_param(best)
    bestslope = slope(instance, best, x, y, minval, maxval, granularity)
    if bestslope == 0:
        return initparams
    if bestslope == 1:
        top = [lx.copy() for lx in best.copy()]
        top[x][y] = maxval
        topslope = slope(instance, top, x, y, minval, maxval, granularity)
        if topslope in [0, 1]:
            return top

        mid = [lx.copy() for lx in best.copy()]
        mid[x][y] = best[x][y] + (top[x][y]-best[x][y])/2
        midslope = slope(instance, mid, x, y, minval, maxval, granularity)
        if midslope == 0:
            # print('seems early')
            return mid
        if midslope == -1:
            # take new point between best and mid
            newminval = best[x][y]
            newmaxval = mid[x][y]
        elif midslope == 1:
            # take new point between mid and top
            newminval = mid[x][y]
            newmaxval = top[x][y]
        newguess = [lx.copy() for lx in mid.copy()]
        newguess[x][y] = newminval + (newmaxval-newminval)/2
        return localhillclimb(instance, newguess, x, y,
                              newminval, newmaxval, granularity)

    if bestslope == -1:
        bottom = [lx.copy() for lx in best.copy()]
        bottom[x][y] = minval
        bottomslope = slope(instance, bottom, x, y, minval, maxval,
                            granularity)
        if bottomslope in [0, -1]:
            return bottom

        mid = [lx.copy() for lx in best.copy()]
        mid[x][y] = best[x][y] + (bottom[x][y]-best[x][y])/2
        midslope = slope(instance, mid, x, y, minval, maxval, granularity)
        if midslope == 0:
            # print('seems early')
            return mid
        if midslope == 1:
            # take new point between best and mid
            newminval = mid[x][y]
            newmaxval = best[x][y]
        elif midslope == -1:
            # take new point between mid and top
            newminval = bottom[x][y]
            newmaxval = mid[x][y]
        newguess = [lx.copy() for lx in mid.copy()]
        newguess[x][y] = newminval + (newmaxval-newminval)/2
        return localhillclimb(instance, newguess, x, y,
                              newminval, newmaxval, granularity)


def hillclimb(instance, initparams, minval, maxval, initgranularity):
    # instance has following methods:
    # cost_for_param((initparams)
    # initparams = 2D list

    climb = .25
    immediately = False

    best = [lx.copy() for lx in initparams.copy()]
    bestcost = instance.cost_for_param(best)
    print('bestcost: {}'.format(bestcost))

    allbest = [lx.copy() for lx in best.copy()]
    allbestcost = bestcost

    granularity = initgranularity
    allelements = []
    for x in range(len(initparams)):
        for y in range(len(initparams[x])):
            allelements.append([x, y])
    loop = 0
    for cnt in range(100):
        poplist = [lx.copy() for lx in allelements.copy()]
        if not immediately:
            atonce = [lx.copy() for lx in best.copy()]
        while len(poplist) > 0:
            x, y = poplist.pop(random.randrange(len(poplist)))
            # print('best[{}][{}] = {}  [{}]'.format(x, y, best[x][y],
            #                                        bestcost))
            verybest = localhillclimb(instance, best, x, y, minval, maxval,
                                      granularity)
            verybestcost = instance.cost_for_param(verybest)
            # print('          => {}  [{}]'.format(newbest[x][y], newbestcost))
            if (verybestcost*.999) > bestcost:
                print('Oops, verybest has higher cost than best. ' +
                      '({} > {})'.format(verybestcost, bestcost))
                continue  # while len(poplist) > 0:
            newbest = [lx.copy() for lx in best.copy()]
            newbest[x][y] = best[x][y] + (verybest[x][y] - best[x][y]) * climb
            newbestcost = instance.cost_for_param(newbest)
            if (newbestcost*.999) > bestcost:
                print('Oops, newbest has higher cost than best. ' +
                      '({} >{})'.format(newbestcost, bestcost))
                continue  # while len(poplist) > 0:
            if immediately:
                best = [lx.copy() for lx in newbest.copy()]
                bestcost = newbestcost
            else:
                atonce[x][y] = newbest[x][y]
        if not immediately:
            atoncecost = instance.cost_for_param(atonce)
            if atoncecost < bestcost:
                best = [lx.copy() for lx in atonce.copy()]
                bestcost = atoncecost
            else:
                climb /= 2
                print('climb: {}'.format(climb))
        if bestcost < allbestcost:
            allbest = [lx.copy() for lx in best.copy()]
            allbestcost = bestcost
            print('Save ', end='')
        elif bestcost == allbestcost:
            loop += 1
            if loop > 5:
                break
        print('bestcost: {}'.format(bestcost))
        time.sleep(.25)
    return allbest


if __name__ == '__main__':
    elfis2_adc()