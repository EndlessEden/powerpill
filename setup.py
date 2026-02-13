#!/usr/bin/env python3

from distutils.core import setup
import time

setup(
    name='Powerpill',
    version=time.strftime('%Y.%m.%d.%H.%M.%S', time.gmtime(  1637376062)),
    description='''Pacman wrapper for faster downloads.''',
    author='Xyne',
    author_email='gro xunilhcra enyx, backwards',
    url='''http://xyne.dev/projects/powerpill''',
    py_modules=['Powerpill'],
    scripts=['powerpill']
)
