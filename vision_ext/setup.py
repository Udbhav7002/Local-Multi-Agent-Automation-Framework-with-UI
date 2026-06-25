from setuptools import setup, Extension
import pybind11
import os

class get_pybind_include(object):
    def __init__(self, user=False):
        self.user = user
    def __str__(self):
        return pybind11.get_include(self.user)

# Common homebrew paths for Apple Silicon and Intel Macs
include_dirs = [
    get_pybind_include(),
    get_pybind_include(user=True),
    '/opt/homebrew/include',
    '/opt/homebrew/include/opencv4',
    '/usr/local/include',
    '/usr/local/include/opencv4'
]

library_dirs = [
    '/opt/homebrew/lib',
    '/usr/local/lib'
]

ext_modules = [
    Extension(
        'vision_ext',
        ['vision_parser.cpp'],
        include_dirs=include_dirs,
        library_dirs=library_dirs,
        libraries=['opencv_core', 'opencv_imgproc', 'tesseract'],
        extra_compile_args=['-std=c++17'],
        language='c++'
    ),
]

setup(
    name='vision_ext',
    version='1.0',
    ext_modules=ext_modules,
    zip_safe=False,
)
