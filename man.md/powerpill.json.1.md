# Name

powerpill.json - Powerpill configuration file


# Description
The Powerpill configuration file is a plain JSON file. By default it is located at `/etc/powerpill/powerpill.json`. The main object is a dictionary that holds multiple dictionaries. The latter are considered sections of the configuration file and contain options related to different parts of Powerpill.


# Sections
Note that all fields, including section names, are in lower case in the file. Upper case may appear in the man page during automatic conversion of the markdown file. For example, the first section is "aria2", *not* "ARIA2".

## aria2
Options for configuring Aria2.

args
:   The list of arguments to pass to the Aria2 binary. See Aria2's man page for details. By default Aria2 will also load `$HOME/.aria2/aria2.conf`. When run with sudo, this will refer to root's home directory. To disable this, use the `--no-conf` option. To use a powerpill-specific Aria2 configuration file, use the `--conf-path` option, for example `--conf-path=/etc/powerpill/aria2.conf`.

path
:   The path to the Aria2 executable.

    Default: `/usr/bin/aria2c`



## pacman
Options for configuring Pacman.

config
:   The path to the configuration file.

path
:   The path to the Pacman executable.

    Default: `/usr/bin/pacman`



## pacserve
Options for enabling Pacserve support. When enabled, Powerpill will preferentially download files from the Pacserve server to save bandwidth.

server
:   The URI of the Pacserve server. If `null` then Pacserve support is disabled. If set, this should only contain the protocol, the host and the port, e.g.

        "server" : "http://localhost:15678"


## powerpill
Options that control Powerpill behavior.

select
:   Present a package selection dialogue when downloading package groups.

reflect databases
:   Use Reflector when retrieving databases. This may lead to mismatches between databases and their signatures if the retrieved mirrors are not synchronized.


## reflector
Options for configuring Reflector support. Reflector can retrieve the current
list of mirrors from the Arch Linux server's web API and use them for parallel
downloads.

args
:   The list of arguments to pass to Reflector. See `reflector --help` for
    details. The default configuration file includes an entry named
    "args.unused" as a starting point. Change this to "args" to enable the
    default arguments.



## rsync
Options for configuring Rsync.

args
:   The list of arguments to pass to Rsync. In general, the only options
    that should be passed are those that affect console output during the
    operation, but not the operation itself. E.g. `--no-motd`, '--verbose`.

    Sometimes Rsync will attempt to redownload a file if the modification time
    of the server file is newer than the local file. To prevent this the
    "--checksum" option may be used, but not all Rsync servers allow this option
    due to the additional overhead of computing the checksum.

db only
:   If true, Rsync will only be used to download the databases and all package
    downloads will be handled by Aria2.

path
:   The path to the Rsync executable.

    Default: `/usr/bin/rsync`

servers
:   A list of Rsync-enabled Pacman mirrors, double-quoted and separated with commas. You can find them with `reflector -p rsync`. Each entry should include the full server URL starting with `rsync://` and ending with `$repo/os/$arch`. Leave this list empty or remove it from the file to disable Rsync support. Syntax example:

    "servers": [
      "rsync://example.com/archlinux/$repo/os/$arch",
      "rsync://mirrors.kernel.org/archlinux/$repo/os/$arch"
    ]



# Download Progress
By default Powerpill will display output from Aria2 and Rsync during the download. To disable Aria2 output, add the `--quiet` option to the Aria2 arguments list. To disable output from Rsync, remove `--progress` and `--verbose` from the Rsync arguments list.

