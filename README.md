[!IMPORTANT]

    Mirror & Modification Notice: This repository is a community-maintained mirror and updated fork of Xyne's powerpill. The original project and documentation are located at https://xyne.dev/projects/powerpill/.

About

   Powerpill is a Pacman wrapper that uses parallel and segmented downloading through Aria2 and Reflector to try to speed up downloads for Pacman. Powerpill can also use Rsync for official mirrors that support it. This can be efficient for users who already use full bandwidth when downloading from a single mirror. Pacserve is also supported via the configuration file and will be used before downloading from external mirrors.


History

   Powerpill goes back to the beginning of my(xyne) time with Arch Linux. The original version was a very simple Perl script posted on the forum shortly after signing up. Over time it acquired features and became a full Pacman wrapper, eventually duplicating a lot of ALPM's functionality and spawning a collection of Perl libraries.

   When Pacman finally switched to locally tarred databases, the Perl libraries were abandoned. Reflector was salvaged from that tangled abyss, but Powerpill was left to be forgotten. The idea nevertheless lived on. First came pacman2aria2, which was refined into pm2ml. Building on pm2ml, the current implementation of Powerpill was reborn as a full yet superficial Pacman wrapper.

---

Metadata

    Version: 2021.11

    License: GPLv2

    Architecture: any

    URL: https://xyne.dev/projects/powerpill

Dependencies

    aria2

    pm2ml (>2012.12.12)

    pyalpm

    python3

    python3-xcgf

    python3-xcpf

Optional Dependencies

    python3-threaded_servers: internal Pacserve support.

    reflector: Reflector and Rsync support.

    rsync: Rsync download support.

---

Configuration

   The powerpill configuration file is located at /etc/pacboy/config-powerpill.json by default. Refer to the powerpill.json man page for details.
   The official Pacman repos do not provide database signature files. To avoid download errors, set the SigLevel setting of each offical repo to PackageRequired, e.g.
    
    [core]
    SigLevel = PackageRequired

Pacserve

If you have pacserve installed and configured, Powerpill will attempt to use it to find local copies of packages before downloading from the internet. This is configured in the powerpill.json file.

---

POWERPILL.JSON(1)
    powerpill.json - Powerpill configuration file
    
 Description

The Powerpill configuration file is a plain JSON file. By default it is located at /etc/powerpill/powerpill.json. The main object is a dictionary that holds multiple dictionaries. The latter are considered sections of the configuration file and contain options related to different parts of Powerpill.
Sections

Note that all fields, including section names, are in lower case in the file. Upper case may appear in the man page during automatic conversion of the markdown file. For example, the first section is “aria2”, not “ARIA2”.
aria2

Options for configuring Aria2.

args
    The list of arguments to pass to the Aria2 binary. See Aria2’s man page for details. By default Aria2 will also load $HOME/.aria2/aria2.conf. When run with sudo, this will refer to root’s home directory. To disable this, use the --no-conf option. To use a powerpill-specific Aria2 configuration file, use the --conf-path option, for example --conf-path=/etc/powerpill/aria2.conf. 
path

  The path to the Aria2 executable.

    Default: /usr/bin/aria2c

pacman

Options for configuring Pacman.

config
  The path to the Pacman executable.

    Default: /usr/bin/pacman

pacserve

Options for enabling Pacserve support. When enabled, Powerpill will preferentially download files from the Pacserve server to save bandwidth.

server

  The URI of the Pacserve server. If null then Pacserve support is disabled. If set, this should only contain the protocol, the host and the port, e.g.

    "server" : "http://localhost:15678"

powerpill

Options that control Powerpill behavior.

select
    
    Present a package selection dialogue when downloading package groups. 

reflect databases

    Use Reflector when retrieving databases. This may lead to mismatches between databases and their signatures if the retrieved mirrors are not synchronized. 

reflector

Options for configuring Reflector support. Reflector can retrieve the current list of mirrors from the Arch Linux server’s web API and use them for parallel downloads.

args
    
    The list of arguments to pass to Reflector. See reflector --help for details. The default configuration file includes an entry named “args.unused” as a starting point. Change this to “args” to enable the default arguments. 

rsync

Options for configuring Rsync.

args

    The list of arguments to pass to Rsync. In general, the only options that should be passed are those that affect console output during the operation, but not the operation itself. E.g. --no-motd, ’–verbose`.

    Sometimes Rsync will attempt to redownload a file if the modification time of the server file is newer than the local file. To prevent this the “–checksum” option may be used, but not all Rsync servers allow this option due to the additional overhead of computing the checksum.
db only
    If true, Rsync will only be used to download the databases and all package downloads will be handled by Aria2. 
path

    The path to the Rsync executable.

    Default: /usr/bin/rsync
servers

    A list of Rsync-enabled Pacman mirrors, double-quoted and separated with commas. You can find them with reflector -p rsync. Each entry should include the full server URL starting with rsync:// and ending with $repo/os/$arch. Leave this list empty or remove it from the file to disable Rsync support. Syntax example:

    “servers”: [ “rsync://example.com/archlinux/repo/os/arch”, “rsync://mirrors.kernel.org/archlinux/repo/os/arch”]

Download Progress

By default Powerpill will display output from Aria2 and Rsync during the download. To disable Aria2 output, add the --quiet option to the Aria2 arguments list. To disable output from Rsync, remove --progress and --verbose from the Rsync arguments list.
Help Message

$ powerpill --help

USAGE
  powerpill [powerpill options] [pacman args]

OPTIONS
  Powerpill should accept the same arguments as Pacman, e.g.

      powerpill -Syu

  See "pacman --help" for further help.

  The following additional arguments are supported:

    --powerpill-config <path>
        The path to a Powerpill configuration file.
        Default: /etc/powerpill/powerpill.json

    --powerpill-clean
        Clean up leftover .aria2 files from an unrecoverable download. Use this
        option to resolve aria2c length mismatch errors.
---


CHANGELOG
2016-01-15

    Updated pm2ml argument handling.
    Added quiet option to configure_logging.
    Optionally ignore ignored packages (i.e. include them) for system upgrade calculations (necessary for pacman -Qu emulation).

2015-11-21

    Changed “ask” option to “select” to avoid overlap with unrelated “–ask” option in pacman.

2014-08-17

    Added --remote-time=true to the default Aria2 arguments in powerpill.json.

2014-08-12

    use metalink preferences to enforce user mirror preferences when downloading databases.

2014-08-11

    correction handle -Sl and -Ss when no list or search arguments are given.

2013-05-10

    updated for Pacserve compatibility

2013-05-09

    recognize Pacman’s –color option

2013-03-13

    pass through Pacman binary return codes

2013-01-31

    added new powerpill/reflect databases to powerpill.json

2012-12-12

    rsync/server has been renamed rsync/servers and converted to a list in powerpill.json. Powerpill will try each server in the list until the download succeeds or the list is exhausted. In the latter case, Powerpill will attempt to use Aria2 instead for official packages.
    added powerpill/ask option to control behavior of package selection dialogue for package groups

2012-12-07

    Ariac and Rsync output are now displayed by default: see the powerpill.json manual page for instructions to disable this output

2012-12-02

    added bash-completion file

2012-11-29

    refactored code
    added more robust option parsing
    replaced powerpill.conf with powerpill.json for more versatile configuration
    added powerpill.json man page
    removed aria2.conf (should now be configured via Aria2 arguments in powerpill.json.

TODO

    add signal handlers and propagate signals to subprocesses
    add group selection dialogue (optionally based on curses/dialog checklist)

---

GPLv2 Compliance

This software is licensed under the GNU General Public License, version 2.

    Original Author: Xyne (https://xyne.dev/)

    Mirror Maintainer: EndlessEden

In accordance with Section 2(a) of the GPLv2, this file serves as a prominent notice that this repository may contain modified versions of the original work by Xyne.

    This program is free software; you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation; either version 2 of the License, or (at your option) any later version.

---

Created based on the upstream source at xyne.dev/projects/powerpill/
