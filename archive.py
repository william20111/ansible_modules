#!/usr/bin/python
# based off the ansible unarchive


DOCUMENTATION = '''
---
module: archive.py
version: 1.0
short_description: This module archives and stores directory
description:
    - the M(archive) module archives directorys. And can manage the number of archives stored in the dest directory
options:
    src:
      description:
        - The src directory is the directory to be archived.
      required: true
      default: null
    dest:
      description:
        - the dest directory is the directory to store the archive in.
      required: true
      default: null
    archive:
      description:
        - The name of the archive file which will have date-time stamped onto it.
      required: true
      default: null
    arch_type:
      description:
        - The archive type, choices include zip, tar, tar.gz, tar.bz2, tar.xz
      required: false
      default: tgz
    number:
      description:
        - The number of archives to be maintained in the dest directory. If you set 5 it the module will auto delete the oldest when you surpass the limit using os st_ctime
    required: false
    default: null
author: "William Fleming (@will_123)"
todo:
  - add some extra error catching and checks
  - auto detect the file extension and not require user to enter it
  - re-implement tar support using native tarfile module
  - re-implement zip support using native zipfile module
notes:
  -  requires C(gtar)/C(unzip) command on target host
  -  can handle I(gzip), I(bzip2) and I(xz) archives as well as uncompressed tar files
'''

EXAMPLES = '''
# Example from Ansible Playbooks
- archive: src=/home/jimbo dest=/home/jimbo/archives archive=home.tar

# archive home folder using bz2 compression
- unarchive: src=/home/jimbo dest=/home/jimbo/archives archive=home.tar.bz2 arch_type=bz2

# archive home foler using bz2 compression and only maintain 5 most recent archives in dest folder
- archive: src=/home/jimbo dest=/home/jimbo/archives archive=home.tar.bz2 arch_type=bz2 number=5
'''

import os
import datetime


class TgzArchive(object):
    def __init__(self, src, dest, archive, number, module):
        self.src = src
        self.dest = dest
        self.number = number
        self.archive = archive
        self.module = module
        self.cmd_path = self.module.get_bin_path('tar')
        self.zipflag = 'z'
        self.extension = '.tar.gz'

    def archive_dir(self):
        cmd = '%s -v%scf %s/%s %s' % (self.cmd_path, self.zipflag, self.dest, self.archive, self.src)
        rc, out, err = self.module.run_command(cmd)
        return dict(cmd=cmd, rc=rc, out=out, err=err)

    def archive_check(self, arch_type):
        if arch_type == 'tgz':
            return True

    def archive_removal(self):
        dir_list = os.listdir(self.dest)
        archives = [archive for archive in dir_list if self.extension in archive]
        filedata = {}
        for fname in archives:
            filedata[os.path.join(self.dest, fname)] = os.stat(os.path.join(self.dest, fname)).st_mtime
        filedata_sorted = sorted(filedata, key=filedata.get)
        if len(filedata_sorted) > self.number:
            delete = len(filedata_sorted) - self.number
            for x in range(0, delete):
                try:
                    os.remove(filedata_sorted[x])
                except IOError:
                    err = "failed to remove %s" % (filedata_sorted[x])
                    return dict(err=err, out=archives)
        dir_list = os.listdir(self.dest)
        archives = [archive for archive in dir_list if self.extension in archive]
        return dict(out=archives)


# class to handle tar files that aren't compressed
class TarArchive(TgzArchive):
    def __init__(self, src, dest, archive, number, module):
        self.src = src
        self.dest = dest
        self.module = module
        self.archive = archive
        self.number = number
        self.cmd_path = self.module.get_bin_path('tar')
        self.zipflag = ''
        self.extension = '.tar'

    def archive_check(self, arch_type):
        if arch_type == 'tar':
            return True


# class to handle bzip2 compressed tar files
class TarBzip(TgzArchive):
    def __init__(self, src, dest, archive, number, module):
        self.src = src
        self.dest = dest
        self.number = number
        self.module = module
        self.archive = archive
        self.cmd_path = self.module.get_bin_path('tar')
        self.zipflag = 'j'
        self.extension = '.tar.bz2'

    def archive_check(self, arch_type):
        if arch_type == 'bz2':
            return True


# class to handle xz compressed tar files
class TarXz(TgzArchive):
    def __init__(self, src, dest, archive, number, module):
        self.src = src
        self.dest = dest
        self.number = number
        self.module = module
        self.archive = archive
        self.cmd_path = self.module.get_bin_path('tar')
        self.zipflag = 'J'
        self.extension = '.tar.xz'

    def archive_check(self, arch_type):
        if arch_type == 'xz':
            return True


class ZipArchive(object):
    def __init__(self, src, dest, archive, number, module):
        self.src = src
        self.dest = dest
        self.archive = archive
        self.number = number
        self.module = module
        self.cmd_path = self.module.get_bin_path('zip')
        self.extension = '.zip'

    def archive_dir(self):
        cmd = '%s -r %s/%s %s' % (self.cmd_path, self.dest, self.archive, self.src)
        rc, out, err = self.module.run_command(cmd)
        return dict(cmd=cmd, rc=rc, out=out, err=err)

    def archive_check(self, arch_type):
        if not self.cmd_path:
            return False
        arch_type = self.module.get_bin_path(arch_type)
        if arch_type == self.cmd_path:
            return True

    def archive_removal(self):
        dir_list = os.listdir(self.dest)
        archives = [archive for archive in dir_list if self.extension in archive]
        filedata = {}
        for fname in archives:
            filedata[os.path.join(self.dest, fname)] = os.stat(os.path.join(self.dest, fname)).st_mtime
        filedata_sorted = sorted(filedata, key=filedata.get)
        if len(filedata_sorted) > self.number:
            delete = len(filedata_sorted) - self.number
            for x in range(0, delete):
                try:
                    os.remove(filedata_sorted[x])
                except IOError:
                    err = "failed to remove %s" % (filedata_sorted[x])
                    return dict(err=err, out=archives)
        dir_list = os.listdir(self.dest)
        archives = [archive for archive in dir_list if self.extension in archive]
        return dict(out=archives)


# try handlers in order and return the one that works or bail if none work
def pick_handler(src, dest, arch_type, archive, number, module):
    handlers = [ZipArchive, TgzArchive, TarBzip, TarXz, TarArchive]
    for handler in handlers:
        obj = handler(src, dest, archive, number, module)
        if obj.archive_check(arch_type):
            return obj
    module.fail_json(
        msg='Failed to find handler to archive. Make sure the required command to extract the file is installed.')


def main():
    module = AnsibleModule(
        # not checking because of daisy chain to file module
        argument_spec=dict(
            src=dict(required=True),
            dest=dict(required=True),
            archive=dict(required=True),
            number=dict(required=False, type='int'),
            arch_type=dict(required=False, default='tgz', choices=['tgz', 'zip', 'tar', 'bz2', 'xz']),
        )
    )

    src = os.path.expanduser(module.params['src'])
    dest = os.path.expanduser(module.params['dest'])
    number = module.params['number']
    arch_type = module.params['arch_type']
    archive = module.params['archive']

    # does tar file exist and perms
    if not os.path.exists(src):
        module.fail_json(msg="Source '%s' does not exist" % src)
    if not os.access(src, os.R_OK):
        module.fail_json(msg="Source '%s' not readable" % src)

    # does dest folder exist
    if not os.path.exists(os.path.dirname(dest)):
        module.fail_json(msg="Destination directory '%s' does not exist" % (os.path.dirname(dest)))
    if not os.access(os.path.dirname(dest), os.W_OK):
        module.fail_json(msg="Destination '%s' not writable" % (os.path.dirname(dest)))

    if not number:
        handler = pick_handler(src, dest, arch_type, archive, module)
        res_args = dict(handler=handler.__class__.__name__, dest=dest, src=src, archive=archive)
    else:
        now = datetime.datetime.now()
        archive_tstmp = datetime.datetime.strftime(now, '%d-%m-%Y-%H-%M-%-S') + "-" + archive
        handler = pick_handler(src, dest, arch_type, archive_tstmp, number, module)
        res_args = dict(handler=handler.__class__.__name__, dest=dest, src=src, archive=archive)

    # do the unpack
    try:
        res_args['archive_results'] = handler.archive_dir()
        if res_args['archive_results']['rc'] != 0:
            module.fail_json(msg="failed to archive %s to %s" % (src, dest), **res_args)
    except IOError:
        module.fail_json(msg="failed to archive %s to %s" % (src, dest), **res_args)
    else:
        res_args['changed'] = True

    # do archive removal check
    if number:
        try:
            res_args['archive_removal_results'] = handler.archive_removal()
        except IOError:
            module.fail_json(msg="failed on archiving purge for %s" % dest, **res_args)
        else:
            res_args['changed'] = True

    module.exit_json(**res_args)


# import module snippets
from ansible.module_utils.basic import *

main()
