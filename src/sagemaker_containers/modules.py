# Copyright 2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the 'License'). You
# may not use this file except in compliance with the License. A copy of
# the License is located at
#
#     http://aws.amazon.com/apache2.0/
#
# or in the 'license' file accompanying this file. This file is
# distributed on an 'AS IS' BASIS, WITHOUT WARRANTIES OR CONDITIONS OF
# ANY KIND, either express or implied. See the License for the specific
# language governing permissions and limitations under the License.
from __future__ import absolute_import

import importlib
import logging
import os
import shlex
import subprocess
import sys
import tarfile
import traceback

import boto3
from six.moves.urllib.parse import urlparse

from sagemaker_containers import env


logger = logging.getLogger(__name__)

DEFAULT_MODULE_NAME = 'default_user_module_name'


def s3_download(url, dst):  # type: (str, str) -> None
    """Download a file from S3.

    Args:
        url (str): the s3 url of the file.
        dst (str): the destination where the file will be saved.
    """
    url = urlparse(url)

    if url.scheme != 's3':
        raise ValueError("Expecting 's3' scheme, got: %s in %s" % (url.scheme, dst))

    bucket, key = url.netloc, url.path.lstrip('/')

    s3 = boto3.resource('s3')
    s3.Bucket(bucket).download_file(key, dst)


def prepare(path, name):  # type: (str, str) -> None
    """Prepare a Python script (or module) to be imported as a module.

    If the script does not contain a setup.py file, it creates a minimal setup.

    Args:
        path (str): path to directory with the script or module.
        name (str): name of the script or module.
    """
    if not os.path.exists(os.path.join(path, 'setup.py')):
        logging.info('Module %s does not provide a setup.py. Generating a minimal setup.' % name)

        with open(os.path.join(path, 'setup.py'), 'w') as f:
            lines = ['from setuptools import setup',
                     'setup(name="%s", py_modules=["%s"])' % (name, name)]

            f.write(os.linesep.join(lines))


def install(path):  # type: (str) -> None
    """Install a Python module in the executing Python environment.

    Args:
        path (str):  Real path location of the Python module.
    """
    if not sys.executable:
        raise RuntimeError('Failed to retrieve the real path for the Python executable binary')
    try:
        subprocess.check_call(shlex.split('%s -m pip install %s -U' % (sys.executable, path)))
    except subprocess.CalledProcessError:
        raise RuntimeError('Failed to pip install %s:%s%s' % (path, os.linesep, traceback.format_exc()))


def download_and_import(url, name=DEFAULT_MODULE_NAME):  # type: (str, str) -> module
    """Download, prepare and install a compressed tar file from S3 as a module.

    SageMaker Python SDK saves the user provided scripts as compressed tar files in S3
    https://github.com/aws/sagemaker-python-sdk.

    This function downloads this compressed file, transforms it as a module, and installs it.

    Args:
        url (str): the s3 url of the file.
        name (str): name of the script or module.

    Returns:
        (module): the imported module
    """
    with env.tmpdir() as tmpdir:
        dst = os.path.join(tmpdir, 'tar_file')
        s3_download(url, dst)

        module_path = os.path.join(tmpdir, 'module_dir')

        os.makedirs(module_path)

        with tarfile.open(name=dst, mode='r:gz') as t:
            t.extractall(path=module_path)

            prepare(module_path, name)

            install(module_path)

            return importlib.import_module(name)
