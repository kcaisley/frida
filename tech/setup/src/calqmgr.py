#!/usr/bin/env python3

if __name__ == "__main__":
    debug = False
    verbose = True
    if False:
        import sys
        import os
        print("Python version")
        print (sys.version)
        print("Version info.")
        print (sys.version_info)
        print("Path")
        print (os.getcwd())
        print("")
    import subprocess
    import re

    stat = ["lmstat","-f","caltannerpvs"]
    statout = subprocess.Popen(stat, stdout=subprocess.PIPE).communicate()[0].decode()
    print(statout)


    pattern = r'Flexible License Manager status on [^:]+ +(?P<nowhh>\d+):(?P<nowmm>\d+)\n'
    match = re.search(pattern, statout)
    if debug:
        print('match.groupdict(): ')
        print(match.groupdict())
    nowhh = int(match.groupdict()['nowhh'])
    nowmm = int(match.groupdict()['nowmm'])
    now = nowhh*60+nowmm
    if verbose:
        print('nowhh:')
        print(nowhh)
        print('nowmm:')
        print(nowmm)
        print('now:')
        print(now)

    pattern = r'Total of (?P<total>\d+) license[s]? issued;  Total of (?P<use>\d+) license[s]? in use'
    #pattern = r'Total of (\d+) license'
    match = re.search(pattern, statout)
    if debug:
        print('match: ')
        print(match)
        print('match.groups(): ')
        print(match.groups())
        print('match.groupdict(): ')
        print(match.groupdict())
    lic_total = int(match.groupdict()['total'])
    lic_use = int(match.groupdict()['use'])
    if verbose:
        print('lic_total:')
        print(lic_total)
        print('lic_use:')
        print(lic_use)

    if lic_use == 0:
        print("0 licenses in use")
    else:
        print("at least 1 licenses in use")
        debug = True
        pattern = r'\n\s+(?P<user>\w+)\s+(?P<server1>\w+)\s+(?P<server2>\w+):(?P<display>\d\d)(?P<pid>[^_]+)[^\n]+start[^\n]+'
        pattern = r'\n\s+(?P<user>\w+)\s+(?P<server1>\w+)\s+(?P<server2>\w+):(?P<display>\d\d)(?P<pid>[^_]+)[^\n]+start[^:]+ +(?P<lichh>\d+):(?P<licmm>\d+)\n'
        match = re.search(pattern, statout)
        if debug:
            print('match: ')
            print(match)
            print('match.groups(): ')
            print(match.groups())
            print('match.groupdict(): ')
            print(match.groupdict())
        lic_user = match.groupdict()['user']
        lic_pid = match.groupdict()['pid']
        lic_start = int(match.groupdict()['lichh']) * 60 + int(match.groupdict()['licmm'])

        if verbose:
            print('lic_user:')
            print(lic_user)
            print('lic_pid:')
            print(lic_pid)
            print('lic_start:')
            print(lic_start)
        
        if 'queued' in statout:
            print('There is a queue.... action :)')
            free_time = 0
            
            if ((lic_start + free_time) % (24*60)) < now:
                print('kill -s 20 ' + lic_pid)
                
        

