#!/usr/bin/env python3

import os
import shutil
import subprocess


SVN2GIT = 'svn2git'


def main():
    prepare()
    write_rules()
    migrate()


def prepare():
    target = 'migrated'
    if os.path.exists(target):
        shutil.rmtree(target)
    os.mkdir(target)
    os.chdir(target)


def write_rules():
    packages = []
    with open('../packages') as f:
        for line in f:
            packages.append(line.strip())

    with open('rules.txt', 'w') as f:
        for package in packages:
            println(f, 'create repository {}'.format(package))
            println(f, 'end repository')
            println(f)
        println(f, r'''
match /packages/([^/]+)/trunk/
  repository \1
  branch master
end match

#match /packages/([^/]+)/branches/([^/]+)/
#  repository \1
#  branch \2
#end match

match /packages/([^/]+)/branches/
end match

match /packages/([^/]+)/tags/([^/]+)/
  repository \1
  branch refs/tags/\2
  # same as git-buildpackage's _sanitize_version
  substitute branch s/~/_/
  substitute branch s/:/%/
end match

match /packages/([^/]+)/debian/
  repository \1
  branch master
end match

match /packages/([^/]+)/(?!debian|branches|tags|trunk)[^/]+/
end match

match /(gnupginterface|pygoogle|pyspf|urwid)/
#  repository \1
#  branch master
end match

match /(metainfo|modules|tools|www)/
end match
''')


def migrate():
    # TODO: identity-map
    subprocess.check_call((SVN2GIT, '--rules=rules.txt', '--stats',
                           '../python-modules'))


def println(f, line=''):
    f.write(line + '\n')

if __name__ == '__main__':
    main()
