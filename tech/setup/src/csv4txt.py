#!/usr/bin/python3
# -*- coding: utf-8 -*-
# -*- mode: Python -*-
# based on this work: https://github.com/emvivre/csv2txt

import sys
import getopt
import csv

def convert(input_csv, output_txt, delimiter=',', separator='|', padding=1,
            fields_range=[], header=False, reverse=False):
    with open(input_csv) as fd:
        reader = csv.reader(fd)
        data = [ l for l in reader ]
    nb_col = max([len(l) for l in data])
    fields_range = fields_range if len(fields_range) > 0 else range(nb_col)
    # print("data: \n" + repr(data))
    if reverse:
        if header:
            headercols = data[0]
            tmpdata = data[1:]
            data = [headercols]
        else:
            tmpdata = data
            data = []
        for x in range(len(tmpdata)-1,-1,-1):
            data.append(tmpdata[x])
        # print("reversed data: \n" + repr(data))

    # normalize number of column for each line
    for li in range(len(data)):
        data[li] += ['']*(nb_col-len(data[li]))

    # compute maximum length for each column
    max_length_per_col = [0]*nb_col
    for line in data:
        for i in range(len(line)):
            l = len(line[i])
            if l > max_length_per_col[ i ]:
                max_length_per_col[ i ] = l

    # check field range
    for f in fields_range:
        if f >= len(max_length_per_col):
            print('ERROR: invalid field number given !')
            quit(1)

    # apply padding to fields except the last one
    for i in fields_range[:-1]:
        max_length_per_col[ i ] += 2 + padding

    # generate output
    s = ''
    onlyfirsttime = True
    for line in data:
        for i in fields_range[:-1]:
            c = line[ i ]
            pad_len = max_length_per_col[i]-len(c)
            s += c + ' '*max(0,pad_len-2) + separator + ' '
        s += line[fields_range[-1]]
        s += '\n'
        if header and onlyfirsttime:
            onlyfirsttime = False
            for i in fields_range[:-1]:
                c = ''
                pad_len = max_length_per_col[i]-len(c)
                s += c + '-'*max(0,pad_len-2) + separator + '-'
            s += line[fields_range[-1]]
            s += '\n'


    # save output
    if output_txt != '-':
        with open(output_txt, 'w+t') as fd:
            fd.write(s)
    else:
        print(s)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print('Usage: %s \n\t'  % sys.argv[0] +
              '[-d <DELIMITER>] \n\t[-s <SEPARATOR>] \n\t[-p <PADDING>] \n\t' +
              '[-f <FIELD_0>,<FIELD_1>,...] \n\t[--sort "[<>]FieldName1,[<>]FieldName2] \n\t' +
              '[--page <PAGELENGHT>] \n\t<INPUT_CSV> <OUTPUT_TXT>')
        quit(1)

    delimiter = ','
    separator = '|'
    padding = 1
    fields_range = []
    header = False
    reverse = False
    # sort = []
    # page = 0

    # (opt, args) = getopt.getopt(sys.argv[1:], 'd:s:p:f:hr', ['sort=', 'page='])
    (opt, args) = getopt.getopt(sys.argv[1:], 'd:s:p:f:hr')
    print("opt: " +repr(opt))
    print("args: " +repr(args))
    sys.stdout.flush()

    for (k,v) in opt:
        if k == '-d':
            delimiter = v
        elif k == '-s':
            separator = v
        elif k == '-p':
            padding = int(v)
        elif k == '-f':
            fields_range = [ int(vv) for vv in v.split(',') ]
        elif k == '-h':
            header = True
        elif k == '-r':
            reverse = True
        # elif k == '--sort':
        #     dim = v.split(',')
        #     for x in dim:
        #         col = x
        #         asc = '<'
        #         if x[0] in ['>','<']:
        #             col = x[1:]
        #             asc = x[0]
        #         sort.append([col,asc])
        #     print("sort: " +repr(sort))
        # elif k == '--page':
        #     page = int(v)

    # read data
    (input_csv, output_txt) = args
    convert(input_csv, output_txt, delimiter, separator, padding, fields_range, header, reverse)
