#!/usr/bin/env python3
# -*- coding: utf8 -*-

'''
Pacman wrapper for parallel and segmented downloads with Aria2,and optional
internal support for Rsync, Reflector and Pacserve.
'''

# Copyright (C) 2012-2021 Xyne
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# (version 2) as published by the Free Software Foundation.
#
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

# The code is a bit messy because I cobbled it together from parisync.
# I intend to clean it up when I have the time and proper motivation.

import collections
import glob
import json
import logging
import os
import platform
import subprocess
import sys
import urllib.parse

import pyalpm

import pm2ml
import XCGF
import XCPF
import XCPF.PacmanConfig

try:
    from ThreadedServers.Pacserve import search_pkgs as search_pacserve
except ImportError:
    def search_pacserve(_pacserve_url, _pkgnames):
        '''
        Search for package names on the given Pacserve server.
        '''
        return None

try:
    import Reflector
    OFFICIAL_REPOSITORIES = Reflector.MirrorStatus.REPOSITORIES
except ImportError:
    OFFICIAL_REPOSITORIES = tuple()

# --------------------------------- Globals ---------------------------------- #

DB_EXT = '.db'
FILES_EXT = '.files'
SIG_EXT = '.sig'
DB_LOCK_FILE = 'db.lck'
DB_LOCK_NAME = 'database'
CACHE_LOCK_FILE = 'cache.lck'
CACHE_LOCK_NAME = 'cache'

POWERPILL_CONFIG = '/etc/powerpill/powerpill.json'
ARIA2_EXT = '.aria2'

# See the aria2c manual page for details.
ARIA2_DOWNLOAD_ERROR_EXIT_CODES = (0, 2, 3, 4, 5)
# See the rsync manual page for details.
RSYNC_DOWNLOAD_ERROR_EXIT_CODES = (2, 5, 10, 12, 23, 24, 30)

# Arguments that change the Pacman configuration file.
PACMAN_CONF_OPTS = (
    ('-b', '--dbpath', 'DBPath'),
    ('-r', '--root', 'RootDir'),
    ('--arch', 'Architecture'),
    ('--cachedir', 'CacheDir'),
    ('--gpgdir', 'GPGDir'),
    ('--logfile', 'LogFile'),
    ('--color', 'Color'),
)

# Parameterized Pacman arguments.
# `--ask` is undocumented but mentioned along with a support request here:
# https://bbs.archlinux.org/viewtopic.php?pid=1577363#p1577363
PACMAN_PARAM_OPTS = set((
    '-b', '--dbpath',
    '--arch',
    '--ask',
    '--cachedir',
    '--color',
    '--config',
    '--gpgdir',
    '--ignore',
    '--ignoregroup',
    '--logfile',
    '--print-format'
))

# Non-download Pacman sync operations.
PACMAN_OPS = set((
    '-c', '--clean',
    '-g', '--groups',
    '-i', '--info',
    '-l', '--list',
    '-p', '--print', '--print-format',
    '-s', '--search',
))

# Order must match string of short options in RECOGNIZED_PACMAN_SHORT_OPTIONS.
RECOGNIZED_PACMAN_OPTIONS = (
    'sync',
    'files',
    'refresh',
    'sysupgrade',
    'downloadonly',
    'quiet',
    'verbose',
    'debug',
)


RECOGNIZED_PACMAN_SHORT_OPTIONS = dict(
    ('-' + x, '--' + y) for x, y in zip('SFyuwqv', RECOGNIZED_PACMAN_OPTIONS)
)

POWERPILL_PARAM_OPTS = set((
    '--powerpill-config',
))


# -------------------- Configuration and Argument Parsing -------------------- #

def expand_recognized_pacman_short_options(args):
    '''
    Replace recognized Pacman short options with their long equivalents.
    '''
    for arg in args:
        try:
            yield RECOGNIZED_PACMAN_SHORT_OPTIONS[arg]
        except KeyError:
            yield arg


def parse_args(args=None):  # pylint: disable=too-many-statements,too-many-branches
    '''
    Parse (Pacman) command-line arguments and extract those that control
    Powerpill.
    '''
    if args is None:
        args = sys.argv[1:]
    # Arguments set to None will default to the powerpill configuration file.
    pargs = {
        'pacman_config': None,
        'powerpill_config': POWERPILL_CONFIG,
        'powerpill_clean': False,
        'aria2_config': None,
        'help': False,
        'pacman_config_options': {'CacheDir': list()},
        'pm2ml_options': list(),
        'options': list(),
        'args': list(),
        'other_operation': False,
        'raw': list(XCGF.filter_arguments(args, remove={
            '--powerpill-clean': 0,
            '--powerpill-config': 1,
        })),
    }
    for rpo in RECOGNIZED_PACMAN_OPTIONS:
        pargs[rpo] = 0
    argq = collections.deque(expand_recognized_pacman_short_options(XCGF.expand_short_args(args)))
    included_stdin = False
    while argq:
        arg = argq.popleft()

        if arg == '-':
            if not included_stdin:
                included_stdin = True
                pargs['args'].extend(XCPF.get_args_from_stdin())
            else:
                pargs['args'].append(arg)
            continue

        if arg == '--':
            if not included_stdin:
                argq = XCPF.maybe_insert_args_from_stdin(argq)
            pargs['args'].extend(argq)
            break

        if arg[:2] == '--' and arg[2:] in RECOGNIZED_PACMAN_OPTIONS:
            pargs[arg[2:]] += 1

        elif arg in ('-h', '--help'):
            pargs['help'] = True

        elif arg in ('--config', '--powerpill-config'):
            try:
                next_arg = argq.popleft()
            except IndexError as err:
                raise ArgumentError('no file path given for "{}"'.format(arg)) from err
            else:
                if arg == '--config':
                    k = 'pacman_config'
                else:
                    k = 'powerpill_config'
                pargs[k] = os.path.abspath(next_arg)

        elif arg == '--powerpill-clean':
            pargs['powerpill_clean'] = True

        elif arg[0] == '-':
            # (short argument if present, long argument, internal name)
            for conf_opt in PACMAN_CONF_OPTS:
                if arg in conf_opt[:-1]:
                    opt = conf_opt[-1]
                    try:
                        val = argq.popleft()
                    except IndexError as err:
                        raise ArgumentError('no argument for option {}'.format(arg)) from err
                    if opt == 'CacheDir':
                        pargs['pacman_config_options'][opt].append(val)
                    else:
                        pargs['pacman_config_options'][opt] = val
                    break
            else:
                if arg in PACMAN_OPS:
                    pargs['other_operation'] = True
                if arg in pm2ml.PACMAN_OPTIONS:  # \
                    # and arg not in ('--ignore', '--ignoregroup'):
                    name = 'pm2ml_options'
                else:
                    name = 'options'
                pargs[name].append(arg)
                if arg in PACMAN_PARAM_OPTS:
                    try:
                        next_arg = argq.popleft()
                    except IndexError as err:
                        #             if arg in PACMAN_OPS:
                        #               pass
                        #             else:
                        raise ArgumentError('no argument for pacman option {}'.format(arg)) from err
                    else:
                        pargs[name].append(next_arg)
        else:
            pargs['args'].append(arg)
    return pargs


def unparse_args(pargs):  # pylint: disable=too-many-branches
    '''
    Convert parsed arguments to a list of Pacman arguments.
    '''
    # All of the argument parsing assumes a sync operation and so overlapping
    # short arguments are expanded to their long sync arguments, which breaks
    # other operations. For example, "-u" will be expanded to "--sysupgrade" even
    # for a query operation for which the correct expansion would be "--upgrades".
    # This is a workaround until I refactor the current argument parsing mess.
    if not (pargs['sync'] or pargs['files']):
        for arg in pargs['raw']:
            yield arg
        return
    # Map configuration file parameters to command-line options.
    pacman_opts = dict()
    for opt in PACMAN_CONF_OPTS:
        pacman_opts[opt[-1]] = opt[-2]

    for opt in RECOGNIZED_PACMAN_OPTIONS:
        for _ in range(pargs[opt]):
            yield '--' + opt
    if pargs['pacman_config']:
        yield '--config'
        yield pargs['pacman_config']

    for key, val in pargs['pacman_config_options'].items():
        opt = pacman_opts[key]
        if key == 'CacheDir':
            for cdir in val:
                yield opt
                yield cdir
        else:
            yield opt
            yield val

    if pargs['help']:
        yield '--help'
    for whatever in pargs['pm2ml_options']:
        yield whatever
    for whatever in pargs['options']:
        yield whatever
    for whatever in pargs['args']:
        yield whatever


def display_help():
    '''
    Print the help message.
    '''
    name = os.path.basename(sys.argv[0])
    title = name.title()

    print('''USAGE
  {name} [{name} options] [pacman args]

OPTIONS
  {title} should accept the same arguments as Pacman, e.g.

      {name} -Syu

  See "pacman --help" for further help.

  The following additional arguments are supported:

    --powerpill-config <path>
        The path to a Powerpill configuration file.
        Default: {powerpill_config}

    --powerpill-clean
        Clean up leftover .aria2 files from an unrecoverable download. Use this
        option to resolve aria2c length mismatch errors.

'''.format(
        name=name,
        title=title,
        powerpill_config=POWERPILL_CONFIG
    )
    )


def get_pacman_conf(pargs, powerpill_conf):
    '''
    Get the pacman configuration file.
    '''
    if not pargs['pacman_config']:
        pargs['pacman_config'] = powerpill_conf.get('pacman/config')

    try:
        pacman_conf = XCPF.PacmanConfig.PacmanConfig(pargs['pacman_config'])
    except FileNotFoundError as err:
        logging.error('failed to load %s [%s]', pargs['pacman_config'], err)
        return None

    # RootDir affects other options, so it must be handled first.
    try:
        rootdir = pargs['pacman_config_options']['RootDir']
        for opt in ('DBPath', 'LogFile'):
            pacman_conf.options[opt] = os.path.join(rootdir, pacman_conf.options[opt][1:])
    except KeyError:
        pass

    for key, val in pargs['pacman_config_options'].items():
        if key != 'RootDir' and val:
            pacman_conf.options[key] = val

    return pacman_conf


# -------------------------------- Exceptions -------------------------------- #

class PowerpillError(XCPF.XcpfError):
    '''Parent class of all custom exceptions raised by this module.'''

    def __str__(self):
        return '{}: {}'.format(self.__class__.__name__, self.msg)


class ConfigError(PowerpillError):
    '''Exceptions raised by the Config class.'''


class ArgumentError(PowerpillError):
    '''Exceptions raised by the Config class.'''


# ------------------------------- Config Class ------------------------------- #

class Config():
    '''
    JSON object wrapper for implementing a configuration file.
    '''
    DEFAULTS = {
        'aria2': {
            'path': '/usr/bin/aria2c',
        },
        'pacman': {
            'path': '/usr/bin/pacman',
            'config': '/etc/pacman.conf',
        },
        'powerpill': {
            'select': True,
            'reflect databases': False,
        },
        'rsync': {
            'rsync': '/usr/bin/rsync',
        },
    }

    def __init__(self, path=None):
        if path is None:
            self.obj = dict()
            self.path = None
        else:
            self.load(path)

    def __str__(self):
        return json.dumps(self.obj, indent='  ', sort_keys=True)

    def load(self, path):
        '''
        Load the configuration file.
        '''
        try:
            self.obj = XCGF.load_json(path)
        except ValueError as err:
            raise ConfigError(
                '''failed to load {} [{}]
Check the file for syntax errors.'''.format(path, err),
                error=err) from err
        except FileNotFoundError as err:
            raise ConfigError(str(err), error=err) from err
        self.path = path

    def save(self, path=None):
        '''
        Save the configuration file.
        '''
        if path is None:
            path = self.path
        if path is None:
            raise ConfigError('no path given for saving configuration file')
        with open(path, 'w') as handle:
            json.dump(self.obj, handle, indent='  ', sort_keys=True)

    def get(self, args):
        '''
        Return the requested entry or None if it does not exist.
        '''
        obj = self.obj
        args = args.split('/')
        for arg in args:
            try:
                obj = obj[arg]
            except KeyError:
                obj = None
                break
        # Get default if not found.
        if obj is None:
            obj = self.DEFAULTS
            for arg in args:
                try:
                    obj = obj[arg]
                except KeyError:
                    obj = None
                    break
        return obj

    def set(self, args, value):
        '''
        Set the requested entry to the given value.
        '''
        obj = self.obj
        args = args.split('/')
        for arg in args[:-1]:
            try:
                obj = obj[arg]
            except KeyError:
                obj[arg] = dict()
                obj = obj[arg]
        obj[args[-1]] = value


# -------------------------------- Powerpill --------------------------------- #

class Powerpill():
    '''
    Main program class.
    '''

    def __init__(self, pargs, pm2ml_pargs=None, ttl=pm2ml.DEFAULT_TTL):

        self.pargs = pargs
        self.conf = Config(pargs['powerpill_config'])
        self.pacman_conf = get_pacman_conf(pargs, self.conf)
        self.db_lock = None
        if pm2ml_pargs is None:
            pm2ml_pargs = pm2ml.parse_args([])
        self.pm2ml = pm2ml.Pm2ml(pm2ml_pargs, pacman_conf=self.pacman_conf)

    # rsync has a hard limit of 1000 arguments (someone actually hit this and
    # reported it), so this may return multiple commands to handle all arguments.
    def download_queue_to_rsync_cmds(
        self,
        rsync_server,
        queue,
        output_dir=None,
    ):  # pylint: disable=too-many-locals
        '''
        Convert a download queue to an rsync command list.
        '''
        cmd = [self.conf.get('rsync/path'), '-aL'] + self.conf.get('rsync/args')

        url = urllib.parse.urlparse(rsync_server)
        host = url.netloc
        # [1:] to remove initial slash
        path = url.path[1:].replace('$arch', self.pacman_conf.options['Architecture'])

        host_added = False

        if not output_dir:
            output_dir = '.'

        args = list()

        for db, sigs, files in queue.dbs:  # pylint: disable=invalid-name
            if files:
                db_ext = FILES_EXT
            else:
                db_ext = DB_EXT
            db_path = '::' + os.path.join(path.replace('$repo', db.name), db.name + db_ext)
            if not host_added:
                args.append(host + db_path)
                host_added = True
            else:
                args.append(db_path)
            if sigs:
                args.append(db_path + SIG_EXT)

        for pkg, _urls, sigs in queue.sync_pkgs:
            pkg_path = '::' + os.path.join(path.replace('$repo', pkg.db.name), pkg.filename)
            if not host_added:
                args.append(host + pkg_path)
                host_added = True
            else:
                args.append(pkg_path)
            if sigs:
                args.append(pkg_path + SIG_EXT)

        # handle the hard limit
        rsync_limit = 1000
        arg_limit = rsync_limit - (len(cmd) + 1)
        assert arg_limit > 0, 'rsync command construction failed due to argument limit'
        while args:
            yield cmd + args[:arg_limit] + [output_dir]
            args = args[arg_limit:]

    def get_pm2ml_pkg_download_args(self, dpath=None, ignore=True):
        '''
        Iterate over pm2ml options for downloading packages.
        '''
        if dpath:
            yield '-o'
            yield dpath
        for opt in ('sysupgrade', 'verbose', 'debug'):
            for _ in range(self.pargs[opt]):
                yield '--' + opt
        for opt in self.pargs['pm2ml_options']:
            yield opt
        if ignore:
            for pkg in self.pacman_conf.options['IgnorePkg']:
                yield '--ignore'
                yield pkg
            for grp in self.pacman_conf.options['IgnoreGroup']:
                yield '--ignoregroup'
                yield grp
        if self.conf.get('powerpill/select'):
            yield '--select'
        for arg in self.pargs['args']:
            yield arg

    def download(self, pm2ml_args, dbs=False, force=False):
        '''
        Download files specified by pm2ml arguments.
        '''
#     for pkg in self.pacman_conf.options['IgnorePkg']:
#       pm2ml_args.extend(('--ignore', pkg))
#     for grp in self.pacman_conf.options['IgnoreGroup']:
#       pm2ml_args.extend(('--ignoregroup', grp))
#     if self.conf.get('powerpill/select'):
#       pm2ml_args.append('--select')
        if dbs:
            #       pm2ml_args.append('--preference')
            reflect = self.conf.get('powerpill/reflect databases')
        else:
            reflect = True
        # This must be added last.
        if reflect and self.conf.get('reflector/args'):
            pm2ml_args += ['--reflector'] + self.conf.get('reflector/args')
        pm2ml_pargs = pm2ml.parse_args(pm2ml_args)
        sync_pkgs, sync_deps, \
            _aur_pkgs, _aur_deps, \
            _not_found, _unknown_deps, _orphans = \
            self.pm2ml.resolve_targets_from_arguments(pm2ml_pargs)

        download_queue = \
            self.pm2ml.build_download_queue(
                pm2ml_pargs,
                sync_pkgs | sync_deps
            )

        rsync_queue = pm2ml.DownloadQueue()
        metalink_queue = pm2ml.DownloadQueue()

        output_dir = pm2ml_pargs.output_dir
        if output_dir:
            # A FileExistsError will be raised even with exists_ok=True if the mode
            # does not match the umask-masked mode.
            try:
                os.makedirs(output_dir, exist_ok=True)
            except FileExistsError:
                pass
        pushd = XCGF.Pushd(output_dir)

        rsync_servers = self.conf.get('rsync/servers')
        pacserve_server = self.conf.get('pacserve/server')

        if dbs:
            for db, sigs, files in download_queue.dbs:
                if files:
                    db_ext = FILES_EXT
                else:
                    db_ext = DB_EXT
                is_local = False
                for server in db.servers:
                    if server[:7] == 'file://':
                        db_name = db.name + db_ext
                        local_path = os.path.join(server[7:], db_name)
                        output_path = os.path.join(output_dir, db_name)
                        try:
                            XCGF.copy_file_and_maybe_sig(local_path, output_path, sig=sigs)
                        except FileNotFoundError:
                            continue
                        else:
                            is_local = True
                            break
                if is_local:
                    continue
                if rsync_servers and db.name in OFFICIAL_REPOSITORIES:
                    rsync_queue.add_db(db, sigs, files)
                else:
                    metalink_queue.add_db(db, sigs, files)

        else:
            queued = dict()
            for pkg, urls, sigs in download_queue.sync_pkgs:
                is_local = False
                for server in urls:
                    if server[:7] == 'file://':
                        local_path = server[7:]
                        output_path = os.path.join(output_dir, pkg.filename)
                        try:
                            XCGF.copy_file_and_maybe_sig(local_path, output_path, sig=sigs)
                        except FileNotFoundError:
                            continue
                        else:
                            is_local = True
                            break
                if not is_local:
                    queued[pkg.filename] = pkg

            found = None
            if pacserve_server:
                queued_names = sorted(queued)
                found = search_pacserve(pacserve_server, queued_names)
                # The local pacserve server likely points to the same cache
                # directory. The incoming file would be written to the same file
                # that Pacserve is reading, thus truncating the file. Avoid this
                # by skipping the file if it has a valid checksum, otherwise remove
                # it and requery Pacserve.
                if found is not None:
                    unlinked = False
                    for filename, found_url in found.items():
                        if found_url.startswith(pacserve_server):
                            db_sha256sum = queued[filename].sha256sum
                            for cdir in self.pacman_conf.options['CacheDir']:
                                file_cachepath = os.path.join(cdir, filename)
                                cache_sha256 = XCGF.get_checksum(file_cachepath, typ='sha256')
                                if cache_sha256 is None:
                                    continue
                                if cache_sha256 != db_sha256sum:
                                    os.unlink(file_cachepath)
                                    unlinked = True
                                    continue
                                break
                    if unlinked:
                        found = search_pacserve(pacserve_server, queued_names)

        for pkg, urls, sigs in download_queue.sync_pkgs:
            use_pacserve = True
            try:
                urls = [found[pkg.filename]]
            except (KeyError, TypeError):
                use_pacserve = False

            if not use_pacserve \
                    and not self.conf.get('rsync/db only') \
                    and rsync_servers \
                    and pkg.db.name in OFFICIAL_REPOSITORIES:
                rsync_queue.add_sync_pkg(pkg, urls, sigs)
            else:
                metalink_queue.add_sync_pkg(pkg, urls, sigs)

        metalink_queue.aur_pkgs = download_queue.aur_pkgs

        if metalink_queue:
            metalink = str(
                pm2ml.download_queue_to_metalink(metalink_queue, set_preference=dbs)
            ).encode()
            aria2_cmd = [
                self.conf.get('aria2/path'),
                '--metalink-file=-',
            ] + self.conf.get('aria2/args')
            if dbs:
                aria2_cmd += [
                    '--split=1',
                ]
            if force:
                aria2_cmd += [
                    '--continue=false',
                    '--remove-control-file=true',
                    '--allow-overwrite=true',
                    '--conditional-get=false',
                ]
            elif dbs:
                aria2_cmd += [
                    '--continue=false',
                    '--remove-control-file=true',
                    '--allow-overwrite=true',
                    '--conditional-get=true',
                ]
            with pushd:
                aria2c_p = subprocess.Popen(aria2_cmd, stdin=subprocess.PIPE)
                aria2c_p.communicate(input=metalink)

        if rsync_queue:
            for rsync_server in rsync_servers:
                rsync_cmds = self.download_queue_to_rsync_cmds(
                    rsync_server,
                    rsync_queue,
                    output_dir=output_dir
                )
                with pushd:
                    rsync_ps = tuple(subprocess.Popen(cmd) for cmd in rsync_cmds)
                    es = tuple(p.wait() for p in rsync_ps)
                if all((e == 0) for e in es):
                    # Success
                    break
                if all((e in RSYNC_DOWNLOAD_ERROR_EXIT_CODES) for e in es):
                    # Server error, try another one.
                    continue
                msg = ''
                if len(es) > 1:
                    for i, e in enumerate(es):
                        if e == 0 or e in RSYNC_DOWNLOAD_ERROR_EXIT_CODES:
                            continue
                        msg += 'rsync process {:d} exited with {:d}\n'.format(i, e)
                else:
                    msg = 'rsync exited with {:d}\n'.format(es[0])
                raise PowerpillError('{}> server: {}'.format(msg, rsync_server))
            else:
                # Fall back on Aria2
                metalink2 = str(pm2ml.download_queue_to_metalink(rsync_queue)).encode()
                aria2_cmd2 = [
                    self.conf.get('aria2/path'),
                    '--metalink-file=-',
                ] + self.conf.get('aria2/args')
                with pushd:
                    aria2c_p2 = subprocess.Popen(aria2_cmd2, stdin=subprocess.PIPE)
                    aria2c_p2.communicate(input=metalink2)
                    e = aria2c_p2.wait()
                if e not in ARIA2_DOWNLOAD_ERROR_EXIT_CODES:
                    raise PowerpillError('aria2c exited with {:d}'.format(e))

        if metalink_queue:
            e = aria2c_p.wait()
            if e not in ARIA2_DOWNLOAD_ERROR_EXIT_CODES:
                raise PowerpillError('aria2c exited with {:d}'.format(e))

    def run_pacman(self, args=None):
        '''
        Run Pacman (or equivalent) with the given arguments.
        '''
        if args is None:
            args = list(unparse_args(self.pargs))
        return subprocess.call([self.conf.get('pacman/path')] + args)

    def refresh_databases(self, files=False, pm2ml_passthrough_args={}):
        '''
        Download Pacman sync databases.
        '''
        pacman_conf = self.pacman_conf
        sync_dir = os.path.join(pacman_conf.options['DBPath'], 'sync')
        pm2ml_args = ['-yso', sync_dir]
        if files:
            pm2ml_args.append('--files')
        pm2ml_args.extend(('--' + p for p in ('verbose', 'debug') if self.pargs[p] > 0))
        pm2ml_args.extend(self.pargs['pm2ml_options'])
        db_lockfile = os.path.join(pacman_conf.options['DBPath'], DB_LOCK_FILE)
        db_lock = XCGF.Lockfile(db_lockfile, DB_LOCK_NAME)
        with db_lock:
            self.download(pm2ml_args, dbs=True, force=(self.pargs['refresh'] > 1))
        self.pm2ml.refresh_databases(**pm2ml_passthrough_args)
        self.pargs['refresh'] = 0
        self.initialize_alpm()

    def initialize_alpm(self):
        '''
        Reinitialize the ALPM database.
        '''
        self.pm2ml.initialize_alpm()

    def download_packages(self):
        '''
        Download files to cache.
        '''
        pacman_conf = self.pacman_conf
        cachedir = pacman_conf.options['CacheDir'][0]
        pm2ml_args = list(self.get_pm2ml_pkg_download_args(dpath=cachedir))
        cache_lockfile = os.path.join(cachedir, CACHE_LOCK_FILE)
        cache_lock = XCGF.Lockfile(cache_lockfile, CACHE_LOCK_NAME)
        with cache_lock:
            self.download(pm2ml_args)

    def clean(self):
        '''
        Wrapper around clean.
        '''
        clean(get_cleaning_targets(self.pacman_conf))

    def get_architecture(self):
        '''
        Return the target architecture.
        '''
        arch = self.pacman_conf.options['Architecture']
        if arch is None or arch == 'auto':
            return platform.machine()
        return arch

    def use_color(self):
        '''
        Return the target architecture.
        '''
        color = self.pacman_conf.options['Color']
        if color not in ('always', 'never', 'auto'):
            color = 'never'
        if color == 'never':
            return False
        if color == 'always':
            return True
        return sys.stdout.isatty()

    # ------------------------ Operation Determiners ------------------------- #

    def no_operation(self):
        return (not self.pargs['sync'] and not self.pargs['other_operation'])

    def other_operation(self):
        return self.pargs['other_operation']

    def no_download(self):
        return (
            self.pargs['other_operation'] or not (
                self.pargs['sync'] and (
                    (
                        self.pargs['sysupgrade'] or self.pargs['args']
                    ) or self.pargs['refresh']
                )
            )
        )

    def info_operation(self):
        return '-i' in self.pargs['options'] or '--info' in self.pargs['options']

    def search_operation(self):
        return '-s' in self.pargs['options'] or '--search' in self.pargs['options']

    def list_operation(self):
        return '-l' in self.pargs['options'] or '--list' in self.pargs['options']

    def search_operation(self):
        return '-s' in self.pargs['options'] or '--search' in self.pargs['options']

    def proceed_to_installation(self):
        return self.pargs['downloadonly'] == 0 and (self.pargs['sysupgrade'] > 0 or self.pargs['args'])

    def query_upgrades(self):
        return ('-Q' in self.pargs['raw'] or '--query' in self.pargs['raw']) and \
               ('-u' in self.pargs['raw'] or '--upgrades' in self.pargs['raw'])


# ----------------------------------- Main ----------------------------------- #

def get_cleaning_targets(pacman_conf):
    yield os.path.join(pacman_conf.options['DBPath'], 'sync'), DB_LOCK_FILE
    for cachedir in pacman_conf.options['CacheDir']:
        yield cachedir, CACHE_LOCK_FILE


def clean(cleaning_targets):
    '''
    Clean up leftover download files in the sync database and package cache.
    '''
    for dpath, lockname in cleaning_targets:
        lockfile = os.path.join(dpath, lockname)
        lock = XCGF.Lockfile(lockfile, CACHE_LOCK_NAME)
        logging.info('cleaning {}'.format(dpath))
        with lock:
            for path in glob.iglob(os.path.join(dpath, '*' + ARIA2_EXT)):
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass
                except IOError as e:
                    logging.error('failed to remove {} [{}]'.format(path, e))
                    raise e
                else:
                    logging.debug('removed {}'.format(path))
    logging.info('cleaning complete')


def configure_logging(pargs, quiet=False):
    if quiet:
        level = logging.ERROR
    elif pargs['debug']:
        level = logging.DEBUG
    elif pargs['verbose']:
        level = logging.INFO
    elif pargs['quiet']:
        level = logging.ERROR
    else:
        level = None

    XCGF.configure_logging(level=level)


def main(args=None):
    pargs = parse_args(args)

    if pargs['help']:
        display_help()
        return 0

    configure_logging(pargs)
    powerpill = Powerpill(pargs)

    # Clean up before doing anything else.
    if pargs['powerpill_clean']:
        powerpill.clean()
        if powerpill.no_operation():
            return 0

    if not pargs['sync']:
        if pargs['files'] and pargs['refresh'] > 0:
            powerpill.refresh_databases(files=True)
        return powerpill.run_pacman()

    if pargs['refresh'] > 0:
        powerpill.refresh_databases()

    # Jump straight to Pacman if the operation does not involve a download.
    if powerpill.no_download():
        if pargs['other_operation']:
            return powerpill.run_pacman()
        else:
            return 0

    if pargs['sysupgrade'] > 0 or pargs['args']:
        powerpill.download_packages()

    if powerpill.proceed_to_installation():
        return powerpill.run_pacman()

    return 0


def run_main(args=None):
    try:
        return main(args)
    except (KeyboardInterrupt, BrokenPipeError):
        pass
    except (
        PermissionError,
        PowerpillError,
        pyalpm.error,
        XCGF.LockError,
        XCPF.XcpfError,
    ) as e:
        return e


if __name__ == '__main__':
    sys.exit(run_main())
