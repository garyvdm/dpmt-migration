#!/usr/bin/env python3

import os
import shutil
import subprocess
import re


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
match /(metainfo|modules|tools|www)/
end match

match /packages/(trunk|tags|debian)/
end match

# packages that get renamed
match /packages/(pyth|python-pyth)/ 
end match


match (?:/packages)?/([^/]+)/trunk/
  repository \1
  branch master
end match

#match (?:/packages)?/([^/]+)/branches/([^/]+)/
#  repository \1
#  branch \2
#end match

match (?:/packages)?/([^/]+)/branches/
end match

match (?:/packages)?/([^/]+)/tags/([^/]+)/
  repository \1
  branch refs/tags/\2
  # same as git-buildpackage's _sanitize_version
  substitute branch s/~/_/
  substitute branch s/:/%/
end match

match (?:/packages)?/([^/]+)/debian/
  repository \1
  branch master
end match

match (?:/packages)?/([^/]+)/(?!debian|branches|tags|trunk)[^/]+
end match

''')


def migrate():
    # TODO: identity-map
    subprocess.check_call((SVN2GIT, '--rules=rules.txt', '--stats',
                           '../python-modules'))

def clean_svn_buildpackages_commits(gitdir):
    """Rewrites svn-buildpackages so that the only have one parent."""

    run = subprocess.check_output

    base_git_args = ['git', '--git-dir={}'.format(gitdir)]
    refs = run(base_git_args + ['show-ref', '--tags'])

    is_svn_buildpackage = re.compile(b'\n\n\[svn-buildpackage\]', flags=re.DOTALL).search

    for ref in refs.splitlines():
        ref_sha, _, ref_name = ref.partition(b' ')
        commit = run(base_git_args + ['cat-file', '-p', ref_sha])
        if is_svn_buildpackage(commit):
            first_parent = run(base_git_args + ['rev-list', ref_sha, '-n 2']).splitlines()[1]
            r = b'^parent (?!' + first_parent + b').*?\n'
            new_commit, _ = re.subn(r, b'', commit, flags=re.MULTILINE)

            hash_object_proc = subprocess.Popen(base_git_args + ['hash-object', '-w', '-t', 'commit', '--stdin'],
                                                stdin=subprocess.PIPE, stdout=subprocess.PIPE)
            hash_object_proc.stdin.write(new_commit)
            hash_object_proc.stdin.close()
            hash_object_proc.wait()
            new_commit_sha = hash_object_proc.stdout.read().strip()

            run(base_git_args + ['update-ref',
                                 '-m', 'svn-buildpackage multiple parent cleanup',
                                 ref_name, new_commit_sha, ref_sha])


def println(f, line=''):
    f.write(line + '\n')

if __name__ == '__main__':
    main()
