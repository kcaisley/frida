#
# ------------------------------------------------------------
# Copyright (c) All rights reserved
# SiLab, Institute of Physics, University of Bonn
# ------------------------------------------------------------
#

''' Module to manage firmware download, compilation and flashing using vivado.
    Mainly for CI runner but also useful during headless session (e.g. test beams)
'''

import os
import time
import argparse
import pexpect
import git
import fileinput

import tjmonopix2
from tjmonopix2.system import logger

log = logger.setup_derived_logger('FirmwareManager')

tjmonopix2_path = os.path.dirname(tjmonopix2.__file__)
sitcp_repo = r'https://github.com/BeeBeansTechnologies/SiTCP_Netlist_for_Kintex7'


def compile_firmware(platform):
    ''' Compile firmware using vivado in tcl mode
    '''

    def get_return_string(timeout=1):
        ''' Helper function to get full return string.

            This complexity needed here since Xilinx does multi line returns
        '''
        flushed = bytearray()
        try:
            while not vivado.expect(r'.+', timeout=timeout):
                flushed += vivado.match.group(0)
        except (pexpect.exceptions.TIMEOUT, pexpect.exceptions.EOF):
            pass
        return flushed.decode('utf-8')

    supported_firmwares = ['BDAQ53', 'BDAQ53_KX1', 'MIO3']
    if platform not in supported_firmwares:
        log.error('Can only compile firmwares: %s', ','.join(supported_firmwares))
        return

    log.info('Compile firmware %s', platform)

    vivado_tcl = os.path.join(tjmonopix2_path, '..', 'firmware/vivado')

    # Use mappings from run.tcl
    fpga_types = {'BDAQ53': 'xc7k160tffg676-2',
                  'BDAQ53_KX1': 'xc7k160tfbg676-1',
                  'MIO3': 'xc7k160tfbg676-1'}
    constraints_files = {'BDAQ53': 'bdaq53_kx2.xdc',
                         'BDAQ53_KX1': 'bdaq53_kx1.xdc',
                         'MIO3': 'mio3_kx1.xdc'}
    flash_sizes = {'BDAQ53': 64,
                   'BDAQ53_KX1': 64,
                   'MIO3': 64}
    suffices = {'BDAQ53': '',
                'BDAQ53_KX1': '',
                'MIO3': ''}

    for k, v in fpga_types.items():
        if k in platform:
            fpga_type = v
            constraints_file = constraints_files[k]
            flash_size = flash_sizes[k]
            suffix = suffices[k]

    command_args = fpga_type + ' ' + constraints_file + ' ' + str(flash_size) + ' ' + suffix
    command = 'vivado -mode batch -source run.tcl -tclargs %s' % command_args
    log.info('Compiling firmware. Takes about 5 minutes!')
    try:
        vivado = pexpect.spawn(command, cwd=vivado_tcl, timeout=10)
        vivado.expect('Vivado', timeout=5)
    except pexpect.exceptions.ExceptionPexpect:
        log.error('Cannot execute vivado command %d.\nMaybe paid version is missing that is needed for compilation?', command)
        return

    timeout = 36  # equals 180 seconds with no new print to screen
    t = 0
    while t < timeout:
        r = get_return_string()
        if r:
            if 'write_cfgmem completed successfully' in r:
                print('.', end='\n', flush=True)
                break
            print('.', end='', flush=True)
            t = 0
        else:
            time.sleep(5)
            t += 1
    else:
        raise RuntimeError('Timeout during compilation, check vivado.log')

    # Move firmware to current folder
    log.info('SUCCESS! Firmware can be found in firmware/bit folder')


def flash_firmware(name):
    ''' Flash firmware using vivado in tcl mode
    '''

    def get_return_string(timeout=1):
        ''' Helper function to get full return string.

            This complexity needed here since Xilinx does multi line returns
        '''
        flushed = bytearray()
        try:
            while not vivado.expect(r'.+', timeout=timeout):
                flushed += vivado.match.group(0)
        except pexpect.exceptions.TIMEOUT:
            pass
        return flushed.decode('utf-8')

    def write_flash_memory(name):
        vivado.sendline('set_property PROGRAM.ADDRESS_RANGE {use_file} [get_property PROGRAM.HW_CFGMEM [current_hw_device]]')
        vivado.sendline('set_property PROGRAM.FILES {%s} [get_property PROGRAM.HW_CFGMEM [current_hw_device]]' % name)
        vivado.sendline('set_property PROGRAM.BLANK_CHECK 0 [ get_property PROGRAM.HW_CFGMEM [current_hw_device]]')
        vivado.sendline('set_property PROGRAM.ERASE 1 [get_property PROGRAM.HW_CFGMEM [current_hw_device]]')
        vivado.sendline('set_property PROGRAM.CFG_PROGRAM 1 [get_property PROGRAM.HW_CFGMEM [current_hw_device]]')
        vivado.sendline('set_property PROGRAM.VERIFY 1 [get_property PROGRAM.HW_CFGMEM [current_hw_device]]')

        vivado.sendline('create_hw_bitstream -hw_device [current_hw_device] [get_property PROGRAM.HW_CFGMEM_BITFILE [current_hw_device]]')
        vivado.sendline('program_hw_devices [current_hw_device]')
        vivado.expect('End of startup status: HIGH', timeout=10)

        vivado.sendline('program_hw_cfgmem -hw_cfgmem [ get_property PROGRAM.HW_CFGMEM [current_hw_device]]')
        vivado.expect('Flash programming completed successfully', timeout=2 * 60)  # Generous timeout
        return get_return_string()

    try:
        vivado = pexpect.spawn('vivado_lab -mode tcl', timeout=10)  # try lab version
        vivado.expect('Vivado', timeout=5)
    except pexpect.exceptions.ExceptionPexpect:
        try:
            vivado = pexpect.spawn('vivado -mode tcl', timeout=10)  # try full version
            vivado.expect('Vivado', timeout=5)
        except pexpect.exceptions.ExceptionPexpect:
            log.error('Cannot execute vivado / vivado_lab commend')
            return
    vivado.expect(['vivado_lab%', 'Vivado%'])  # Booted up when showing prompt

    log.info('Connecting to JTAG interface')

    vivado.sendline('open_hw_manager')
    vivado.expect(['vivado_lab%', 'Vivado%'])  # Command finished when showing prompt

    vivado.sendline('connect_hw_server')
    vivado.expect('localhost')  # Printed when successful
    get_return_string()

    vivado.sendline('current_hw_target')
    ret = get_return_string()
    log.info('Connected to FPGA: %s', ret)
    if 'WARNING' in ret:
        log.error('Cannot find programmer hardware, Xilinx warning:\n%s', ret)
        vivado.sendline('exit')
        vivado.expect('Exiting')
        return

    vivado.sendline('open_hw_target')
    vivado.expect('Opening hw_target')  # Printed when programmer found

    vivado.sendline('current_hw_device [lindex [get_hw_devices] 0]')
    vivado.expect(['vivado_lab%', 'Vivado%'])  # Printed when finished
    ret = get_return_string()

    if 'xc7k160t' in ret and 'bdaq' not in name and 'mio3' not in name:
        log.error('The selected bitfile \'%s\' does not match the connected FPGA type \'xc7k160t\'', name)
        vivado.sendline('exit')
        vivado.expect('Exiting')
        return

    if '.bit' in name or '.bin' in name:
        log.info('Writing only to FPGA, not to FLASH memory. Config lost after power cycle!')

        vivado.sendline('set devPart [get_property PART [current_hw_device]]')
        vivado.expect(['vivado_lab%', 'Vivado%'])  # Printed when finished

        vivado.sendline('set_property PROGRAM.FILE {%s} [current_hw_device]' % name)
        vivado.expect(['vivado_lab%', 'Vivado%'])  # Printed when finished

        log.info('Writing firmware %s', name)

        vivado.sendline('program_hw_devices [current_hw_device]')
        vivado.expect('End of startup status: HIGH')  # firmware upload successful
    elif '.mcs' in name:
        log.info('Writing to the FLASH memory. Config kept even after power cycle.')

        flash_chip = 's25fl512s-spi-x1_x2_x4'  # Flash memory for KX2 and newer revisions of KX1
        try:
            vivado.sendline('create_hw_cfgmem -hw_device [current_hw_device] [lindex [get_cfgmem_parts {%s}] 0]' % flash_chip)
            ret = write_flash_memory(name)
        except Exception:
            log.warning("Configuration with memory type s25fl512s-spi-x1_x2_x4 failed, trying mt25ql256-spi-x1_x2_x4")
            flash_chip = 'mt25ql256-spi-x1_x2_x4'  # Try flash memory of earlier revisions
            vivado.sendline('create_hw_cfgmem -hw_device [current_hw_device] [lindex [get_cfgmem_parts {%s}] 0]' % flash_chip)
            ret = write_flash_memory(name)

        log.info(ret)

        vivado.sendline('boot_hw_device [current_hw_device]')
        vivado.expect('Done pin status: HIGH')

    vivado.sendline('close_hw_target')
    vivado.expect('Closing')
    vivado.sendline('exit')
    vivado.expect('Exiting')

    log.success('All done!')


def get_sitcp():
    ''' Download SiTCP sources from official github repo and apply patches
    '''

    def line_prepender(filename, line):
        with open(filename, 'rb+') as f:
            content = f.read()
            f.seek(0, 0)
            # Python 3, wtf?
            add = bytearray()
            add.extend(map(ord, line))
            add.extend(map(ord, '\n'))
            f.write(add + content)

    def patch_sitcp():
        # Patch sources, see README
        line_prepender(filename=sitcp_folder + 'TIMER.v', line=r'`default_nettype wire')
        line_prepender(filename=sitcp_folder + 'WRAP_SiTCP_GMII_XC7K_32K.V', line=r'`default_nettype wire')
        for line in fileinput.input([sitcp_folder + 'WRAP_SiTCP_GMII_XC7K_32K.V'], inplace=True):
            print(line.replace("assign\tMY_IP_ADDR[31:0]\t= (~FORCE_DEFAULTn | (EXT_IP_ADDR[31:0]==32'd0) \t? DEFAULT_IP_ADDR[31:0]\t\t: EXT_IP_ADDR[31:0]\t\t);",
                               'assign\tMY_IP_ADDR[31:0]\t= EXT_IP_ADDR[31:0];'), end='')

    sitcp_folder = os.path.join(tjmonopix2_path, '..', 'firmware/SiTCP/')

    # Only download if not already existing SiTCP git repository
    if not os.path.isdir(os.path.join(sitcp_folder, '.git')):
        log.info('Downloading SiTCP')

        # Has to be moved to be allowed to use existing folder for git checkout
        git.Repo.clone_from(url=sitcp_repo,
                            to_path=sitcp_folder, branch='master')
        patch_sitcp()

    else:  # update if existing
        log.info('SiTCP folder already exists, updating if possible')
        g = git.cmd.Git(sitcp_folder)
        if 'up to date' in g.pull():
            log.info('SiTCP is up to date')
        else:
            patch_sitcp()
            log.info('Updated and patched SiTCP from git repository')


def main():
    parser = argparse.ArgumentParser(description='TJ-Monopix2 firmware manager', formatter_class=argparse.RawTextHelpFormatter)

    parser.add_argument('-f', '--firmware',
                        nargs=1,
                        help='Firmware file name or platform to build firmware for',)

    parser.add_argument('-c', '--compile',
                        nargs=1,
                        help='Platform to compile firmware for',)

    parser.add_argument('--get_sitcp',
                        action='store_true',
                        help='Standalone download and patching of SiTCP.',)

    args = parser.parse_args()

    if args.firmware and args.compile:
        raise RuntimeError("Both firmware file and compile platform is given, choose one.")

    if args.firmware:
        flash_firmware(args.firmware[0])
    elif args.compile:
        get_sitcp()
        compile_firmware(args.compile[0])
    elif args.get_sitcp:
        get_sitcp()


if __name__ == '__main__':
    main()
