from setuptools import Extension, setup, find_packages
from setuptools.command.build_ext import build_ext
import sys
import setuptools
from glob import glob

with open("README.md", "r") as fh:
    long_description = fh.read()

class get_pybind_include(object):
    """Helper class to determine the pybind11 include path

    The purpose of this class is to postpone importing pybind11
    until it is actually installed, so that the ``get_include()``
    method can be invoked. """

    def __init__(self, user=False):
        self.user = user

    def __str__(self):
        import pybind11
        return pybind11.get_include(self.user)


_proj = Extension("_proj",
                  sources=["diffcp/proj.c"],
                  extra_compile_args=["-O3"])

_diffcp = Extension(
        '_diffcp',
        glob("cpp/src/*.cpp") + glob("cpp/src/*.c"),
        include_dirs=[
            get_pybind_include(),
            get_pybind_include(user=True),
            "cpp/external/eigen",
            "cpp/include"
        ],
        language='c++',
        extra_compile_args=["-O3", "-std=c++11"]
)

ext_modules = [_proj, _diffcp]

setup(
    name='diffcp',
    version="1.0.4",
    author="Akshay Agrawal, Shane Barratt, Stephen Boyd, Enzo Busseti, Walaa Moursi",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    setup_requires=['pybind11 >= 2.4'],
    install_requires=[
        "numpy >= 1.15",
        "scs >= 2.1.1",
        "scipy >= 1.1.0",
        "pybind11 >= 2.4"],
    url="http://github.com/cvxgrp/diffcp/",
    ext_modules=ext_modules,
    license="Apache License, Version 2.0",
    classifiers=[
        "Programming Language :: Python :: 3",
    ],
)
