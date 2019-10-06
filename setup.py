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


ext_modules = [
    Extension(
        '_diffcp',
        glob("cpp/src/*.cpp") + glob("cpp/src/*.c"),
        include_dirs=[
            # Path to pybind11 headers
            get_pybind_include(),
            get_pybind_include(user=True),
            "cpp/external/eigen",
            "cpp/include"
        ],
        language='c++',
        extra_compile_args=["-O3"]
    ),
]


# As of Python 3.6, CCompiler has a `has_flag` method.
# cf http://bugs.python.org/issue26689
def has_flag(compiler, flagname):
    """Return a boolean indicating whether a flag name is supported on
    the specified compiler.
    """
    import tempfile
    with tempfile.NamedTemporaryFile('w', suffix='.cpp') as f:
        f.write('int main (int argc, char **argv) { return 0; }')
        try:
            compiler.compile([f.name], extra_postargs=[flagname])
        except setuptools.distutils.errors.CompileError:
            return False
    return True


def cpp_flag(compiler):
    flag = '-std=c++11'

    if has_flag(compiler, flag):
        return flag

    raise RuntimeError('Unsupported compiler -- at least C++11 support '
                       'is needed!')


class BuildExt(build_ext):
    """A custom build extension for adding compiler-specific options."""
    c_opts = {
        'msvc': ['/EHsc'],
        'unix': [],
    }
    l_opts = {
        'msvc': [],
        'unix': [],
    }

    if sys.platform == 'darwin':
        darwin_opts = ['-stdlib=libc++', '-mmacosx-version-min=10.7']
        c_opts['unix'] += darwin_opts
        l_opts['unix'] += darwin_opts

    def build_extensions(self):
        ct = self.compiler.compiler_type
        opts = self.c_opts.get(ct, [])
        link_opts = self.l_opts.get(ct, [])
        if ct == 'unix':
            opts.append('-DVERSION_INFO="%s"' % self.distribution.get_version())
            opts.append(cpp_flag(self.compiler))
            if has_flag(self.compiler, '-fvisibility=hidden'):
                opts.append('-fvisibility=hidden')
        elif ct == 'msvc':
            opts.append('/DVERSION_INFO=\\"%s\\"' % self.distribution.get_version())
        for ext in self.extensions:
            ext.extra_compile_args = opts
            ext.extra_link_args = link_opts
        build_ext.build_extensions(self)

setup(
    name='diffcp',
    version="1.0.4",
    author="Akshay Agrawal, Shane Barratt, Stephen Boyd, Enzo Busseti, Walaa Moursi",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    install_requires=[
        "numpy >= 1.15",
        "scs >= 2.1.1",  # no more AA iteration prints
        "scipy >= 1.1.0",
        "pybind11 >= 2.4"],
    setup_requires=['pybind11>=2.4'],
    url="http://github.com/cvxgrp/diffcp/",
    ext_modules=ext_modules,
    cmdclass={'build_ext': BuildExt},
    license="Apache License, Version 2.0",
    classifiers=[
        "Programming Language :: Python :: 3",
    ],
)
