#! /usr/bin/python3

import sys
print(sys.version)
import time
import logging      # in case you want to add extra logging
import lgeneral
import subprocess
import re
import sqlite3


sqlite_time_format = "%Y-%m-%d %H:%M:%S"
timestamp_time_format = "%Y%m%d_%H%M%S"
lmstati_time_format = "%d-%b-%Y"
lmstata_time_format = "%Y/%m/%d %H:%M"


def lmstat_a():
    p = subprocess.Popen(['lmstat','-a'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output, error = p.communicate()
    # print('output: ' + str(output))
    # print('error: ' + str(error))
    return output.decode()


def lmstat_i():
    p = subprocess.Popen(['lmstat','-i'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output, error = p.communicate()
    # print('output: ' + str(output))
    # print('error: ' + str(error))
    return output.decode()


def parse_output(lmstat_output):
    pattern1 = r'^Users of (\w+)[:]\s+([^\n]+)'
    pattern2 = r'[(]Total of (\d+) license[s]? issued;  Total of (\d+) license[s]? in use[)]'
    m = re.findall('Users', lmstat_output, re.MULTILINE)
    assertm = len(m)
    
    lic = re.finditer(pattern1, lmstat_output, re.MULTILINE)
    licrawstr = ''
    for match in lic:
        assertm -= 1
        licname = match.groups()[0]
        m2 = re.search(pattern2, match.groups()[1])
        if m2 is not None:
            lictot = m2.groups()[0]
            licuse = m2.groups()[1]
            licrawstr += '//'+licname+':'+licuse+'/'+lictot
            print(', '.join([licname, lictot, licuse]))
        else:
            licerr = match.groups()[1]
            licrawstr += '//'+licname+':'+licerr
            print(': '.join([licname, licerr]))
    if assertm != 0:
        logging.warning("No. of 'Users' in lmstat, not equal to detected " + 
                        "No. of license with other pattern(s)")
        logging.debug("lmstat_output: ")
        logging.debug(lmstat_output)
        
    
    
    return licrawstr


def parse_output_beta(lmstat_output):
    debug = True
    
    pattern1 = r'^Users of (?P<licname>\w+)[:]'
    pattern1a = r'^Users of (?P<licname>\w+)[:]\s+(?P<licerr>[^\n]+)'
    pattern2 = r'^Users of (?P<licname>\w+)[:]\s+[(]Total of (?P<lictot>\d+) license[s]? issued;  Total of (?P<licuse>\d+) license[s]? in use[)]'
    pattern3_ = r'" v(?P<version>[0-9.]+), [^,]+, expiry: (?P<day>\d+)-(?P<mon>\w+)-(?P<year>\d+)'
    pattern4 = r'''^\s+(?P<string>[^,\n]+,\s+
    start\s+(?P<weekday>\w+)\s+(?P<mon>\w+)[/](?P<day>\d+)\s+(?P<hour>\w+)[:](?P<min>\d+)).*?'''
    
    lic = re.finditer(pattern1, lmstat_output, re.MULTILINE)
    
    starts = []
    for match in lic:
        starts.append(match.start())
    starts.append(len(lmstat_output))
    
    liccount = ''
    licdetail = ''
    for i in range(len(starts)-1):
        # license count
        lictext = lmstat_output[starts[i]:starts[i+1]]
        match = re.search(pattern2, lictext)
        if match is not None:
            licname = match.groupdict()['licname']
            lictot = match.groupdict()['lictot']
            licuse = match.groupdict()['licuse']
            liccount += '//'+licname+':'+licuse+'/'+lictot
            print(', '.join([licname, lictot, licuse]))
        else:
            match = re.search(pattern1a, lictext)
            licname = match.groupdict()['licname']
            licerr = match.groupdict()['licerr']
            liccount += '//'+licname+':'+licerr
            print(': '.join([licname, licerr]))
        # license detail
        pattern3 = r'"' + licname + pattern3_
        if debug:
            if licuse != '0':
                print("pattern3 = r'" + pattern3 + "'")
                print("lictext = '''" + lictext + "'''")
        sublic = re.finditer(pattern3, lictext)
        substarts = []
        for match in sublic:
            substarts.append(starts[i] + match.start())
        substarts.append(starts[i+1])
        if debug:
            if licuse != '0':
                print("substarts = " + repr(substarts))
        
        for i in range(len(substarts)-1):
            sublictext = lmstat_output[substarts[i]:substarts[i+1]]
            if debug:
                print("pattern3 = r'" + pattern3 + "'")
                print("sublictext = '''" + sublictext + "'''")
            match = re.search(pattern3, sublictext)
            if match is not None:
                licversion = match.groupdict()['version']
                licexp = '-'.join([match.groupdict()['day'], match.groupdict()['mon'], match.groupdict()['year']])
                licdetail += '\n' + ','.join([licname, licversion, licexp])
                
                if debug:
                    print("pattern4 = r'''" + pattern4 + "'''")
                    print("sublictext = '''" + sublictext + "'''")
                instlic = re.finditer(pattern4, sublictext, re.MULTILINE | re.X)
                for match in instlic:
                    if debug:
                        print("p4match: " + match.groupdict()['string'])
                    mon = match.groupdict()['mon']
                    day = match.groupdict()['day']
                    hour = match.groupdict()['hour']
                    min = match.groupdict()['min']
                    ts = time.localtime()
                    age = ts.tm_min - int(min)
                    age += 60 * (ts.tm_hour - int(hour))
                    age += 24*60* (ts.tm_mday - int(day))
                    if debug:
                        print("age : " + str(age))
                    
                    if ts.tm_mon != int(mon):
                        leapyear = 1 if ts.tm_year % 4 == 0 else 0
                        daysmonth = [31, 28 + leapyear, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
                        tmp_mon = ts.tm_mon
                        while tmp_mon != int(mon):
                            tmp_mon -= 1
                            age += 24*60*daysmonth[tmp_mon]
                            if tmp_non < 1:
                                tmp_non == 12
                    licdetail += '\n\t' + match.groupdict()['string'] + '\n\t\tage: ' + str(age)
            else:
                logging.warning('no license details found. see details below.')
                logging.debug("lmstat_output: ")
                logging.debug(lmstat_output)
                
    print('licdetail:')
    print(licdetail)
    print('end')
    
    return liccount + licdetail


def parse_lmstata_for_db(lmstat_output):
    
    # CREATE TABLE detail(
    #         timestamp    TEXT, 
    #         interval     INTEGER, 
    #         license_ID   INTEGER, 
    #         string       TEXT, 
    #         age_minutes  INTEGER, 
    #         FOREIGN KEY (license_ID) 
    #         REFERENCES license (license_ID) 
    #             ON UPDATE RESTRICT 
    #             ON DELETE RESTRICT 
    #         )
            
    # returns:
    usedlicenses = []
    # contains [key, string, age]
    # age -1 means in queue
    
    debug = True
    
    pattern1 = r'^Users of (?P<licname>\w+)[:]'
    pattern1a = r'^Users of (?P<licname>\w+)[:]\s+(?P<licerr>[(]Error:[^\n]+)'
    pattern2 = r'^Users of (?P<licname>\w+)[:]\s+[(]Total of (?P<lictot>\d+) license[s]? issued;  Total of (?P<licuse>\d+) license[s]? in use[)]'
    #pattern3_ = r'" v(?P<version>[0-9.]+), [^,]+, expiry: (?P<day>\d+)-(?P<mon>\w+)-(?P<year>\d+)'
    pattern3_ = r'" v(?P<version>[0-9.]+), [^,]+, expiry: (?P<expiry>\S+)'
    pattern4 = r'^\s+(?P<string>[^,\n]+,\s+start\s+(?P<weekday>\w+)\s+(?P<datetime>(?P<mon>\w+)[/]\d+\s+\w+[:]\d+)).*?'
    pattern5 = r'^\s+(?P<string>[^\n]+\s+queued for\s+(?P<queuesize>\d+)\s+lic\S+)'
    
    lic = re.finditer(pattern1, lmstat_output, re.MULTILINE)
    
    starts = []
    for match in lic:
        starts.append(match.start())
    starts.append(len(lmstat_output))
    
    liccount = ''
    licdetail = ''
    for i in range(len(starts)-1):
        # license count
        lictext = lmstat_output[starts[i]:starts[i+1]]
        match = re.search(pattern2, lictext)
        if match is not None:
            licname = match.groupdict()['licname']
            licuse = match.groupdict()['licuse']
        else:
            match = re.search(pattern1a, lictext)
            if match is not None:
                logging.warning('Unexpected Users line here:')
                logging.debug('lictext:' + str(lictext))
                continue   #for i
        
        # license detail
        pattern3 = r'"' + licname + pattern3_
        if debug:
            if licuse != '0':
                print("pattern3 = r'" + pattern3 + "'")
                print("lictext = '''" + lictext + "'''")
        sublic = re.finditer(pattern3, lictext)
        substarts = []
        for match in sublic:
            substarts.append(starts[i] + match.start())
        substarts.append(starts[i+1])
        if debug:
            if licuse != '0':
                print("substarts = " + repr(substarts))
        if licuse == '0':
            assert len(substarts) == 1
        else:
            assert len(substarts) != 1
            
        for i in range(len(substarts)-1):
            sublictext = lmstat_output[substarts[i]:substarts[i+1]]
            if debug:
                print("pattern3 = r'" + pattern3 + "'")
                print("sublictext = '''" + sublictext + "'''")
            match = re.search(pattern3, sublictext)
            if match is not None:
                licversion = match.groupdict()['version']
                licexp_time = time.strptime(match.groupdict()['expiry'], lmstati_time_format)
                licexp_epoch = time.mktime(licexp_time) + 24*60*60 - 1  # end of the day
                licexpiry = time.strftime(sqlite_time_format, time.localtime(licexp_epoch))
                
                lickey = (licname, licversion, licexpiry)
                
                if debug:
                    print("pattern4 = r'''" + pattern4 + "'''")
                    print("sublictext = '''" + sublictext + "'''")
                instlic = re.finditer(pattern4, sublictext, re.MULTILINE | re.X)
                for match in instlic:
                    if debug:
                        print("p4match: " + match.groupdict()['string'])
                    string = match.groupdict()['string']
                    start_ = match.groupdict()['datetime']
                    mon = match.groupdict()['mon']
                    ts = time.localtime()
                    year = str(ts.tm_year)
                    if ts.tm_mon < int(mon):
                        year = str(ts.tm_year - 1)
                    start_str = time.strptime(year + "/" + start_, lmstata_time_format)
                    start = time.strftime(sqlite_time_format, start_str)
                    if debug:
                        print("start : " + start)
                    
                    usedlicenses.append([lickey, string, start])
                if debug:
                    print("pattern5 = r'''" + pattern5 + "'''")
                    print("sublictext = '''" + sublictext + "'''")
                qlic = re.finditer(pattern5, sublictext, re.MULTILINE)
                for match in qlic:
                    if debug:
                        print("p5match: " + match.groupdict()['string'])
                    string = match.groupdict()['string']
                    queuesize = int(match.groupdict()['queuesize'])
                    start = "Q"
                    if debug:
                        print("queuesize: " + str(queuesize))
                    
                    for x in range(queuesize):
                        if debug:
                            print("[lickey, string, start]: " + str([lickey, string, start]))
                    
                        usedlicenses.append([lickey, string, start])
            else:
                logging.warning('no license details found. see details below.')
                logging.debug("sublictext: " + str(sublictext))
                
    print('usedlicenses:')
    print(usedlicenses)
    
    return usedlicenses

def parse_lmstati_for_db(lmstat_output):
    debug = True
    
    pattern1 = r'Feature\s+Version\s+#licenses\s+Vendor\s+Expires'
    pattern2 = r'^(?P<name>\w+)\s+(?P<version>\S+)\s+(?P<amount>\d+)\s+(?P<vendor>\w+)\s+(?P<expiry>\S+)'
    header = re.search(pattern1, lmstat_output, re.MULTILINE)
    
    if header is not None:
        start = header.end()
    else:
        return {}
    
    sublic = re.finditer(pattern2, lmstat_output[start:], re.MULTILINE)
    licpool = {}
    for match in sublic:
        licname = match.groupdict()['name']
        licversion = match.groupdict()['version']
        licamount = int(match.groupdict()['amount'])
        licexp_time = time.strptime(match.groupdict()['expiry'], lmstati_time_format)
        licexp_epoch = time.mktime(licexp_time) + 24*60*60 - 1  # end of the day
        licexpiry = time.strftime(sqlite_time_format, time.localtime(licexp_epoch))
        
        lickey = (licname, licversion, licexpiry)
        licpool[lickey] = licpool.get(lickey, 0) + licamount
    
    return licpool

def wait_interval(interval):
    if interval < 1:
        return
    sec = time.localtime().tm_sec
    # waitmin = interval*60
    interval_ = interval
    # if the interval fits exactly in an hour, sync on the hour
    if interval in [1,2,3,4,5,6,10,12,15,20,30,60]:
        min_now = time.localtime().tm_min
        min_now_ = min_now
        while min_now_ % interval != 0:
            min_now_ -= 1
            interval_ -= 1
            if interval_ < 2:
                interval_ = 1
                break    # while
    
    time.sleep(interval_ * 60 - sec - 1)
    time.sleep(1-time.time()%1)

def lmlogall(interval=0, logfile='lm_log.log'):
    while True:
        try:
            ts = time.strftime(timestamp_time_format, time.localtime())
            lmstat_output = lmstat_a()
            logline = ts + parse_output(lmstat_output)
            with open(logfile, 'a') as fp:
                fp.write(logline + '\n')
            wait_interval(interval)

        except KeyboardInterrupt:
            break
        if interval == 0:
            break


def lmlogdetail(interval=0, logfile='lm_detail.log'):
    while True:
        try:
            ts = time.strftime(timestamp_time_format, time.localtime())
            lmstat_output = lmstat_a()
            logline = ts + parse_output_beta(lmstat_output)
            with open(logfile, 'a') as fp:
                fp.write(logline + '\n')
            wait_interval(interval)

        except KeyboardInterrupt:
            break
        if interval == 0:
            break


def lmlogdb(interval=0, logfile='lm_log.db'):
    prepare_db(logfile)
    ts = time.strftime(sqlite_time_format, time.localtime())
    while True:
        try:
            ts_previous = ts
            # get timestamp
            ts = time.strftime(sqlite_time_format, time.localtime())
            # add detailed license info to db
            db_add_details(logfile, ts, interval)
                
            # if total number for anyof the licenses changes:
                # check pool again
            # daily analysis
            if ts_previous[:10] != ts[:10]:
                # summarize log into day and ninetofive statistics
                pass
            wait_interval(interval)
            

        except KeyboardInterrupt:
            break
        if interval == 0:
            break
    

def db_definition():
    db_definition = {}
    db_definition['license'] = """CREATE TABLE license(
            license_ID   INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, 
            name         TEXT, 
            version      TEXT, 
            expiry       TEXT, 
            UNIQUE (name, version, expiry)
            )"""
    db_definition['pool'] = """CREATE TABLE pool(
            timestamp     TEXT, 
            license_ID    INTEGER, 
            amount        INTEGER, 
            FOREIGN KEY (license_ID) 
            REFERENCES license (license_ID) 
                ON UPDATE RESTRICT 
                ON DELETE RESTRICT 
            )"""
    db_definition['detail'] = """CREATE TABLE detail(
            timestamp    TEXT, 
            interval     INTEGER, 
            license_ID   INTEGER, 
            string       TEXT UNIQUE NOT NULL, 
            start        TEXT, 
            qstart       TEXT, 
            FOREIGN KEY (license_ID) 
            REFERENCES license (license_ID) 
                ON UPDATE RESTRICT 
                ON DELETE RESTRICT 
            )"""
    db_definition['day'] = """CREATE TABLE day(
            timestamp    TEXT, 
            license_ID   INTEGER, 
            no_use       REAL, 
            full_use     REAL, 
            avg_use      REAL, 
            min          INTEGER, 
            max          INTEGER, 
            age_oldest   INTEGER, 
            age_youngest INTEGER, 
            age_avg      REAL, 
            q_size_max   INTEGER, 
            q_time_min   INTEGER, 
            q_time_max   INTEGER, 
            q_time_avg   REAL, 
            FOREIGN KEY (license_ID) 
            REFERENCES license (license_ID) 
                ON UPDATE RESTRICT 
                ON DELETE RESTRICT 
            )"""
    db_definition['ninetofive'] = """CREATE TABLE ninetofive(
            timestamp    TEXT, 
            license_ID   INTEGER, 
            no_use       REAL, 
            full_use     REAL, 
            avg_use      REAL, 
            min          INTEGER, 
            max          INTEGER, 
            age_oldest   INTEGER, 
            age_youngest INTEGER, 
            age_avg      REAL, 
            q_size_max   INTEGER, 
            q_time_min   INTEGER, 
            q_time_max   INTEGER, 
            q_time_avg   REAL, 
            FOREIGN KEY (license_ID) 
            REFERENCES license (license_ID) 
                ON UPDATE RESTRICT 
                ON DELETE RESTRICT 
            )"""
    return db_definition


def prepare_db(dbfile):
    db_def = db_definition()
    con = sqlite3.connect(dbfile)
    cur = con.cursor()
    res = cur.execute("SELECT name FROM sqlite_master")
    alltablenames = res.fetchall()
    names = [x[0] for x in alltablenames] 
    for k, v in db_def.items():
        if k not in names:
            cur.execute(v)
    db_update_pool(cur)
    cur.close()
    con.commit()
    con.close()


def db_update_pool(cur, force=False):
    debug = True
    
    lmstat_output = lmstat_i()
    pool = parse_lmstati_for_db(lmstat_output)
    for k,v in pool.items():
        # print('pool[' + repr(k) + ']: ' + str(v))
        k_repr = [repr(x) for x in k]
        # print(k_repr)
        valuestring = ','.join(k_repr)
        select = """SELECT DISTINCT license_ID
            FROM license
            WHERE name = """ + k_repr[0] + """AND
                version = """ + k_repr[1] + """AND
                expiry = """ + k_repr[2]
        licID = cur.execute(select).fetchall()
        if len(licID) == 0:
            insert = """INSERT INTO license (name, version, expiry) 
                VALUES (""" + valuestring + ')'
            if debug:
                print(insert)
            
            cur.execute(insert)
            licID = cur.execute(select).fetchall()
        # print("licID: " + repr(licID))
        # print("licID[0]: " + repr(licID[0]))
        # print("licID[0][0]: " + repr(licID[0][0]))
        assert len(licID) == 1
        select = """SELECT amount
            FROM pool
            WHERE license_ID = """ + str(licID[0][0]) + """
            ORDER BY timestamp DESC"""
        amount = cur.execute(select).fetchone()
        now = time.strftime(sqlite_time_format, time.localtime())
        if k[2] < now:
            v = 0
        if force or amount is None or amount[0] != v:
            insert = """INSERT INTO pool (timestamp, license_ID, amount) 
                VALUES (datetime('now', 'localtime'), 
                """ + str(licID[0][0]) + """, 
                """ + str(v) + ')'
            cur.execute(insert)
            if debug:
                print(insert)


def db_add_details(dbfile, timestamp, interval):
    debug = True
    
    lmstat_output = lmstat_a()
    usedlicenses = parse_lmstata_for_db(lmstat_output)
    
    con = sqlite3.connect(dbfile)
    cur = con.cursor()
    
    for key,string,start in usedlicenses:
        if debug:
            print('key: ' + str(key))
            print('string: ' + str(string))
            print('start: ' + str(start))
        # print('pool[' + repr(key) + ']: ' + str(v))
        key_repr = [repr(x) for x in key]
        # print(key_repr)
        valuestring = ','.join(key_repr)
        select = """SELECT DISTINCT license_ID
            FROM license
            WHERE name = """ + key_repr[0] + """AND
                version = """ + key_repr[1] + """AND
                expiry = """ + key_repr[2]
        licID = cur.execute(select).fetchall()
        if len(licID) == 0:
            insert = """INSERT INTO license (name, version, expiry) 
                VALUES (""" + valuestring + ')'
            if debug:
                print(insert)
            
            cur.execute(insert)
            licID = cur.execute(select).fetchall()
        # print("licID: " + repr(licID))
        # print("licID[0]: " + repr(licID[0]))
        # print("licID[0][0]: " + repr(licID[0][0]))
        assert len(licID) == 1
        select = """SELECT timestamp
            FROM detail
            WHERE string = '""" + string + "'"
        fetch = cur.execute(select).fetchall()
        if len(fetch) != 0:
            insert = """UPDATE detail 
                SET timestamp = '""" + timestamp + """' 
                WHERE string = '""" + string + "'"
        else:
            if start != 'Q':
                insert = """INSERT INTO detail (timestamp, interval, license_ID, string, start) 
                    VALUES ('""" + timestamp + """', 
                    """ + str(interval) + """, 
                    """ + str(licID[0][0]) + """, 
                    '""" + string + """', 
                    '""" + str(start) + "')"
            else:insert = """INSERT INTO detail (timestamp, interval, license_ID, string, qstart) 
                    VALUES ('""" + timestamp + """', 
                    """ + str(interval) + """, 
                    """ + str(licID[0][0]) + """, 
                    '""" + string + """', 
                    '""" + timestamp + "')"
        if debug:
            print(insert)
        cur.execute(insert)
    cur.close()
    con.commit()
    con.close()


def argparse_setup(subparsers):
    parser_all = subparsers.add_parser(
        'all', help=('runs license manager logger on all licenses'))
    parser_all.add_argument(
        '-i', '--interval', default=5, type=int, 
        help=('interval of the logger in minutes, default 5 minutes. 0 : one-off'))

    parser_det = subparsers.add_parser(
        'detail', help=('runs license manager logger on all licenses, with detail'))
    parser_det.add_argument(
        '-i', '--interval', default=5, type=int, 
        help=('interval of the logger in minutes, default 5 minutes. 0 : one-off'))

    parser_db = subparsers.add_parser(
        'db', help=('runs license manager logger and stores in db'))
    parser_db.add_argument(
        '-i', '--interval', default=5, type=int, 
        help=('interval of the logger in minutes, default 5 minutes. 0 : one-off'))
    parser_db.add_argument(
        '-o', '--outfile', default='lm_log.db', type=str, 
        help=('output logfile for database storage, default: lm_log.db'))

    parser_deb = subparsers.add_parser(
        'debug', help=('runs license manager logger and stores in db'))
    parser_deb.add_argument(
        '-i', '--interval', default=5, type=int, 
        help=('interval of the logger in minutes, default 5 minutes. 0 : one-off'))

def argparse_eval(args):
    # make a dict of args
    dictargs = vars(args)
    print('argparse_eval( ' + repr(args) + ' )')
    funcdict = {'all': (lmlogall,
                        [dictargs.get('interval')]),
                'detail': (lmlogdetail,
                           [dictargs.get('interval')]),
                'db': (lmlogdb,
                       [dictargs.get('interval'),
                        dictargs.get('outfile')]),
                'debug': (lmlogdb,
                          [dictargs.get('interval'),
                           dictargs.get('outfile')])
                }
    return funcdict


if __name__ == "__main__":
    lgeneral.logsetup()
    lgeneral.myargparse(argparse_setup, argparse_eval, 'v20240812')

    print(sys.version)
    logging.info(sys.version)

    time.sleep(1)
