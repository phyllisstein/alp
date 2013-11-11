#!/usr/bin/env python

from distutils.core import setup

install_requires = [
    'six==1.3.0',
    'biplist==0.6',
    'beautifulsoup4==4.3.2',
    'requests==1.2.0',
    'requests-cache==0.4.4'
    ]

setup(name='Alp',
    version='1.5.0',
    description='A Python Module for Alfred Workflows',
    author='Daniel Shannon',
    author_email='d@daniel.sh',
    url='https://github.com/phyllisstein/alp',
    packages=['alp'],
    long_description=open('README.mdown').read(),
    install_requires=install_requires
    )